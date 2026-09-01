"""
Hazard layer: catchment routing, antecedent moisture classification, runoff modelling.

Two classes of hazards:
1. **Riverine** - Lag-and-accumulate routing from upstream catchment rainfall
2. **Flash flood** - SCS curve number runoff model with inverted AMC-I for semi-arid soils

Reference: Section 7 of the build prompt.

CRITICAL: These towns flood from rainfall in the Ethiopian highlands, not local
rainfall. The routing lag (~4 days Shabelle, ~6 days Juba) is the tool's single
largest source of usable lead time. Ignoring it is the most common structural
error in Somalia flood models.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta


@dataclass
class AntecedentMoistureClass:
    """Antecedent soil moisture condition."""

    class_type: str  # "AMC-I", "AMC-II", "AMC-III"
    prior_5day_mm: float  # Cumulative rainfall in prior 5 days
    prior_90day_mm: float  # Cumulative rainfall in prior 90 days
    percentile_90day: Optional[float] = None  # Where prior 90-day sits in climatology

    def __post_init__(self):
        """Validate AMC type."""
        if self.class_type not in ["AMC-I", "AMC-II", "AMC-III"]:
            raise ValueError(f"Invalid AMC type: {self.class_type}")


class RouteCalculator:
    """Lag-and-accumulate routing from upstream catchment to gauge."""

    def __init__(self, routing_lag_days: int, catchment_name: str = ""):
        """
        Initialize routing calculator.

        Args:
            routing_lag_days: Days of travel time from catchment to gauge
            catchment_name: Name of catchment for logging
        """
        self.routing_lag_days = routing_lag_days
        self.catchment_name = catchment_name

    def route_rainfall(
        self,
        upstream_daily_rainfall: np.ndarray,
        dates: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Route upstream rainfall to gauge accounting for lag.

        Shifts the upstream signal forward by exactly routing_lag_days.
        This is NOT a hydraulic model; it simply answers "will the high-risk
        level be exceeded" by lagging the upstream index.

        Args:
            upstream_daily_rainfall: 1D array of daily rainfall (mm) at upstream station
            dates: 1D array of datetime objects corresponding to rainfall

        Returns:
            (routed_rainfall, routed_dates) shifted by routing lag
        """
        if len(upstream_daily_rainfall) != len(dates):
            raise ValueError("rainfall and dates arrays must have same length")

        lag_steps = self.routing_lag_days
        if lag_steps >= len(upstream_daily_rainfall):
            raise ValueError(
                f"Routing lag ({lag_steps} days) exceeds record length ({len(upstream_daily_rainfall)} days)"
            )

        # Extend the record so the lagged signal is not truncated at its end.
        routed_rainfall = np.concatenate([np.zeros(lag_steps), upstream_daily_rainfall])

        # Shift the dates array forward
        lag_delta = timedelta(days=lag_steps)
        routed_dates = np.array([d + lag_delta for d in dates])
        routed_dates = np.concatenate(
            [np.array([dates[-1] + lag_delta + timedelta(days=i) for i in range(lag_steps)]), routed_dates]
        )

        return routed_rainfall, routed_dates

    def accumulate_rainfall(
        self,
        routed_rainfall: np.ndarray,
        window_days: int = 30,
    ) -> np.ndarray:
        """
        Calculate accumulated rainfall over a window.

        Args:
            routed_rainfall: 1D array of daily rainfall (mm)
            window_days: Accumulation window (default 30 days)

        Returns:
            1D array of accumulated rainfall
        """
        return np.convolve(routed_rainfall, np.ones(window_days), mode="same")


