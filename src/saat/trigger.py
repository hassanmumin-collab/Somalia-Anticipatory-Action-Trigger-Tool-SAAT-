"""
Trigger tier evaluation with fail-loud data status mechanism.

Three rules, all derived from how trigger systems fail in practice:

1. **Fail loud.** A missing data source produces UNEVALUABLE, not INACTIVE.
   The characteristic failure of automated triggers is that a scraper breaks,
   the indicator reads null, the condition evaluates false, and the system
   reports calm through the event. That failure presents as calm.

2. **No discretion at activation time.** Thresholds are in config with verification
   evidence attached. If negotiable, it is a meeting, not a trigger.

3. **Record the counterfactual.** Log every evaluation to JSONL so the real-world
   contingency table can be built from operational history.

Reference: Section 6 of the build prompt.
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any
import json
from pathlib import Path


class DataStatus(Enum):
    """Data quality status for each indicator."""

    OK = "OK"  # Recent, complete, verified
    DEGRADED = "DEGRADED"  # Delayed (24-48 hours old) or partial
    MISSING = "MISSING"  # Down > 48 hours, using fallback
    STALE = "STALE"  # No update for > 48 hours, no fallback available


class TierStatus(Enum):
    """Activation status of a trigger tier."""

    INACTIVE = "INACTIVE"  # Evaluated, threshold not met
    ACTIVE = "ACTIVE"  # Threshold met, action triggered
    UNEVALUABLE = "UNEVALUABLE"  # Could not evaluate due to missing data
    ESCALATION = "ESCALATION"  # Data quality issue requires human review


@dataclass
class IndicatorReading:
    """A single indicator reading with data quality status."""

    indicator_name: str
    value: Optional[float]
    threshold: float
    operator: str  # ">=" or "<=" or ">" or "<"
    data_status: DataStatus
    source: str
    timestamp: datetime
    last_update: datetime
    update_age_hours: float
    fallback_used: bool = False
    fallback_source: Optional[str] = None
    notes: Optional[str] = None

    def is_met(self) -> bool:
        """Check if threshold condition is met (ignoring data status)."""
        if self.value is None:
            return False

        if self.operator == ">=":
            return self.value >= self.threshold
        elif self.operator == ">":
            return self.value > self.threshold
        elif self.operator == "<=":
            return self.value <= self.threshold
        elif self.operator == "<":
            return self.value < self.threshold
        else:
            raise ValueError(f"Unknown operator: {self.operator}")

    def is_usable(self) -> bool:
        """Check if data is usable for decision-making."""
        return self.data_status in [DataStatus.OK, DataStatus.DEGRADED]

    def requires_escalation(self) -> bool:
        """Check if this reading requires human review."""
        return self.data_status in [DataStatus.MISSING, DataStatus.STALE]


@dataclass
class TierEvaluation:
    """Complete evaluation of a single tier."""

    tier_name: str
    tier_number: int
    evaluation_time: datetime
    readings: List[IndicatorReading]
    combination_logic: str  # "and", "or", "majority", etc.
    status: TierStatus
    threshold_met: bool
    all_data_ok: bool
    has_missing_data: bool
    has_stale_data: bool
    rationale: str
    actions_triggered: Optional[List[str]] = None
    envelope_share: Optional[float] = None
    cost_loss_verified: bool = False
    verification_evidence: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSONL logging."""
        return {
            "tier_name": self.tier_name,
            "tier_number": self.tier_number,
            "evaluation_time": self.evaluation_time.isoformat(),
            "status": self.status.value,
            "threshold_met": self.threshold_met,
            "all_data_ok": self.all_data_ok,
            "has_missing_data": self.has_missing_data,
            "has_stale_data": self.has_stale_data,
            "rationale": self.rationale,
            "actions_triggered": self.actions_triggered,
            "envelope_share": self.envelope_share,
            "cost_loss_verified": self.cost_loss_verified,
            "readings": [
                {
                    "indicator": r.indicator_name,
                    "value": r.value,
                    "threshold": r.threshold,
                    "operator": r.operator,
                    "data_status": r.data_status.value,
                    "source": r.source,
                    "update_age_hours": r.update_age_hours,
                }
                for r in self.readings
            ],
        }


