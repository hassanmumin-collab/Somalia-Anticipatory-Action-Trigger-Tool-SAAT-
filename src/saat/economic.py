"""
Economic module: monetised loss estimation through four channels.

**Four channels of economic impact:**

1. **Direct crop loss:** Inundated area × yield × price.
   Duration-driven, not depth-driven. Maize/sesame: ~3-5 days submergence at
   vegetative stage = near-total loss. Sorghum more tolerant. Apply growth-stage
   multiplier; near-harvest crop partially salvageable.

2. **Livestock via RVF and export ban:** Flood mortality modest vs. drought.
   Dominant channel: disease → Gulf import suspension. Livestock exports (Saudi,
   UAE, Oman) are Somalia's largest export earner + primary FX source for Berbera/
   Bosaso. Model as contingent loss: P(outbreak|flood) × P(ban|outbreak) × export
   value × ban duration. **Report conditional loss alongside expected loss.**
   Note: El Niño–RVF association rests on small sample (1997-98, 2006-07).

3. **Second-order irrigation damage:** Canal siltation, embankment breach, barrage
   damage cause NEXT season to underperform. One Deyr flood = two bad harvests.
   Model repair cost + next-season foregone production. **Headline sensitivity:**
   decides whether one-season or two-season shock.

4. **Recovery upside:** Pasture regeneration, improved conception, herd rebuilding
   over 12-18 months. After four failed seasons, this is substantial. **Report on
   separate time axis, do NOT net against immediate caseload** in headline reporting.
   Tool showing only downside will be dismissed by anyone working in pastoral
   livelihoods, and rightly.

Plus: **Food security.** Do NOT predict IPC phase directly from rainfall.
Model transmission channels: production loss, market access disruption, cereal
price response, terms of trade collapse, AWD/cholera burden (leading mortality
channel in flood years independent of food access).

Reference: Section 9 of the build prompt.

PLACEHOLDER ASSUMPTIONS (all null pending Somalia-specific calibration):
- Submergence damage curves
- Second-order yield penalty
- Mitigation effectiveness
- RVF conditional probabilities
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple
from enum import Enum
import numpy as np


class CropType(Enum):
    """Crop types with different flood tolerance."""

    MAIZE = "maize"  # Sensitive: ~3-5 days = near-total loss
    SESAME = "sesame"  # Sensitive: similar to maize
    SORGHUM = "sorghum"  # Tolerant: withstands longer submergence
    RICE = "rice"  # Flooded rice = potential benefit (not loss)


class GrowthStage(Enum):
    """Crop growth stage affecting loss severity."""

    VEGETATIVE = "vegetative"  # Near-total loss from submergence
    FLOWERING = "flowering"  # High loss
    GRAIN_FILL = "grain_fill"  # Moderate loss
    NEAR_HARVEST = "near_harvest"  # Partial salvage possible


@dataclass
class SubmergenceDamageCurve:
    """Duration-driven crop loss curve."""

    crop_type: CropType
    growth_stage: GrowthStage
    critical_duration_days: float  # Days to near-total loss
    loss_fraction_at_duration: Dict[int, float] = field(default_factory=dict)
    # e.g., {1: 0.1, 3: 0.8, 5: 0.95, 10: 0.98}

    # PLACEHOLDER: No published Somalia calibration confirmed
    description: str = "Placeholder shapes from general agronomic tolerance ranges."


@dataclass
class CropLoss:
    """Direct crop loss calculation."""

    crop_type: CropType
    growth_stage: GrowthStage
    inundated_area_hectares: float
    submergence_duration_days: float
    yield_kg_per_hectare: float
    price_usd_per_kg: float

    loss_fraction: Optional[float] = None  # Estimated from damage curve
    economic_loss_usd: Optional[float] = None

    def calculate_loss(self, damage_curve: Optional[SubmergenceDamageCurve] = None) -> float:
        """
        Calculate direct crop loss.

        Loss = inundated_area × yield × price × loss_fraction(duration)

        Args:
            damage_curve: Submergence damage curve (if None, use placeholder)

        Returns:
            Economic loss in USD
        """
        self._validate_inputs()
        if damage_curve is None:
            raise ValueError(
                "A verified submergence damage curve is required; "
                "Somalia-specific curves are not yet calibrated."
            )
        if damage_curve.crop_type != self.crop_type or damage_curve.growth_stage != self.growth_stage:
            raise ValueError("Damage curve crop_type and growth_stage must match the crop loss")
        if not damage_curve.loss_fraction_at_duration:
            raise ValueError("Damage curve must define at least one duration/loss point")

        durations = np.asarray(sorted(damage_curve.loss_fraction_at_duration), dtype=float)
        losses = np.asarray(
            [damage_curve.loss_fraction_at_duration[int(duration)] for duration in durations],
            dtype=float,
        )
        if np.any((losses < 0) | (losses > 1)) or np.any(np.diff(losses) < 0):
            raise ValueError("Damage curve loss fractions must be monotonic values in [0, 1]")
        self.loss_fraction = float(
            np.interp(self.submergence_duration_days, durations, losses, left=0.0, right=losses[-1])
        )

        total_production_usd = (
            self.inundated_area_hectares * self.yield_kg_per_hectare * self.price_usd_per_kg
        )
        self.economic_loss_usd = total_production_usd * self.loss_fraction

        return self.economic_loss_usd

    def _validate_inputs(self) -> None:
        """Reject invalid physical and monetary inputs before calculation."""
        values = (
            self.inundated_area_hectares,
            self.submergence_duration_days,
            self.yield_kg_per_hectare,
            self.price_usd_per_kg,
        )
        if not all(np.isfinite(value) and value >= 0 for value in values):
            raise ValueError("Crop loss inputs must be finite and non-negative")


@dataclass
class LivestockRVFLoss:
    """RVF and export ban contingent loss."""

    livestock_type: str  # "cattle", "goats", "sheep"
    monthly_export_value_usd: float
    p_outbreak_given_flood: float  # P(RVF outbreak | flood)
    p_ban_given_outbreak: float  # P(export ban | RVF outbreak)
    expected_ban_duration_months: float
    survival_rate_if_outbreak: float = 0.95  # Direct mortality

    # PLACEHOLDER: Rest on small sample (1997-98, 2006-07)
    # No Somalia-specific calibration confirmed
    description: str = "Conditional probabilities poorly constrained."

    def __post_init__(self) -> None:
        """Validate probabilities and non-negative monetary inputs."""
        if not 0 <= self.p_outbreak_given_flood <= 1:
            raise ValueError("p_outbreak_given_flood must be in [0, 1]")
        if not 0 <= self.p_ban_given_outbreak <= 1:
            raise ValueError("p_ban_given_outbreak must be in [0, 1]")
        if not 0 <= self.survival_rate_if_outbreak <= 1:
            raise ValueError("survival_rate_if_outbreak must be in [0, 1]")
        if self.monthly_export_value_usd < 0 or self.expected_ban_duration_months < 0:
            raise ValueError("Export value and ban duration must be non-negative")

    def calculate_expected_loss(self) -> float:
        """
        Calculate expected loss from RVF/export ban.

        E[loss] = P(outbreak|flood) × P(ban|outbreak) × monthly_export × ban_months

        Returns:
            Expected economic loss in USD
        """
        return (
            self.p_outbreak_given_flood
            * self.p_ban_given_outbreak
            * self.monthly_export_value_usd
            * self.expected_ban_duration_months
        )

    def calculate_conditional_loss(self) -> float:
        """
        Calculate conditional loss given outbreak occurs.

        Returns:
            Loss conditional on RVF outbreak (used for decision analysis)
        """
        return (
            self.p_ban_given_outbreak
            * self.monthly_export_value_usd
            * self.expected_ban_duration_months
        )


@dataclass
class SecondOrderIrrigationDamage:
    """Damage to irrigation infrastructure affecting next season."""

    canal_length_km: float
    canal_desilting_cost_per_km_usd: float
    embankment_repair_cost_usd: float
    barrage_damage_fraction: float  # 0-1

    # Next season impact
    irrigated_area_hectares_next: float
    yield_loss_fraction_next_season: float  # Foregone production
    yield_kg_per_hectare: float
    price_usd_per_kg: float

    # PLACEHOLDER: No published Somalia estimate confirmed
    description: str = "Placeholder. Headline sensitivity: decides 1-season vs 2-season shock."

    def __post_init__(self) -> None:
        """Validate fractions and non-negative cost inputs."""
        if not 0 <= self.barrage_damage_fraction <= 1:
            raise ValueError("barrage_damage_fraction must be in [0, 1]")
        if not 0 <= self.yield_loss_fraction_next_season <= 1:
            raise ValueError("yield_loss_fraction_next_season must be in [0, 1]")
        values = (
            self.canal_length_km,
            self.canal_desilting_cost_per_km_usd,
            self.embankment_repair_cost_usd,
            self.irrigated_area_hectares_next,
            self.yield_kg_per_hectare,
            self.price_usd_per_kg,
        )
        if not all(np.isfinite(value) and value >= 0 for value in values):
            raise ValueError("Irrigation damage inputs must be finite and non-negative")

    def calculate_repair_cost(self) -> float:
        """Calculate infrastructure repair cost."""
        canal_cost = self.canal_length_km * self.canal_desilting_cost_per_km_usd
        barrage_cost = self.barrage_damage_fraction * self.embankment_repair_cost_usd
        return canal_cost + barrage_cost

    def calculate_next_season_foregone_production(self) -> float:
        """Calculate forgone production in next season."""
        total_next_production = (
            self.irrigated_area_hectares_next
            * self.yield_kg_per_hectare
            * self.price_usd_per_kg
        )
        foregone = total_next_production * self.yield_loss_fraction_next_season
        return foregone

    def calculate_total_second_order_cost(self) -> float:
        """Calculate total repair + foregone production."""
        repair = self.calculate_repair_cost()
        foregone = self.calculate_next_season_foregone_production()
        return repair + foregone


@dataclass
class RecoveryUpside:
    """Recovery and rebuilding upside after flood."""

    # Required scenario inputs
    pasture_recovery_gain_fraction: float  # Improvement vs. pre-flood baseline
    breeding_rate_improvement_percent: float  # % improvement in conception rates
    post_flood_herd_size: int
    next_season_yield_improvement_fraction: float  # If rains normal
    # Optional timing and context
    recovery_months: int = 12
    grazing_area_hectares: Optional[float] = None  # For context
    recovery_timeline_months: int = 18

    # PLACEHOLDER: Judgemental. Not netted against immediate caseload.
    description: str = (
        "Substantial after four failed seasons. Report on separate time axis. "
        "Do NOT net against immediate caseload in headline reporting."
    )

    def __post_init__(self) -> None:
        """Validate recovery parameters."""
        if not 0 <= self.pasture_recovery_gain_fraction:
            raise ValueError("pasture_recovery_gain_fraction must be non-negative")
        if self.breeding_rate_improvement_percent < 0:
            raise ValueError("breeding_rate_improvement_percent must be non-negative")
        if self.post_flood_herd_size < 0 or self.next_season_yield_improvement_fraction < 0:
            raise ValueError("Recovery quantities must be non-negative")

    def calculate_recovery_benefit(self, baseline_herd_productivity: float) -> float:
        """
        Calculate herd recovery benefit.

        Args:
            baseline_herd_productivity: Baseline kg per animal per year

        Returns:
            Recovery gain in kg (or USD equivalent)
        """
        # Simplified: improved conception rates lead to larger herd after 12-18 months
        herd_size_gain = self.post_flood_herd_size * (self.breeding_rate_improvement_percent / 100)
        gain_kg = herd_size_gain * baseline_herd_productivity * (self.recovery_timeline_months / 12)
        return gain_kg


@dataclass
class FoodSecurityTransmission:
    """Food security impact through market and livelihood channels."""

    # Production loss (direct)
    production_loss_fraction: float

    # Market access disruption
    # When roads cut and Baidoa/Belet Weyne isolate
    market_access_loss_fraction: float

    # Cereal price response
    baseline_cereal_price_usd_per_kg: float
    price_elasticity_supply: float  # How much price rises per % production loss
    expected_price_spike_fraction: float

    # Terms of trade collapse
    baseline_tot: float  # Goat-to-cereal exchange rate
    tot_elasticity: float
    expected_tot_decline_fraction: float

    # AWD/cholera burden (independent of food access)
    awd_mortality_rate: float  # Deaths per 1000
    at_risk_population: int
    treatment_cost_per_case_usd: float

    def calculate_food_insecurity_progression(self) -> Dict[str, float]:
        """
        Model transmission channels to IPC phase.

        Do NOT predict IPC directly. Model channels:
        - Production loss
        - Market disruption
        - Cereal price response
        - Terms of trade collapse
        - AWD/cholera burden

        Returns:
            Estimates of impact on each transmission channel
        """
        fractions = (
            self.production_loss_fraction,
            self.market_access_loss_fraction,
            self.expected_price_spike_fraction,
            self.expected_tot_decline_fraction,
        )
        if not all(0 <= value <= 1 for value in fractions):
            raise ValueError("Food-security loss and response fractions must be in [0, 1]")
        if self.at_risk_population < 0 or self.treatment_cost_per_case_usd < 0:
            raise ValueError("Population and treatment cost must be non-negative")
        return {
            "production_loss_fraction": self.production_loss_fraction,
            "market_access_disruption_fraction": self.market_access_loss_fraction,
            "cereal_price_spike_fraction": self.expected_price_spike_fraction,
            "cereal_price_usd_per_kg": self.baseline_cereal_price_usd_per_kg
            * (1 + self.expected_price_spike_fraction),
            "terms_of_trade_decline_fraction": self.expected_tot_decline_fraction,
            "terms_of_trade": self.baseline_tot * (1 - self.expected_tot_decline_fraction),
            "awd_expected_deaths": self.at_risk_population * self.awd_mortality_rate / 1000,
            "awd_treatment_cost_usd": self.at_risk_population
            * self.awd_mortality_rate
            / 1000
            * self.treatment_cost_per_case_usd,
        }


@dataclass
class EconomicLossSummary:
    """Complete economic loss summary."""

    event_date: str
    direct_crop_loss_usd: float
    livestock_rvf_expected_loss_usd: float
    livestock_rvf_conditional_loss_usd: Optional[float]
    second_order_damage_usd: float
    recovery_upside_usd: Optional[float]
    food_security_impact: Dict[str, float]

    def total_expected_loss(self, include_recovery: bool = False) -> float:
        """
        Calculate total expected loss.

        Args:
            include_recovery: If False, net recovery upside. If True, report separately.

        Returns:
            Total economic loss (USD)
        """
        total = (
            self.direct_crop_loss_usd
            + self.livestock_rvf_expected_loss_usd
            + self.second_order_damage_usd
        )

        # Recovery is an upside on a separate time axis and is never netted into
        # the immediate loss headline.

        return total

    def headline_report(self) -> str:
        """
        Generate headline loss report.

        Report conditional RVF loss separately (low prob, high consequence).
        Report recovery on separate time axis.
        Report food security channels separately from direct losses.

        Returns:
            Formatted report string
        """
        immediate = self.total_expected_loss(include_recovery=False)
        lines = [
            f"Economic loss summary for {self.event_date}",
            f"Immediate expected loss (USD): {immediate:,.2f}",
            f"  Direct crop loss (USD): {self.direct_crop_loss_usd:,.2f}",
            f"  RVF/export-ban expected loss (USD): {self.livestock_rvf_expected_loss_usd:,.2f}",
            f"  Second-order irrigation damage (USD): {self.second_order_damage_usd:,.2f}",
        ]
        if self.livestock_rvf_conditional_loss_usd is not None:
            lines.append(
                f"  RVF/export-ban conditional loss (USD): "
                f"{self.livestock_rvf_conditional_loss_usd:,.2f}"
            )
        if self.recovery_upside_usd is not None:
            lines.append(f"Recovery upside, reported separately (USD): {self.recovery_upside_usd:,.2f}")
        for channel, value in self.food_security_impact.items():
            lines.append(f"Food-security {channel}: {value:,.2f}")
        return "\n".join(lines)
