"""Operational tests for the expected-casualty model (urban + riverine)."""

import pytest

from saat.casualties import (
    CasualtySummary,
    DrowningExposure,
    DrowningRiskCurve,
    ElectrocutionExposure,
    FloodSetting,
    RiverineFloodCasualties,
    UrbanFloodCasualties,
)


URBAN_CURVE = DrowningRiskCurve(
    FloodSetting.URBAN_PLUVIAL,
    mortality_fraction_at_depth_m={0.3: 0.001, 1.0: 0.01, 2.0: 0.05},
)
RIVERINE_CURVE = DrowningRiskCurve(
    FloodSetting.RIVERINE,
    mortality_fraction_at_depth_m={0.5: 0.005, 1.5: 0.03, 3.0: 0.12},
)


def test_drowning_curve_interpolates_and_clamps():
    assert URBAN_CURVE.interpolate(1.0) == pytest.approx(0.01)
    # Below the shallowest calibration point: no modelled risk.
    assert URBAN_CURVE.interpolate(0.0) == pytest.approx(0.0)
    # Above the deepest point: hold at the deepest known rate, not extrapolate.
    assert URBAN_CURVE.interpolate(5.0) == pytest.approx(0.05)


def test_drowning_curve_rejects_non_monotonic_rates():
    bad_curve = DrowningRiskCurve(
        FloodSetting.URBAN_PLUVIAL, mortality_fraction_at_depth_m={0.3: 0.05, 1.0: 0.01}
    )
    with pytest.raises(ValueError, match="monotonic"):
        bad_curve.interpolate(0.5)


def test_drowning_exposure_requires_matching_setting():
    exposure = DrowningExposure(FloodSetting.URBAN_PLUVIAL, population_exposed=1000, water_depth_m=1.0)
    with pytest.raises(ValueError, match="does not match"):
        exposure.calculate_expected_deaths(RIVERINE_CURVE)


def test_drowning_exposure_lead_time_reduces_deaths_but_is_capped():
    no_warning = DrowningExposure(
        FloodSetting.RIVERINE, population_exposed=10000, water_depth_m=1.5, warning_lead_time_hours=0
    )
    with_warning = DrowningExposure(
        FloodSetting.RIVERINE,
        population_exposed=10000,
        water_depth_m=1.5,
        warning_lead_time_hours=6,
        lead_time_mitigation_fraction_per_hour=0.05,
        max_lead_time_mitigation_fraction=0.8,
    )
    base_deaths = no_warning.calculate_expected_deaths(RIVERINE_CURVE)
    mitigated_deaths = with_warning.calculate_expected_deaths(RIVERINE_CURVE)
    assert mitigated_deaths == pytest.approx(base_deaths * (1 - 0.3))

    long_warning = DrowningExposure(
        FloodSetting.RIVERINE,
        population_exposed=10000,
        water_depth_m=1.5,
        warning_lead_time_hours=1000,
        max_lead_time_mitigation_fraction=0.8,
    )
    # Mitigation cannot exceed the cap even with very long lead time.
    assert long_warning.calculate_expected_deaths(RIVERINE_CURVE) == pytest.approx(base_deaths * 0.2)


def test_electrocution_is_urban_specific_risk():
    exposure = ElectrocutionExposure(
        population_in_contact=5000, exposed_wiring_prevalence=0.1, contact_fatality_rate=0.02
    )
    assert exposure.calculate_expected_deaths() == pytest.approx(5000 * 0.1 * 0.02)


def test_urban_casualties_reject_riverine_drowning_exposure():
    riverine_exposure = DrowningExposure(FloodSetting.RIVERINE, population_exposed=100, water_depth_m=1.0)
    electrocution = ElectrocutionExposure(1000, 0.1, 0.01)
    with pytest.raises(ValueError, match="URBAN_PLUVIAL"):
        UrbanFloodCasualties("Mogadishu", riverine_exposure, electrocution)


def test_urban_casualties_sum_drowning_and_electrocution():
    drowning = DrowningExposure(FloodSetting.URBAN_PLUVIAL, population_exposed=8000, water_depth_m=1.0)
    electrocution = ElectrocutionExposure(
        population_in_contact=8000, exposed_wiring_prevalence=0.15, contact_fatality_rate=0.01
    )
    casualties = UrbanFloodCasualties("Mogadishu (Hodan/Wadajir)", drowning, electrocution)
    total = casualties.total_expected_deaths(URBAN_CURVE)
    expected = 8000 * 0.01 + 8000 * 0.15 * 0.01
    assert total == pytest.approx(expected)
    assert "Mogadishu" in casualties.headline_report(URBAN_CURVE)


def test_riverine_casualties_reject_urban_drowning_exposure():
    urban_exposure = DrowningExposure(FloodSetting.URBAN_PLUVIAL, population_exposed=100, water_depth_m=1.0)
    with pytest.raises(ValueError, match="RIVERINE"):
        RiverineFloodCasualties("Belet Weyne", urban_exposure)


def test_riverine_casualties_applies_secondary_cause_multiplier():
    drowning = DrowningExposure(FloodSetting.RIVERINE, population_exposed=20000, water_depth_m=1.5)
    casualties = RiverineFloodCasualties("Belet Weyne", drowning, secondary_cause_multiplier=1.2)
    base = drowning.calculate_expected_deaths(RIVERINE_CURVE)
    assert casualties.calculate_expected_deaths(RIVERINE_CURVE) == pytest.approx(base * 1.2)


def test_casualty_summary_aggregates_urban_and_riverine():
    urban = UrbanFloodCasualties(
        "Mogadishu",
        DrowningExposure(FloodSetting.URBAN_PLUVIAL, population_exposed=1000, water_depth_m=1.0),
        ElectrocutionExposure(1000, 0.1, 0.01),
    )
    riverine = RiverineFloodCasualties(
        "Jowhar", DrowningExposure(FloodSetting.RIVERINE, population_exposed=5000, water_depth_m=1.5)
    )
    summary = CasualtySummary("2026-10-01", urban=[urban], riverine=[riverine])
    total = summary.total_expected_deaths(URBAN_CURVE, RIVERINE_CURVE)
    expected = urban.total_expected_deaths(URBAN_CURVE) + riverine.calculate_expected_deaths(RIVERINE_CURVE)
    assert total == pytest.approx(expected)
    report = summary.headline_report(URBAN_CURVE, RIVERINE_CURVE)
    assert "Mogadishu" in report
    assert "Jowhar" in report