@dataclass
class AMCClassifier:
    """Classify antecedent moisture condition from rainfall history."""

    climate_90day_15th_percentile: Optional[float] = None  # 15th percentile of 90-day accum
    climate_90day_mean: Optional[float] = None  # Mean of 90-day accumulation

    def classify(
        self,
        prior_5day_mm: float,
        prior_90day_mm: float,
        percentile_90day: Optional[float] = None,
    ) -> AntecedentMoistureClass:
        """
        Classify antecedent moisture from rainfall.

        Standard SCS method:
        - AMC-I (dry):     < 36mm (5-day) for dormant season
        - AMC-II (normal): 36-53mm (5-day)
        - AMC-III (wet):   > 53mm (5-day)

        **INVERTED for semi-arid soils:** On crusted soils, dry means HIGHER
        effective curve number (less infiltration). Standard reference: SCS
        Techs Note 1, TS-1. Somalia inversion physically motivated by crusting
        after 4+ failed seasons but NOT Somalia-specifically calibrated.

        Labels this clearly in code and output as modelling judgement.

        Args:
            prior_5day_mm: Rainfall in prior 5 days (mm)
            prior_90day_mm: Rainfall in prior 90 days (mm)
            percentile_90day: Percentile rank in climatology (optional)

        Returns:
            AntecedentMoistureClass enum
        """
        # Standard SCS thresholds for dormant season
        if prior_5day_mm >= 40:
            # Saturated condition (standard interpretation)
            amc_type = "AMC-III"
        elif prior_5day_mm < 40 and prior_90day_mm is not None:
            # Use 90-day accumulation to classify between dry and normal
            # Below 15th percentile = hardened/crusted (high runoff, INVERTED)
            # Above normal = AMC-II

            if self.climate_90day_15th_percentile is not None:
                if prior_90day_mm <= self.climate_90day_15th_percentile:
                    # INVERTED: dry = high runoff coefficient
                    amc_type = "AMC-I"
                else:
                    amc_type = "AMC-II"
            else:
                # Default: use 5-day threshold
                if prior_5day_mm >= 13:
                    amc_type = "AMC-II"
                else:
                    amc_type = "AMC-I"
        else:
            amc_type = "AMC-II"  # Default to normal

        return AntecedentMoistureClass(
            class_type=amc_type,
            prior_5day_mm=prior_5day_mm,
            prior_90day_mm=prior_90day_mm,
            percentile_90day=percentile_90day,
        )


class SCSRunoffModel:
    """
    SCS (NRCS) curve number model for runoff generation.

    Curve number depends on soil type, land use, and antecedent moisture.
    For Somalia, use inverted AMC-I treatment on semi-arid soils.
    """

    # Default curve numbers (Type B soil, pasture/range land)
    DEFAULT_CURVE_NUMBERS = {
        "AMC-I": 70,  # Dry (but crusted semi-arid = high runoff, inverted)
        "AMC-II": 80,  # Normal
        "AMC-III": 87,  # Wet
    }

    # Inverted curve numbers for crusted semi-arid soils (Somalia context)
    INVERTED_CURVE_NUMBERS = {
        "AMC-I": 85,  # DRY BUT CRUSTED = HIGH runoff coefficient
        "AMC-II": 80,  # Normal
        "AMC-III": 85,  # Wet
    }

    def __init__(self, use_inverted_amc_i: bool = True):
        """
        Initialize SCS model.

        Args:
            use_inverted_amc_i: Whether to invert AMC-I for semi-arid crusting
        """
        self.use_inverted_amc_i = use_inverted_amc_i
        self.curve_numbers = (
            self.INVERTED_CURVE_NUMBERS if use_inverted_amc_i else self.DEFAULT_CURVE_NUMBERS
        )

    def get_curve_number(self, amc: AntecedentMoistureClass) -> float:
        """Get curve number for given AMC."""
        return self.curve_numbers[amc.class_type]

    def calculate_runoff(self, rainfall_mm: float, curve_number: float) -> float:
        """
        Calculate runoff using SCS method.

        Q = (P - 0.2*S)^2 / (P + 0.8*S)  if P > 0.2*S, else Q = 0
        where S = (25400/CN - 254) in mm
              P = rainfall (mm)
              Q = runoff (mm)

        Args:
            rainfall_mm: Rainfall depth (mm)
            curve_number: SCS curve number (0-100)

        Returns:
            Runoff depth (mm)
        """
        if curve_number <= 0 or curve_number > 100:
            raise ValueError(f"Curve number must be in (0, 100], got {curve_number}")

        # Calculate maximum soil retention
        S_mm = (25400 / curve_number) - 254

        if S_mm < 0:
            S_mm = 0

        # Calculate runoff
        initial_abstraction = 0.2 * S_mm
        if rainfall_mm <= initial_abstraction:
            return 0.0
        else:
            numerator = (rainfall_mm - initial_abstraction) ** 2
            denominator = rainfall_mm + 0.8 * S_mm
            return numerator / denominator

    def simulate_event_runoff(
        self,
        event_rainfall_mm: float,
        amc: AntecedentMoistureClass,
    ) -> float:
        """
        Calculate event runoff for given rainfall and AMC.

        Args:
            event_rainfall_mm: Rainfall event depth (mm)
            amc: Antecedent moisture class

        Returns:
            Event runoff (mm)
        """
        cn = self.get_curve_number(amc)
        return self.calculate_runoff(event_rainfall_mm, cn)

    def runoff_depth_to_discharge(
        self,
        runoff_depth_mm: float,
        drainage_area_km2: float,
        timestep_hours: float = 1.0,
    ) -> float:
        """
        Convert runoff depth to discharge.

        Q = (runoff_mm / 1000 m/mm) * area_m2 / time_s
        or simply: Q (m³/s) = runoff_mm * area_km2 * 0.278 / hours

        Args:
            runoff_depth_mm: Runoff depth (mm)
            drainage_area_km2: Drainage area (km²)
            timestep_hours: Time interval (hours)

        Returns:
            Discharge (m³/s)
        """
        if drainage_area_km2 <= 0:
            raise ValueError("drainage_area_km2 must be positive")

        # Convert: mm * km² * 0.278 / hours = m³/s
        discharge_m3s = (runoff_depth_mm * drainage_area_km2 * 0.278) / timestep_hours
        return discharge_m3s


