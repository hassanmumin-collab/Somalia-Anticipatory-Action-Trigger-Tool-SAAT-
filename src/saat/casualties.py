"""
Casualties module: expected-death modelling for two flood settings.

Two distinct causal pathways, deliberately modelled separately rather than as
one generic "flood mortality" rate:

1. **Urban pluvial (Mogadishu).** Poor drainage lets rainfall pond and flow
   through streets and compounds instead of routing to the sea. The dominant
   causes of death are (a) drowning in flowing or ponded water, and (b)
   electrocution from naked/exposed low-voltage wiring and downed lines that
   floodwater brings into contact with pedestrians and waders -- a hazard
   specific to unplanned/informal electrification, with no riverine
   equivalent (riverine towns have far lower grid density).

2. **Riverine (Shabelle/Juba towns: Belet Weyne, Jowhar, Doolow, ...).**
   Drowning dominates. Mortality is governed by depth and, critically, by
   warning lead time -- the entire argument for `hazard.py`'s routing lag is
   that lead time saves lives here, not just money.

Both pathways use an explicit, externally supplied mortality curve, by
analogy with `economic.CropLoss`'s submergence damage curve: there is no
Somalia-specific calibration, so a hidden default would misrepresent
confidence. Run any of these as a range across plausible curves, not a point
estimate, until local mortality data (MOH, WHO EWARS, DMS) exists.

Reference: Section 9 of the build prompt (impact modelling).

PLACEHOLDER ASSUMPTIONS (all pending Somalia-specific calibration):
- Depth-mortality curves for both drowning settings
- Electrocution contact-fatality rate
- Warning-lead-time mortality mitigation slope
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import numpy as np


class FloodSetting(Enum):
    """Flood setting: governs which mortality curve and pathways apply."""

    URBAN_PLUVIAL = "urban_pluvial"  # Mogadishu: ponded/flowing street water
    RIVERINE = "riverine"  # Shabelle/Juba overbank flooding


@dataclass
class DrowningRiskCurve:
    """Depth-driven drowning case-fatality curve for one flood setting."""

    setting: FloodSetting
    mortality_fraction_at_depth_m: Dict[float, float] = field(default_factory=dict)
    # e.g. {0.3: 0.001, 1.0: 0.01, 2.0: 0.05, 3.0: 0.15}

    # PLACEHOLDER: no published Somalia-specific depth-mortality calibration
    description: str = "Placeholder shape from general flood-mortality literature."

    def interpolate(self, water_depth_m: float) -> float:
        """
        Interpolate case-fatality fraction at a given water depth.

        Below the shallowest calibration point returns 0 (no drowning risk
        modelled); above the deepest, holds at the deepest known rate rather
        than extrapolating unboundedly.

        Args:
            water_depth_m: Standing/flowing water depth (m)

        Returns:
            Case-fatality fraction in [0, 1]
        """
        if not self.mortality_fraction_at_depth_m:
            raise ValueError("Drowning risk curve must define at least one depth/mortality point")
        if water_depth_m < 0:
            raise ValueError("water_depth_m must be non-negative")

        depths = np.asarray(sorted(self.mortality_fraction_at_depth_m), dtype=float)
        rates = np.asarray(
            [self.mortality_fraction_at_depth_m[depth] for depth in sorted(self.mortality_fraction_at_depth_m)],
            dtype=float,
        )
        if np.any((rates < 0) | (rates > 1)) or np.any(np.diff(rates) < 0):
            raise ValueError("Drowning risk curve mortality fractions must be monotonic values in [0, 1]")
        return float(np.interp(water_depth_m, depths, rates, left=0.0, right=rates[-1]))


@dataclass
class DrowningExposure:
    """Population exposed to drowning risk, with warning lead-time mitigation."""

    setting: FloodSetting
    population_exposed: float
    water_depth_m: float
    warning_lead_time_hours: float = 0.0
    # Fraction of baseline mortality averted per hour of lead time; capped by
    # max_lead_time_mitigation_fraction because the least mobile residents
    # (elderly, disabled, those without transport) cannot evacuate regardless
    # of how much notice they get.
    lead_time_mitigation_fraction_per_hour: float = 0.05
    max_lead_time_mitigation_fraction: float = 0.8

    mortality_fraction: Optional[float] = None
    expected_deaths: Optional[float] = None

    # PLACEHOLDER: judgemental mitigation slope, no Somalia-specific
    # evacuation-compliance data
    description: str = "Lead-time mitigation slope is judgemental, not calibrated."

    def __post_init__(self) -> None:
        """Validate exposure and mitigation inputs."""
        if self.population_exposed < 0:
            raise ValueError("population_exposed must be non-negative")
        if self.water_depth_m < 0:
            raise ValueError("water_depth_m must be non-negative")
        if self.warning_lead_time_hours < 0:
            raise ValueError("warning_lead_time_hours must be non-negative")
        if not 0 <= self.lead_time_mitigation_fraction_per_hour <= 1:
            raise ValueError("lead_time_mitigation_fraction_per_hour must be in [0, 1]")
        if not 0 <= self.max_lead_time_mitigation_fraction <= 1:
            raise ValueError("max_lead_time_mitigation_fraction must be in [0, 1]")

    def calculate_expected_deaths(self, curve: DrowningRiskCurve) -> float:
        """
        Calculate expected drowning deaths.

        E[deaths] = population_exposed * mortality(depth) * (1 - lead_time_mitigation)

        Args:
            curve: Depth-mortality curve for this exposure's flood setting

        Returns:
            Expected deaths (float; report as a range across plausible curves)
        """
        if curve.setting != self.setting:
            raise ValueError(
                f"Drowning risk curve setting ({curve.setting}) does not match "
                f"exposure setting ({self.setting})"
            )
        base_mortality = curve.interpolate(self.water_depth_m)
        mitigation = min(
            self.warning_lead_time_hours * self.lead_time_mitigation_fraction_per_hour,
            self.max_lead_time_mitigation_fraction,
        )
        self.mortality_fraction = base_mortality * (1 - mitigation)
        self.expected_deaths = self.population_exposed * self.mortality_fraction
        return self.expected_deaths


@dataclass
class ElectrocutionExposure:
    """
    Electrocution risk from naked/exposed wiring in contact with floodwater.

    Urban-specific: unplanned/informal low-voltage distribution, exposed
    splices, and downed lines are a Mogadishu drainage-flood hazard.
    """

    population_in_contact: float  # Wading/contact population in the affected area
    exposed_wiring_prevalence: float  # 0-1: fraction of flooded area with exposed/naked wiring
    contact_fatality_rate: float  # P(death | contact with electrified floodwater)

    expected_deaths: Optional[float] = None

    # PLACEHOLDER: no published Somalia-specific electrocution mortality rate
    # from urban flood contact; treat as a range, not a point estimate
    description: str = "No Somalia-specific electrocution case-fatality rate confirmed."

    def __post_init__(self) -> None:
        """Validate probabilities and non-negative population."""
        if self.population_in_contact < 0:
            raise ValueError("population_in_contact must be non-negative")
        if not 0 <= self.exposed_wiring_prevalence <= 1:
            raise ValueError("exposed_wiring_prevalence must be in [0, 1]")
        if not 0 <= self.contact_fatality_rate <= 1:
            raise ValueError("contact_fatality_rate must be in [0, 1]")

    def calculate_expected_deaths(self) -> float:
        """
        Calculate expected electrocution deaths.

        E[deaths] = population_in_contact * exposed_wiring_prevalence * contact_fatality_rate

        Returns:
            Expected deaths (float)
        """
        self.expected_deaths = (
            self.population_in_contact * self.exposed_wiring_prevalence * self.contact_fatality_rate
        )
        return self.expected_deaths


@dataclass
class UrbanFloodCasualties:
    """
    Combined urban pluvial casualty estimate for one location (default Mogadishu).

    Drowning and electrocution are treated as additive expected deaths over
    the exposed population. This over-counts to the extent the same
    individuals are at risk from both pathways at once; treat the sum as an
    upper-bound approximation appropriate for rare, low-probability risks,
    not a precise joint estimate.
    """

    location: str
    drowning: DrowningExposure
    electrocution: ElectrocutionExposure

    def __post_init__(self) -> None:
        """Reject a riverine exposure attached to an urban casualty estimate."""
        if self.drowning.setting != FloodSetting.URBAN_PLUVIAL:
            raise ValueError("UrbanFloodCasualties requires a URBAN_PLUVIAL drowning exposure")

    def total_expected_deaths(self, drowning_curve: DrowningRiskCurve) -> float:
        """Sum drowning and electrocution expected deaths."""
        return self.drowning.calculate_expected_deaths(drowning_curve) + self.electrocution.calculate_expected_deaths()

    def headline_report(self, drowning_curve: DrowningRiskCurve) -> str:
        """Generate a headline report for this location."""
        total = self.total_expected_deaths(drowning_curve)
        return "\n".join(
            [
                f"Urban pluvial flood casualties -- {self.location}",
                f"  Total expected deaths: {total:,.1f}",
                f"  Drowning (ponded/flowing street water): {self.drowning.expected_deaths:,.1f}",
                f"  Electrocution (exposed/naked wiring): {self.electrocution.expected_deaths:,.1f}",
            ]
        )


@dataclass
class RiverineFloodCasualties:
    """
    Riverine drowning casualty estimate for one gauge town.

    `secondary_cause_multiplier` is a scenario parameter (default 1.0,
    neutral) exposing additional causes -- building collapse, snakebite,
    early waterborne-disease onset -- that are not modelled explicitly here.
    Running with the neutral default is itself a documented decision, by
    analogy with `displacement.vulnerability_multiplier`.
    """

    location: str
    drowning: DrowningExposure
    secondary_cause_multiplier: float = 1.0

    def __post_init__(self) -> None:
        """Reject an urban exposure attached to a riverine casualty estimate."""
        if self.drowning.setting != FloodSetting.RIVERINE:
            raise ValueError("RiverineFloodCasualties requires a RIVERINE drowning exposure")
        if self.secondary_cause_multiplier < 0:
            raise ValueError("secondary_cause_multiplier must be non-negative")

    def calculate_expected_deaths(self, drowning_curve: DrowningRiskCurve) -> float:
        """Drowning deaths scaled by the secondary-cause multiplier."""
        return self.drowning.calculate_expected_deaths(drowning_curve) * self.secondary_cause_multiplier

    def headline_report(self, drowning_curve: DrowningRiskCurve) -> str:
        """Generate a headline report for this location."""
        total = self.calculate_expected_deaths(drowning_curve)
        return "\n".join(
            [
                f"Riverine flood casualties -- {self.location}",
                f"  Total expected deaths (secondary-cause x{self.secondary_cause_multiplier:.2f}): {total:,.1f}",
                f"  Drowning at base rate: {self.drowning.expected_deaths:,.1f}",
                f"  Warning lead time: {self.drowning.warning_lead_time_hours:.0f}h",
            ]
        )


@dataclass
class CasualtySummary:
    """Complete expected-casualty summary across urban and riverine locations."""

    event_date: str
    urban: List[UrbanFloodCasualties] = field(default_factory=list)
    riverine: List[RiverineFloodCasualties] = field(default_factory=list)

    def total_expected_deaths(
        self, urban_curve: DrowningRiskCurve, riverine_curve: DrowningRiskCurve
    ) -> float:
        """Sum expected deaths across every urban and riverine location."""
        urban_total = sum(location.total_expected_deaths(urban_curve) for location in self.urban)
        riverine_total = sum(location.calculate_expected_deaths(riverine_curve) for location in self.riverine)
        return urban_total + riverine_total

    def headline_report(self, urban_curve: DrowningRiskCurve, riverine_curve: DrowningRiskCurve) -> str:
        """Generate a headline casualty report across all locations."""
        total = self.total_expected_deaths(urban_curve, riverine_curve)
        lines = [
            f"Expected-casualty summary for {self.event_date}",
            f"Total expected deaths (all locations): {total:,.1f}",
            "",
        ]
        for location in self.urban:
            lines.append(location.headline_report(urban_curve))
            lines.append("")
        for location in self.riverine:
            lines.append(location.headline_report(riverine_curve))
            lines.append("")
        return "\n".join(lines).rstrip()
