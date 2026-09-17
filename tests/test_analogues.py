"""Operational tests for the 2023-baseline ENSO-scaling projection."""

import pytest

from saat.analogues import (
    BASELINE_2023,
    ENSO_STRENGTH_RATIO_2026_VS_2023,
    scaled_2023_projection,
)


def test_baseline_2023_matches_the_confirmed_pdna_figures():
    assert BASELINE_2023.deaths == 188
    assert BASELINE_2023.displaced == 417_791
    assert BASELINE_2023.econ_loss_usd == pytest.approx(176_000_000.0)
    assert BASELINE_2023.sources


def test_enso_strength_ratio_is_1_3():
    assert ENSO_STRENGTH_RATIO_2026_VS_2023 == pytest.approx(1.3)


def test_scaled_2023_projection_matches_the_documented_planning_figures():
    projection = scaled_2023_projection()
    assert projection["deaths"] == 244
    assert projection["displaced"] == 543_128
    assert projection["econ_loss_usd"] == pytest.approx(228_800_000.0)
    assert projection["multiplier"] == pytest.approx(1.3)


def test_scaled_2023_projection_accepts_a_custom_multiplier():
    doubled = scaled_2023_projection(multiplier=2.0)
    assert doubled["deaths"] == 2 * BASELINE_2023.deaths
    assert doubled["displaced"] == 2 * BASELINE_2023.displaced
    assert doubled["econ_loss_usd"] == pytest.approx(2 * BASELINE_2023.econ_loss_usd)


def test_scaled_2023_projection_at_multiplier_one_equals_the_baseline():
    unscaled = scaled_2023_projection(multiplier=1.0)
    assert unscaled["deaths"] == BASELINE_2023.deaths
    assert unscaled["displaced"] == BASELINE_2023.displaced
    assert unscaled["econ_loss_usd"] == pytest.approx(BASELINE_2023.econ_loss_usd)
