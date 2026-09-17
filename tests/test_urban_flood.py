"""Operational tests for Mogadishu urban pluvial flood productivity loss."""

import pytest

from saat.urban_flood import (
    BusinessInterruptionLoss,
    RoadClosure,
    RoadSegment,
    UrbanPluvialFloodImpact,
)


def test_road_segment_rejects_negative_traffic_value():
    with pytest.raises(ValueError, match="non-negative"):
        RoadSegment("Airport Road", daily_traffic_value_usd=-1.0)


def test_fully_blocked_non_reroutable_traffic_loses_full_value():
    segment = RoadSegment("Airport Road (Aden Adde corridor)", daily_traffic_value_usd=100_000.0, critical=True)
    closure = RoadClosure(segment, closure_duration_days=3.0, reroutable_fraction=0.0)
    assert closure.calculate_loss() == pytest.approx(300_000.0)


def test_reroutable_traffic_only_pays_detour_extra_cost():
    segment = RoadSegment("Maka Al Mukarama Road", daily_traffic_value_usd=50_000.0)
    closure = RoadClosure(
        segment, closure_duration_days=2.0, reroutable_fraction=1.0, detour_cost_multiplier=1.4
    )
    # Full value would be 100,000; but it all reroutes, so only the extra 40% detour cost is lost.
    assert closure.calculate_loss() == pytest.approx(100_000.0 * 0.4)


def test_degraded_capacity_loses_only_the_missing_fraction():
    segment = RoadSegment("KM4-KM5 junction", daily_traffic_value_usd=40_000.0)
    closure = RoadClosure(
        segment,
        closure_duration_days=0.0,
        degraded_duration_days=5.0,
        degraded_capacity_fraction=0.7,
    )
    assert closure.calculate_loss() == pytest.approx(40_000.0 * 5.0 * 0.3)


def test_detour_cost_multiplier_below_one_is_rejected():
    segment = RoadSegment("Afgooye Road", daily_traffic_value_usd=10_000.0)
    with pytest.raises(ValueError, match="detour_cost_multiplier"):
        RoadClosure(segment, closure_duration_days=1.0, reroutable_fraction=0.5, detour_cost_multiplier=0.9)


def test_business_interruption_scales_with_closed_fraction_and_duration():
    loss = BusinessInterruptionLoss(
        area_name="Bakaara Market", daily_business_value_usd=200_000.0, fraction_closed=0.4, duration_days=3.0
    )
    assert loss.calculate_loss() == pytest.approx(200_000.0 * 0.4 * 3.0)


def test_urban_pluvial_impact_sums_roads_and_business_interruption():
    segment = RoadSegment("Airport Road (Aden Adde corridor)", daily_traffic_value_usd=100_000.0, critical=True)
    closure = RoadClosure(segment, closure_duration_days=2.0, reroutable_fraction=0.0)
    business = BusinessInterruptionLoss("Bakaara Market", 200_000.0, 0.3, 2.0)

    impact = UrbanPluvialFloodImpact("2026-10-01", road_closures=[closure], business_interruptions=[business])

    expected_total = closure.calculate_loss() + business.calculate_loss()
    assert impact.total_expected_loss() == pytest.approx(expected_total)

    report = impact.headline_report()
    assert "Airport Road" in report
    assert "Bakaara Market" in report