@dataclass
class SystemEvaluation:
    """Complete evaluation of the trigger system across all tiers."""

    evaluation_time: datetime
    tier_evaluations: Dict[int, TierEvaluation] = field(default_factory=dict)
    highest_active_tier: Optional[int] = None
    system_status: TierStatus = TierStatus.INACTIVE
    overall_rationale: str = ""
    escalations: List[str] = field(default_factory=list)

    def to_jsonl(self) -> str:
        """Convert to JSONL line for logging."""
        return json.dumps(
            {
                "evaluation_time": self.evaluation_time.isoformat(),
                "highest_active_tier": self.highest_active_tier,
                "system_status": self.system_status.value,
                "overall_rationale": self.overall_rationale,
                "escalations": self.escalations,
                "tier_evaluations": {
                    str(k): v.to_dict() for k, v in self.tier_evaluations.items()
                },
            }
        )

    def log_to_file(self, log_file: Path) -> None:
        """Append evaluation to JSONL log file."""
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as f:
            f.write(self.to_jsonl() + "\n")


class TierEvaluator:
    """Evaluates a single trigger tier according to its rules."""

    def __init__(self, tier_name: str, tier_number: int, combination_logic: str = "and"):
        """
        Initialize tier evaluator.

        Args:
            tier_name: Name of the tier (e.g., "Tier 0: Seasonal Readiness")
            tier_number: Tier number (0, 1, 2, 3)
            combination_logic: How to combine indicators ("and", "or", "majority")
        """
        self.tier_name = tier_name
        self.tier_number = tier_number
        self.combination_logic = combination_logic

    def evaluate(
        self,
        readings: List[IndicatorReading],
        envelope_share: Optional[float] = None,
        cost_loss_verified: bool = False,
        verification_evidence: Optional[str] = None,
    ) -> TierEvaluation:
        """
        Evaluate the tier given indicator readings.

        Args:
            readings: List of indicator readings
            envelope_share: Portion of action envelope for this tier
            cost_loss_verified: Whether cost-loss model has been run
            verification_evidence: Link to verification evidence

        Returns:
            TierEvaluation with status and rationale
        """
        evaluation_time = datetime.utcnow()

        # Check data quality
        all_data_ok = all(r.is_usable() for r in readings)
        has_missing_data = any(r.data_status == DataStatus.MISSING for r in readings)
        has_stale_data = any(r.data_status == DataStatus.STALE for r in readings)

        # Check if any reading requires escalation
        escalation_readings = [r for r in readings if r.requires_escalation()]

        # Evaluate threshold logic
        thresholds_met = [r.is_met() for r in readings]

        if self.combination_logic == "and":
            condition_met = all(thresholds_met) if thresholds_met else False
        elif self.combination_logic == "or":
            condition_met = any(thresholds_met) if thresholds_met else False
        elif self.combination_logic == "majority":
            # At least 2 of 3, or majority of N
            majority = len(readings) // 2 + 1
            condition_met = sum(thresholds_met) >= majority
        else:
            raise ValueError(f"Unknown combination logic: {self.combination_logic}")

        # Determine status and rationale
        if escalation_readings:
            # Missing or stale data that could have triggered
            status = TierStatus.ESCALATION
            rationale = (
                f"ESCALATION: Missing/stale data requires human review. "
                f"Indicators with data quality issues: {[r.indicator_name for r in escalation_readings]}"
            )
            threshold_met = None
            actions_triggered = None
        elif not all_data_ok:
            # Degraded data but can still evaluate
            if condition_met:
                status = TierStatus.ACTIVE
                threshold_met = True
                rationale = (
                    f"ACTIVE (degraded data). Threshold met despite data delay. "
                    f"Degraded indicators: {[r.indicator_name for r in readings if r.data_status == DataStatus.DEGRADED]}"
                )
                actions_triggered = [
                    f"Tier {self.tier_number} action: {self.tier_name}"
                ]
            else:
                status = TierStatus.INACTIVE
                threshold_met = False
                rationale = (
                    f"INACTIVE (degraded data). Threshold not met. "
                    f"Degraded indicators: {[r.indicator_name for r in readings if r.data_status == DataStatus.DEGRADED]}"
                )
                actions_triggered = None
        else:
            # All data OK
            if condition_met:
                status = TierStatus.ACTIVE
                threshold_met = True
                rationale = f"ACTIVE. All thresholds met ({self.combination_logic} logic)."
                actions_triggered = [f"Tier {self.tier_number} action: {self.tier_name}"]
            else:
                status = TierStatus.INACTIVE
                threshold_met = False
                rationale = f"INACTIVE. Thresholds not met ({self.combination_logic} logic)."
                actions_triggered = None

        return TierEvaluation(
            tier_name=self.tier_name,
            tier_number=self.tier_number,
            evaluation_time=evaluation_time,
            readings=readings,
            combination_logic=self.combination_logic,
            status=status,
            threshold_met=threshold_met,
            all_data_ok=all_data_ok,
            has_missing_data=has_missing_data,
            has_stale_data=has_stale_data,
            rationale=rationale,
            actions_triggered=actions_triggered,
            envelope_share=envelope_share,
            cost_loss_verified=cost_loss_verified,
            verification_evidence=verification_evidence,
        )


