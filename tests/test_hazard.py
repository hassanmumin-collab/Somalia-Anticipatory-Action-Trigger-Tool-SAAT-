"""Tests for the hazard layer module."""

import pytest
import numpy as np
from datetime import datetime, timedelta

from saat.hazard import (
    AntecedentMoistureClass,
    RouteCalculator,
    AMCClassifier,
    SCSRunoffModel,
    FloodHazardIndicator,
)


class TestAntecedentMoistureClass:
    """Test AMC data class."""

    def test_valid_amc_types(self):
        """Test that valid AMC types are accepted."""
        for amc_type in ["AMC-I", "AMC-II", "AMC-III"]:
            amc = AntecedentMoistureClass(
                class_type=amc_type,
                prior_5day_mm=10.0,
                prior_90day_mm=100.0,
            )
            assert amc.class_type == amc_type

    def test_invalid_amc_type(self):
        """Test that invalid AMC type raises."""
        with pytest.raises(ValueError, match="Invalid AMC type"):
            AntecedentMoistureClass(
                class_type="AMC-IV",
                prior_5day_mm=10.0,
                prior_90day_mm=100.0,
            )


class TestRouteCalculator:
    """Test lag-and-accumulate routing."""

    def test_routing_lag_shifts_signal_forward(self):
        """Test that routing lag shifts the signal forward by exactly lag days."""
        calc = RouteCalculator(routing_lag_days=4, catchment_name="Shabelle")

        # Create synthetic rainfall: peak on day 5
        dates = np.array([datetime(2026, 8, 31) + timedelta(days=i) for i in range(15)])
        rainfall = np.array([0, 0, 10, 20, 30, 20, 10, 0, 0, 0, 0, 0, 0, 0, 0], dtype=float)

        routed_rainfall, routed_dates = calc.route_rainfall(rainfall, dates)

        # Peak should shift from index 4 to index 8 (4 days forward)
        assert np.argmax(routed_rainfall) == np.argmax(rainfall) + 4
        assert np.max(routed_rainfall) == np.max(rainfall)  # Peak amplitude unchanged

    def test_routing_lag_juba_6_days(self):
        """Test 6-day routing lag for Juba."""
        calc = RouteCalculator(routing_lag_days=6, catchment_name="Juba")

        dates = np.array([datetime(2026, 8, 31) + timedelta(days=i) for i in range(20)])
        rainfall = np.array(
            [0, 0, 0, 15, 25, 20, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            dtype=float,
        )

        routed_rainfall, routed_dates = calc.route_rainfall(rainfall, dates)

        peak_index = np.argmax(rainfall)
        routed_peak_index = np.argmax(routed_rainfall)
        assert routed_peak_index == peak_index + 6

    def test_routing_lag_preserves_total_volume(self):
        """Test that routing preserves total rainfall volume."""
        calc = RouteCalculator(routing_lag_days=4)

        dates = np.array([datetime(2026, 8, 31) + timedelta(days=i) for i in range(10)])
        rainfall = np.array([5, 10, 15, 10, 5, 0, 0, 0, 0, 0], dtype=float)

        routed_rainfall, routed_dates = calc.route_rainfall(rainfall, dates)

        # The zeros added at the start (before shift) should equal the rainfall removed at the end
        assert np.sum(routed_rainfall[:-4]) == np.sum(rainfall[:-4])

    def test_routing_lag_too_long_raises(self):
        """Test that lag longer than record raises."""
        calc = RouteCalculator(routing_lag_days=100)

        dates = np.array([datetime(2026, 8, 31) + timedelta(days=i) for i in range(10)])
        rainfall = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)

        with pytest.raises(ValueError, match="exceeds record length"):
            calc.route_rainfall(rainfall, dates)

    def test_accumulate_rainfall_window(self):
        """Test rainfall accumulation over window."""
        calc = RouteCalculator(routing_lag_days=4)

        rainfall = np.array([10, 10, 10, 10, 0, 0, 0, 0, 0, 0], dtype=float)
        accumulated = calc.accumulate_rainfall(rainfall, window_days=3)

        # First 3 days should have ~30mm (sum of first 3)
        assert accumulated[0] > 0
        # Last days should be ~0 (no rain)
        assert accumulated[-1] < 1


