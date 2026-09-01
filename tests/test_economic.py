"""Operational tests for monetised economic impact channels."""

import pytest

from saat.economic import (
    CropLoss,
    CropType,
    EconomicLossSummary,
    FoodSecurityTransmission,
    GrowthStage,
    LivestockRVFLoss,
    RecoveryUpside,
    SecondOrderIrrigationDamage,
    SubmergenceDamageCurve,
)


def test_crop_loss_uses_duration_curve_and_interpolates():
    curve = SubmergenceDamageCurve(
        CropType.MAIZE,
        GrowthStage.VEGETATIVE,
        critical_duration_days=5,
        loss_fraction_at_duration={1: 0.1, 3: 0.8, 5: 0.95},
    )
    loss = CropLoss(CropType.MAIZE, GrowthStage.VEGETATIVE, 10, 4, 1000, 2)
    assert loss.calculate_loss(curve) == pytest.approx(10 * 1000 * 2 * 0.875)
    assert loss.loss_fraction == pytest.approx(0.875)


def test_crop_loss_requires_verified_curve_instead_of_hidden_defaults():
    loss = CropLoss(CropType.SORGHUM, GrowthStage.GRAIN_FILL, 1, 4, 100, 1)
    with pytest.raises(ValueError, match="verified submergence damage curve"):
        loss.calculate_loss()


def test_rvf_reports_expected_and_conditional_loss():
    loss = LivestockRVFLoss("goats", 1000, 0.2, 0.5, 3)
    assert loss.calculate_expected_loss() == pytest.approx(300)
    assert loss.calculate_conditional_loss() == pytest.approx(1500)


def test_irrigation_includes_repair_and_next_season_production():
    damage = SecondOrderIrrigationDamage(10, 100, 2000, 0.25, 100, 0.5, 1000, 2)
    assert damage.calculate_repair_cost() == pytest.approx(1500)
    assert damage.calculate_next_season_foregone_production() == pytest.approx(100000)
    assert damage.calculate_total_second_order_cost() == pytest.approx(101500)


def test_food_security_returns_transmission_channels_without_ipc_prediction():
    channels = FoodSecurityTransmission(0.3, 0.2, 1, 0.5, 0.4, 100, 0.1, 0.25, 2, 10000, 5)
    result = channels.calculate_food_insecurity_progression()
    assert result["cereal_price_usd_per_kg"] == pytest.approx(1.4)
    assert result["terms_of_trade"] == pytest.approx(75)
    assert result["awd_expected_deaths"] == pytest.approx(20)
    assert "ipc_phase" not in result


def test_recovery_is_reported_separately_from_immediate_loss():
    summary = EconomicLossSummary("2026-10-01", 100, 50, 5000, 25, 1000, {"awd_expected_deaths": 2})
    assert summary.total_expected_loss() == pytest.approx(175)
    report = summary.headline_report()
    assert "Recovery upside, reported separately" in report
    assert "RVF/export-ban conditional loss" in report
