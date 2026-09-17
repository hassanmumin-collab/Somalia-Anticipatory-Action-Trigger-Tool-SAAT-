"""Operational tests for monetised riverine agricultural loss channels."""

import pytest

from saat.economic import (
    CropLoss,
    CropType,
    EconomicLossSummary,
    GrowthStage,
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


def test_irrigation_includes_repair_and_next_season_production():
    damage = SecondOrderIrrigationDamage(10, 100, 2000, 0.25, 100, 0.5, 1000, 2)
    assert damage.calculate_repair_cost() == pytest.approx(1500)
    assert damage.calculate_next_season_foregone_production() == pytest.approx(100000)
    assert damage.calculate_total_second_order_cost() == pytest.approx(101500)


def test_summary_totals_direct_and_second_order_loss():
    summary = EconomicLossSummary("2026-10-01", direct_crop_loss_usd=100, second_order_damage_usd=50)
    assert summary.total_expected_loss() == pytest.approx(150)
    report = summary.headline_report()
    assert "Direct crop loss" in report
    assert "Second-order irrigation damage" in report