class TestAMCClassifier:
    """Test antecedent moisture classification."""

    def test_amc_iii_wet_condition(self):
        """Test AMC-III (wet) with >= 40mm in prior 5 days."""
        classifier = AMCClassifier()

        amc = classifier.classify(prior_5day_mm=50, prior_90day_mm=200)
        assert amc.class_type == "AMC-III"

    def test_amc_ii_normal_condition(self):
        """Test AMC-II (normal) classification."""
        classifier = AMCClassifier()

        amc = classifier.classify(prior_5day_mm=25, prior_90day_mm=150)
        assert amc.class_type == "AMC-II"

    def test_amc_i_inverted_dry_crusted(self):
        """Test inverted AMC-I (dry but crusted) for semi-arid soils."""
        # Set 15th percentile of 90-day climate
        classifier = AMCClassifier(climate_90day_15th_percentile=80)

        # Below 15th percentile = hardened/crusted (inverted high runoff)
        amc = classifier.classify(prior_5day_mm=20, prior_90day_mm=50)
        assert amc.class_type == "AMC-I"

        # Above 15th percentile but < 40mm 5-day = normal
        amc = classifier.classify(prior_5day_mm=20, prior_90day_mm=100)
        assert amc.class_type == "AMC-II"

    def test_desiccated_soil_higher_runoff_coefficient(self):
        """Test that desiccated soil (AMC-I inverted) yields higher runoff than normal."""
        model = SCSRunoffModel(use_inverted_amc_i=True)

        amc_i_dry = AntecedentMoistureClass("AMC-I", 10, 50, None)
        amc_ii_normal = AntecedentMoistureClass("AMC-II", 20, 120, None)

        # Same rainfall
        rainfall = 50  # mm

        runoff_i = model.calculate_runoff(rainfall, model.get_curve_number(amc_i_dry))
        runoff_ii = model.calculate_runoff(rainfall, model.get_curve_number(amc_ii_normal))

        # Inverted: AMC-I (desiccated) should have HIGHER runoff than AMC-II
        assert runoff_i >= runoff_ii
        print(f"AMC-I runoff: {runoff_i:.2f}mm, AMC-II runoff: {runoff_ii:.2f}mm")