class SystemEvaluator:
    """Evaluates all trigger tiers and produces system-wide recommendation."""

    def __init__(self):
        """Initialize system evaluator."""
        self.tier_evaluators = {}

    def add_tier(self, tier_number: int, evaluator: TierEvaluator) -> None:
        """Register a tier evaluator."""
        self.tier_evaluators[tier_number] = evaluator

    def evaluate(self, tier_readings: Dict[int, List[IndicatorReading]]) -> SystemEvaluation:
        """
        Evaluate all tiers and produce system recommendation.

        Args:
            tier_readings: Dict mapping tier number to list of indicator readings

        Returns:
            SystemEvaluation with all tier evaluations and system status
        """
        evaluation_time = datetime.utcnow()
        system_eval = SystemEvaluation(evaluation_time=evaluation_time)
        escalations = []

        # Evaluate each tier
        for tier_number in sorted(self.tier_evaluators.keys()):
            if tier_number not in tier_readings:
                escalations.append(
                    f"Tier {tier_number} missing from input (absent tier produces escalation, not silence)"
                )
                continue

            evaluator = self.tier_evaluators[tier_number]
            tier_eval = evaluator.evaluate(tier_readings[tier_number])
            system_eval.tier_evaluations[tier_number] = tier_eval

            if tier_eval.status == TierStatus.ESCALATION:
                escalations.append(f"Tier {tier_number}: {tier_eval.rationale}")

        # Determine highest active tier
        active_tiers = [
            tier_num
            for tier_num, eval in system_eval.tier_evaluations.items()
            if eval.status == TierStatus.ACTIVE
        ]

        if active_tiers:
            system_eval.highest_active_tier = max(active_tiers)
            system_eval.system_status = TierStatus.ACTIVE
            system_eval.overall_rationale = (
                f"Highest tier activated: Tier {system_eval.highest_active_tier}"
            )
        elif escalations:
            system_eval.system_status = TierStatus.ESCALATION
            system_eval.overall_rationale = "System requires human review."
        else:
            system_eval.system_status = TierStatus.INACTIVE
            system_eval.overall_rationale = "All tiers inactive."

        system_eval.escalations = escalations

        return system_eval
