"""
Cost-loss decision model for trigger verification.

Implements the economic value calculation for trigger thresholds.
This is the core of the project: a trigger is a decision rule whose quality
is whether acting on it beats both trivial alternatives: always act and never act.

Reference: Section 4 of the build prompt.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
from enum import Enum


class DataStatus(Enum):
    """Data quality status for trigger evaluation."""

    OK = "OK"
    DEGRADED = "DEGRADED"
    MISSING = "MISSING"
    STALE = "STALE"


@dataclass
class ContingencyMetrics:
    """Contingency table metrics for forecast evaluation."""

    hits: int
    false_alarms: int
    misses: int
    correct_negatives: int

    @property
    def pod(self) -> float:
        """Probability of Detection: hits / (hits + misses)."""
        denominator = self.hits + self.misses
        if denominator == 0:
            return np.nan
        return self.hits / denominator

    @property
    def pofd(self) -> float:
        """Probability of False Detection: false_alarms / (false_alarms + correct_negatives)."""
        denominator = self.false_alarms + self.correct_negatives
        if denominator == 0:
            return np.nan
        return self.false_alarms / denominator

    @property
    def far(self) -> float:
        """False Alarm Ratio: false_alarms / (hits + false_alarms)."""
        denominator = self.hits + self.false_alarms
        if denominator == 0:
            return np.nan
        return self.false_alarms / denominator

    @property
    def csi(self) -> float:
        """Critical Success Index: hits / (hits + false_alarms + misses)."""
        denominator = self.hits + self.false_alarms + self.misses
        if denominator == 0:
            return np.nan
        return self.hits / denominator

    @property
    def pss(self) -> float:
        """Peirce Skill Score (True Skill Statistic): POD - POFD."""
        return self.pod - self.pofd

    @property
    def frequency_bias(self) -> float:
        """Frequency Bias: (hits + false_alarms) / (hits + misses)."""
        denominator = self.hits + self.misses
        if denominator == 0:
            return np.nan
        return (self.hits + self.false_alarms) / denominator

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ContingencyMetrics(hits={self.hits}, fa={self.false_alarms}, "
            f"misses={self.misses}, cn={self.correct_negatives}, "
            f"POD={self.pod:.3f}, FAR={self.far:.3f}, PSS={self.pss:.3f})"
        )


@dataclass
class CostLossParameters:
    """Parameters for the cost-loss decision model."""

    cost_action: float  # C: cost of taking action
    loss_event: float  # L: loss if event occurs unmitigated
    mitigation_effectiveness: float  # f: fraction of loss avoided by correct early action
    climatological_base_rate: float  # s: climatological probability of event

    def validate(self) -> Tuple[bool, Optional[str]]:
        """
        Validate parameters for feasibility.

        Returns:
            (is_feasible, error_message)
        """
        if self.cost_action < 0:
            return False, "cost_action must be non-negative"
        if self.loss_event < 0:
            return False, "loss_event must be non-negative"
        if not 0 <= self.mitigation_effectiveness <= 1:
            return False, "mitigation_effectiveness must be in [0, 1]"
        if not 0 <= self.climatological_base_rate <= 1:
            return False, "climatological_base_rate must be in [0, 1]"

        # Critical feasibility check from build prompt
        if self.cost_action / self.loss_event >= self.mitigation_effectiveness:
            return (
                False,
                (
                    f"INFEASIBLE: C/L ({self.cost_action/self.loss_event:.3f}) >= f "
                    f"({self.mitigation_effectiveness}). No threshold can have positive value. "
                    f"The problem is intervention design, not the trigger."
                ),
            )

        return True, None

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"CostLossParameters(C={self.cost_action}, L={self.loss_event}, "
            f"f={self.mitigation_effectiveness}, s={self.climatological_base_rate})"
        )


@dataclass
class DecisionOutcome:
    """Expected expense for a decision strategy."""

    threshold: Optional[float]
    expected_expense: float
    pod: float
    far: float
    pss: float
    relative_economic_value: float
    contingency: ContingencyMetrics

    def is_feasible_for_constraint(self, min_pod: Optional[float], max_far: Optional[float]) -> bool:
        """Check if this outcome meets operational constraints."""
        if min_pod is not None and (not np.isfinite(self.pod) or self.pod < min_pod):
            return False
        if max_far is not None and (not np.isfinite(self.far) or self.far > max_far):
            return False
        return True

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"DecisionOutcome(threshold={self.threshold:.4f}, "
            f"expense={self.expected_expense:.2e}, V={self.relative_economic_value:.3f}, "
            f"POD={self.pod:.3f}, FAR={self.far:.3f})"
        )


class CostLossModel:
    """Cost-loss decision model for trigger verification."""

    def __init__(self, params: CostLossParameters):
        """
        Initialize model.

        Args:
            params: Cost-loss parameters

        Raises:
            ValueError: If parameters are infeasible
        """
        is_feasible, error = params.validate()
        if not is_feasible:
            raise ValueError(error)
        self.params = params

    def _expected_expense_always_act(self) -> float:
        """Expected expense if always acting."""
        C = self.params.cost_action
        L = self.params.loss_event
        f = self.params.mitigation_effectiveness
        s = self.params.climatological_base_rate
        return C + (1 - f) * s * L

    def _expected_expense_never_act(self) -> float:
        """Expected expense if never acting."""
        L = self.params.loss_event
        s = self.params.climatological_base_rate
        return s * L

    def _expected_expense_perfect(self) -> float:
        """Expected expense for perfect forecast."""
        C = self.params.cost_action
        L = self.params.loss_event
        f = self.params.mitigation_effectiveness
        s = self.params.climatological_base_rate
        return s * (C + (1 - f) * L)

    def expected_expense_forecast(self, metrics: ContingencyMetrics) -> float:
        """
        Calculate expected expense per forecast opportunity for a given forecast.

        E_forecast = (hits + false_alarms)*C + hits*(1-f)*L + misses*L

        The contingency counts are converted to *rates* (fractions of the total
        number of forecast opportunities) before applying the formula, so the
        result is on the same per-opportunity scale as always/never/perfect act.
        This is what makes the spec's identity hold: for a perfect forecast
        hits -> s, misses -> 0, false_alarms -> 0, so E_forecast -> E_perfect.
        Dividing every candidate's expense by the same constant N leaves the
        threshold search (an argmin) unchanged.
        """
        C = self.params.cost_action
        L = self.params.loss_event
        f = self.params.mitigation_effectiveness

        n = metrics.hits + metrics.false_alarms + metrics.misses + metrics.correct_negatives
        if n == 0:
            raise ValueError("Contingency table is empty; cannot compute expected expense")

        hit_rate = metrics.hits / n
        false_alarm_rate = metrics.false_alarms / n
        miss_rate = metrics.misses / n

        return (hit_rate + false_alarm_rate) * C + hit_rate * (1 - f) * L + miss_rate * L

    def relative_economic_value(self, metrics: ContingencyMetrics) -> float:
        """
        Calculate relative economic value of forecast.

        V = (E_reference - E_forecast) / (E_reference - E_perfect)
        where E_reference = min(always_act, never_act)

        V = 1: perfect forecast
        V = 0: adds nothing over best trivial strategy
        V < 0: destroys value
        """
        E_always = self._expected_expense_always_act()
        E_never = self._expected_expense_never_act()
        E_reference = min(E_always, E_never)

        E_forecast = self.expected_expense_forecast(metrics)
        E_perfect = self._expected_expense_perfect()

        if E_reference == E_perfect:
            # Perfect forecast equals reference: no room for improvement
            return np.nan

        return (E_reference - E_forecast) / (E_reference - E_perfect)

    def optimize_threshold(
        self,
        observations: np.ndarray,
        forecasts: np.ndarray,
        min_pod: Optional[float] = None,
        max_far: Optional[float] = None,
    ) -> DecisionOutcome:
        """
        Find optimal threshold by minimizing expected expense.

        Args:
            observations: 1D array, 1 if event occurred, 0 otherwise
            forecasts: 1D array of forecast values
            min_pod: Minimum required Probability of Detection
            max_far: Maximum allowed False Alarm Ratio

        Returns:
            DecisionOutcome with optimal threshold and metrics

        Raises:
            ValueError: If no threshold meets constraints
        """
        if len(observations) != len(forecasts):
            raise ValueError("observations and forecasts must have same length")

        if len(observations) == 0:
            raise ValueError("observations and forecasts cannot be empty")

        # Check for valid observations
        unique_obs = np.unique(observations)
        if not all(o in [0, 1] for o in unique_obs):
            raise ValueError("observations must be binary (0 or 1)")

        # Generate candidate thresholds
        thresholds = np.unique(forecasts)
        thresholds = np.sort(thresholds)[::-1]  # High to low

        best_outcome = None
        best_expense = np.inf

        for threshold in thresholds:
            predicted = (forecasts >= threshold).astype(int)

            # Build contingency table
            hits = np.sum((predicted == 1) & (observations == 1))
            false_alarms = np.sum((predicted == 1) & (observations == 0))
            misses = np.sum((predicted == 0) & (observations == 1))
            correct_negatives = np.sum((predicted == 0) & (observations == 0))

            contingency = ContingencyMetrics(
                hits=int(hits),
                false_alarms=int(false_alarms),
                misses=int(misses),
                correct_negatives=int(correct_negatives),
            )

            expense = self.expected_expense_forecast(contingency)
            rel_value = self.relative_economic_value(contingency)

            outcome = DecisionOutcome(
                threshold=float(threshold),
                expected_expense=expense,
                pod=contingency.pod,
                far=contingency.far,
                pss=contingency.pss,
                relative_economic_value=rel_value,
                contingency=contingency,
            )

            # Check constraints
            if not outcome.is_feasible_for_constraint(min_pod, max_far):
                continue

            # Track best by expected expense
            if expense < best_expense:
                best_expense = expense
                best_outcome = outcome

        if best_outcome is None:
            constraint_desc = []
            if min_pod is not None:
                constraint_desc.append(f"POD >= {min_pod}")
            if max_far is not None:
                constraint_desc.append(f"FAR <= {max_far}")
            raise ValueError(
                f"No threshold meets operational constraints: {', '.join(constraint_desc)}. "
                f"Forecast is not skilful enough at this lead time."
            )

        return best_outcome

    def sweep_thresholds(
        self,
        observations: np.ndarray,
        forecasts: np.ndarray,
    ) -> list[DecisionOutcome]:
        """
        Sweep all thresholds and return outcomes sorted by economic value.

        Args:
            observations: 1D array, 1 if event occurred, 0 otherwise
            forecasts: 1D array of forecast values

        Returns:
            List of DecisionOutcome sorted by relative_economic_value (descending)
        """
        outcomes = []
        thresholds = np.unique(forecasts)
        thresholds = np.sort(thresholds)[::-1]  # High to low

        for threshold in thresholds:
            predicted = (forecasts >= threshold).astype(int)

            hits = np.sum((predicted == 1) & (observations == 1))
            false_alarms = np.sum((predicted == 1) & (observations == 0))
            misses = np.sum((predicted == 0) & (observations == 1))
            correct_negatives = np.sum((predicted == 0) & (observations == 0))

            contingency = ContingencyMetrics(
                hits=int(hits),
                false_alarms=int(false_alarms),
                misses=int(misses),
                correct_negatives=int(correct_negatives),
            )

            expense = self.expected_expense_forecast(contingency)
            rel_value = self.relative_economic_value(contingency)

            outcome = DecisionOutcome(
                threshold=float(threshold),
                expected_expense=expense,
                pod=contingency.pod,
                far=contingency.far,
                pss=contingency.pss,
                relative_economic_value=rel_value,
                contingency=contingency,
            )
            outcomes.append(outcome)

        # Sort by relative economic value (descending)
        outcomes.sort(key=lambda x: (np.isnan(x.relative_economic_value), -x.relative_economic_value))
        return outcomes