@dataclass
class FloodHazardIndicator:
    """Composite indicator of flood hazard."""

    date: datetime
    location: str

    # Riverine component
    routed_rainfall_mm: Optional[float] = None
    accumulated_rainfall_30day_mm: Optional[float] = None
    gauge_height_m: Optional[float] = None
    gauge_high_risk_level_m: Optional[float] = None
    gauge_exceedance: bool = False  # True if gauge > high risk level

    # Flash flood component
    event_rainfall_mm: Optional[float] = None
    amc_class: Optional[AntecedentMoistureClass] = None
    runoff_depth_mm: Optional[float] = None
    flash_index: Optional[float] = None  # Normalized runoff indicator [0-1]

    # Aggregated status
    flood_risk_level: str = "LOW"  # LOW, MODERATE, HIGH, VERY_HIGH
    combined_indicator: Optional[float] = None

    def set_risk_level(self) -> None:
        """Determine overall flood risk level."""
        risk_scores = []

        # Gauge exceedance
        if self.gauge_exceedance:
            risk_scores.append(100)
        elif self.gauge_height_m is not None and self.gauge_high_risk_level_m is not None:
            ratio = self.gauge_height_m / self.gauge_high_risk_level_m
            if ratio > 0.9:
                risk_scores.append(80)
            elif ratio > 0.8:
                risk_scores.append(60)

        # Flash flood runoff
        if self.flash_index is not None:
            if self.flash_index > 0.75:
                risk_scores.append(85)
            elif self.flash_index > 0.5:
                risk_scores.append(60)
            elif self.flash_index > 0.25:
                risk_scores.append(30)

        if not risk_scores:
            self.flood_risk_level = "LOW"
            self.combined_indicator = 0.0
        else:
            mean_score = np.mean(risk_scores)
            self.combined_indicator = mean_score / 100.0

            if mean_score >= 80:
                self.flood_risk_level = "VERY_HIGH"
            elif mean_score >= 60:
                self.flood_risk_level = "HIGH"
            elif mean_score >= 30:
                self.flood_risk_level = "MODERATE"
            else:
                self.flood_risk_level = "LOW"