class TestSCSRunoffModel:
    """Test SCS curve number model."""

    def test_default_curve_numbers(self):
        """Test default SCS curve numbers."""
        model = SCSRunoffModel(use_inverted_amc_i=False)

        amc_i = AntecedentMoistureClass("AMC-I", 10, 50, None)
        amc_ii = AntecedentMoistureClass("AMC-II", 20, 120, None)
        amc_iii = AntecedentMoistureClass("AMC-III", 50, 250, None)

        assert model.get_curve_number(amc_i) == 70
        assert model.get_curve_number(amc_ii) == 80
        assert model.get_curve_number(amc_iii) == 87

    def test_inverted_curve_numbers(self):
        """Test inverted curve numbers for semi-arid soils."""
        model = SCSRunoffModel(use_inverted_amc_i=True)

        amc_i = AntecedentMoistureClass("AMC-I", 10, 50, None)
        amc_ii = AntecedentMoistureClass("AMC-II", 20, 120, None)

        # Inverted: AMC-I should have HIGH curve number (high runoff)
        assert model.get_curve_number(amc_i) == 85
        assert model.get_curve_number(amc_ii) == 80

    def test_runoff_calculation_zero_rainfall(self):
        """Test that zero rainfall produces zero runoff."""
        model = SCSRunoffModel()

        amc = AntecedentMoistureClass("AMC-II", 20, 120, None)
        cn = model.get_curve_number(amc)

        runoff = model.calculate_runoff(0, cn)
        assert runoff == 0

    def test_runoff_calculation_small_rainfall(self):
        """Test small rainfall (less than initial abstraction) produces zero runoff."""
        model = SCSRunoffModel()

        amc = AntecedentMoistureClass("AMC-II", 20, 120, None)
        cn = 80
        # S = (25400/80 - 254) = 63.75mm
        # Initial abstraction = 0.2 * 63.75 = 12.75mm
        # So rainfall < 12.75 should give zero runoff

        runoff = model.calculate_runoff(10, cn)
        assert runoff == 0

    def test_runoff_calculation_heavy_rainfall(self):
        """Test runoff increases with rainfall."""
        model = SCSRunoffModel()

        amc = AntecedentMoistureClass("AMC-II", 20, 120, None)
        cn = 80

        runoff_50 = model.calculate_runoff(50, cn)
        runoff_100 = model.calculate_runoff(100, cn)
        runoff_150 = model.calculate_runoff(150, cn)

        # Runoff should increase monotonically
        assert runoff_50 > 0
        assert runoff_100 > runoff_50
        assert runoff_150 > runoff_100

    def test_runoff_depth_to_discharge_conversion(self):
        """Test conversion from runoff depth to discharge."""
        model = SCSRunoffModel()

        # 25mm runoff over 1000 km² area
        discharge = model.runoff_depth_to_discharge(
            runoff_depth_mm=25,
            drainage_area_km2=1000,
            timestep_hours=1,
        )

        # Q = 25 * 1000 * 0.278 / 1 = 6950 m³/s (approximately)
        assert discharge == pytest.approx(6950, rel=0.01)

    def test_runoff_depth_to_discharge_negative_area_raises(self):
        """Test that negative drainage area raises."""
        model = SCSRunoffModel()

        with pytest.raises(ValueError, match="must be positive"):
            model.runoff_depth_to_discharge(25, -1000, 1)

    def test_invalid_curve_number_raises(self):
        """Test that invalid curve number raises."""
        model = SCSRunoffModel()

        with pytest.raises(ValueError, match="Curve number must be"):
            model.calculate_runoff(50, 150)

    def test_simulate_event_runoff(self):
        """Test event runoff simulation."""
        model = SCSRunoffModel(use_inverted_amc_i=True)

        amc = AntecedentMoistureClass("AMC-I", 10, 50, None)

        # 50mm event on desiccated soil
        runoff = model.simulate_event_runoff(50, amc)

        assert runoff > 0
        assert runoff < 50  # Runoff < rainfall


class TestFloodHazardIndicator:
    """Test flood hazard indicator."""

    def test_risk_level_very_high_gauge_exceedance(self):
        """Test VERY_HIGH risk when gauge exceeds."""
        indicator = FloodHazardIndicator(
            date=datetime(2026, 8, 31),
            location="Belet Weyne",
            gauge_height_m=8.5,
            gauge_high_risk_level_m=7.5,
            gauge_exceedance=True,
        )
        indicator.set_risk_level()

        assert indicator.flood_risk_level == "VERY_HIGH"
        assert indicator.combined_indicator == 1.0

    def test_risk_level_high_flash_flood(self):
        """Test HIGH risk for flash flood."""
        indicator = FloodHazardIndicator(
            date=datetime(2026, 8, 31),
            location="Local area",
            flash_index=0.6,  # Moderate to high runoff
        )
        indicator.set_risk_level()

        assert indicator.flood_risk_level == "HIGH"

    def test_risk_level_moderate(self):
        """Test MODERATE risk."""
        indicator = FloodHazardIndicator(
            date=datetime(2026, 8, 31),
            location="Local area",
            flash_index=0.4,  # Moderate runoff
        )
        indicator.set_risk_level()

        assert indicator.flood_risk_level == "MODERATE"

    def test_risk_level_low_no_hazard(self):
        """Test LOW risk when no hazards."""
        indicator = FloodHazardIndicator(
            date=datetime(2026, 8, 31),
            location="Local area",
        )
        indicator.set_risk_level()

        assert indicator.flood_risk_level == "LOW"
        assert indicator.combined_indicator == 0.0
