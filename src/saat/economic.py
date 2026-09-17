"""
Economic module: monetised agricultural loss in riverine flood zones.

Scope is deliberately narrow: the direct and second-order cost of flooding to
riverine crop agriculture (Shabelle/Juba). Urban productivity loss is modelled
separately in `saat.urban_flood`; casualties in `saat.casualties`.

**Two channels of economic impact:**

1. **Direct crop loss:** Inundated area × yield × price.
   Duration-driven, not depth-driven. Maize/sesame: ~3-5 days submergence at
   vegetative stage = near-total loss. Sorghum more tolerant. Apply growth-stage
   multiplier; near-harvest crop partially salvageable.

2. **Second-order irrigation damage:** Canal siltation, embankment breach, barrage
   damage cause NEXT season to underperform. One Deyr flood = two bad harvests.
   Model repair cost + next-season foregone production. **Headline sensitivity:**
   decides whether one-season or two-season shock.

Reference: Section 9 of the build prompt.

PLACEHOLDER ASSUMPTIONS (all null pending Somalia-specific calibration):
- Submergence damage curves
- Second-order yield penalty
"""

from dataclasses import dataclass, field
from typing import Optional, Dict
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
class EconomicLossSummary:
    """Riverine agricultural loss summary: direct crop loss + second-order damage."""

    event_date: str
    direct_crop_loss_usd: float
    second_order_damage_usd: float

    def total_expected_loss(self) -> float:
        """
        Calculate total expected agricultural loss.

        Returns:
            Total economic loss (USD)
        """
        return self.direct_crop_loss_usd + self.second_order_damage_usd

    def headline_report(self) -> str:
        """
        Generate headline loss report.

        Returns:
            Formatted report string
        """
        total = self.total_expected_loss()
        return "\n".join(
            [
                f"Agricultural loss summary for {self.event_date}",
                f"Total expected loss (USD): {total:,.2f}",
                f"  Direct crop loss (USD): {self.direct_crop_loss_usd:,.2f}",
                f"  Second-order irrigation damage (USD): {self.second_order_damage_usd:,.2f}",
            ]
        )
