"""
Urban flood module: Mogadishu productivity loss from pluvial flooding.

This is the hardest of the four impact channels to model credibly, and is
kept deliberately separate from `economic.py` (riverine agriculture) because
the mechanism is different: urban pluvial flooding does not destroy a crop,
it **interrupts movement and trade** by ponding stagnant water on major
arterial roads (Airport Road / Aden Adde corridor, Maka Al Mukarama Road,
KM4-KM5 junction, Afgooye Road) and flooding market premises.

**Two channels:**

1. **Road-network disruption.** A blocked or degraded arterial road stops or
   slows the flow of goods and people. Traffic that cannot be rerouted loses
   its full value for the closure duration; traffic that reroutes only pays
   the extra detour cost; traffic on a merely degraded (partially passable)
   segment loses the missing capacity fraction.

2. **Business interruption.** Flooded market and business premises (e.g.
   Bakaara Market) stop trading for the duration they are flooded or
   unreachable, independent of whether the road network itself is cut.

Reference: Section 9 of the build prompt (impact modelling).

PLACEHOLDER ASSUMPTIONS (all pending Somalia-specific calibration):
- Daily traffic/trade value per road segment and market area
- Reroutable fraction and detour cost multiplier
- Degraded-capacity fraction during partial passability
"""

from dataclasses import dataclass, field
from typing import List

import numpy as np


@dataclass
class RoadSegment:
    """An arterial road segment carrying goods and people movement."""

    name: str  # e.g. "Airport Road (Aden Adde corridor)"
    daily_traffic_value_usd: float  # Economic value of freight + passenger movement per normal day
    critical: bool = False  # e.g. connects the port and airport to the city centre

    # PLACEHOLDER: no published Somalia-specific road traffic-value estimate
    description: str = "Daily traffic value is a placeholder pending a transport/trade survey."

    def __post_init__(self) -> None:
        """Validate non-negative traffic value."""
        if not np.isfinite(self.daily_traffic_value_usd) or self.daily_traffic_value_usd < 0:
            raise ValueError("daily_traffic_value_usd must be finite and non-negative")


@dataclass
class RoadClosure:
    """
    Economic loss from one road segment being blocked or degraded by stagnant water.

    Three sub-losses, summed:
    - Fully blocked, non-reroutable traffic: its full value is lost for the closure.
    - Fully blocked, reroutable traffic: only the extra detour cost is lost.
    - Degraded (partially passable) traffic: the missing capacity fraction is lost.
    """

    segment: RoadSegment
    closure_duration_days: float  # Fully impassable
    degraded_duration_days: float = 0.0  # Passable but at reduced capacity
    degraded_capacity_fraction: float = 0.5  # Fraction of normal throughput while degraded
    reroutable_fraction: float = 0.0  # Fraction of blocked traffic that can detour
    detour_cost_multiplier: float = 1.5  # Cost of the detour relative to normal (>= 1)

    # PLACEHOLDER: judgemental; no Somalia-specific rerouting/detour survey
    description: str = "Reroutable fraction and detour multiplier are judgemental."

    def __post_init__(self) -> None:
        """Validate durations and fractions."""
        if self.closure_duration_days < 0 or self.degraded_duration_days < 0:
            raise ValueError("Closure and degraded durations must be non-negative")
        if not 0 <= self.degraded_capacity_fraction <= 1:
            raise ValueError("degraded_capacity_fraction must be in [0, 1]")
        if not 0 <= self.reroutable_fraction <= 1:
            raise ValueError("reroutable_fraction must be in [0, 1]")
        if self.detour_cost_multiplier < 1:
            raise ValueError("detour_cost_multiplier must be >= 1 (a detour cannot be cheaper than normal)")

    def calculate_loss(self) -> float:
        """
        Calculate total economic loss from this closure.

        Returns:
            Economic loss in USD
        """
        daily_value = self.segment.daily_traffic_value_usd
        blocked_value = daily_value * self.closure_duration_days

        lost_value = blocked_value * (1 - self.reroutable_fraction)
        detour_extra_cost = (
            blocked_value * self.reroutable_fraction * (self.detour_cost_multiplier - 1)
        )
        degraded_loss = (
            daily_value * self.degraded_duration_days * (1 - self.degraded_capacity_fraction)
        )
        return lost_value + detour_extra_cost + degraded_loss


@dataclass
class BusinessInterruptionLoss:
    """Trade activity halted by flooded or unreachable business premises."""

    area_name: str  # e.g. "Bakaara Market"
    daily_business_value_usd: float  # Normal daily formal + informal trade value
    fraction_closed: float  # 0-1: share of businesses flooded/unreachable
    duration_days: float

    # PLACEHOLDER: no published Somalia-specific informal-trade value estimate
    description: str = "Daily business value is a placeholder pending a market survey."

    def __post_init__(self) -> None:
        """Validate fractions and non-negative monetary/duration inputs."""
        if not 0 <= self.fraction_closed <= 1:
            raise ValueError("fraction_closed must be in [0, 1]")
        if self.daily_business_value_usd < 0 or self.duration_days < 0:
            raise ValueError("daily_business_value_usd and duration_days must be non-negative")

    def calculate_loss(self) -> float:
        """
        Calculate business interruption loss.

        Returns:
            Economic loss in USD
        """
        return self.daily_business_value_usd * self.fraction_closed * self.duration_days


@dataclass
class UrbanPluvialFloodImpact:
    """Complete Mogadishu productivity-loss summary: roads + business interruption."""

    event_date: str
    road_closures: List[RoadClosure] = field(default_factory=list)
    business_interruptions: List[BusinessInterruptionLoss] = field(default_factory=list)

    def total_expected_loss(self) -> float:
        """Sum road-network and business-interruption losses."""
        road_total = sum(closure.calculate_loss() for closure in self.road_closures)
        business_total = sum(loss.calculate_loss() for loss in self.business_interruptions)
        return road_total + business_total

    def headline_report(self) -> str:
        """Generate a headline productivity-loss report."""
        road_total = sum(closure.calculate_loss() for closure in self.road_closures)
        business_total = sum(loss.calculate_loss() for loss in self.business_interruptions)
        lines = [
            f"Mogadishu urban pluvial flood impact for {self.event_date}",
            f"Total expected productivity loss (USD): {road_total + business_total:,.2f}",
            f"  Road-network disruption (USD): {road_total:,.2f}",
        ]
        for closure in self.road_closures:
            lines.append(
                f"    {closure.segment.name}: ${closure.calculate_loss():,.2f} "
                f"({closure.closure_duration_days:.1f}d blocked, "
                f"{closure.degraded_duration_days:.1f}d degraded)"
            )
        lines.append(f"  Business interruption (USD): {business_total:,.2f}")
        for loss in self.business_interruptions:
            lines.append(
                f"    {loss.area_name}: ${loss.calculate_loss():,.2f} "
                f"({loss.fraction_closed:.0%} closed x {loss.duration_days:.1f}d)"
            )
        return "\n".join(lines)
