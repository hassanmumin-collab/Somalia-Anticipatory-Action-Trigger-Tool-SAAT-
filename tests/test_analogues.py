"""Operational tests for the multi-event historical Deyr analogue record."""

import pytest

from saat.analogues import (
    DEYR_HISTORICAL_EVENTS,
    EXPECTED_VALUE_SENSITIVITY,
    EXTREME_IOD_ANALOGUES,
    HISTORICAL_BASE_RATE_EXTREME_IOD,
    WEAK_IOD_ANALOGUES,
    HistoricalDeyrEvent,
    InsufficientDataError,
    bracket_estimate,
    classify_iod_scenario,
    weighted_expected_value,
)


def test_every_historical_event_has_at_least_one_impact_field_and_sources():
    for event in DEYR_HISTORICAL_EVENTS:
        assert event.oni_peak is not None, f"{event.year} missing oni_peak"
        assert event.iod_classification, f"{event.year} missing iod_classification"
        assert event.sources, f"{event.year} has no cited sources"
        assert any(
            value is not None
            for value in (event.deaths, event.displaced, event.econ_loss_usd)
        ), f"{event.year} has no populated impact field"


def test_dataset_contains_the_five_documented_deyr_events():
    years = {e.year for e in DEYR_HISTORICAL_EVENTS}
    assert years == {
        "1997-98 Deyr",
        "2006 Deyr",
        "2015-16 Deyr",
        "2019 Deyr",
        "2023 Deyr",
    }


def test_extreme_and_weak_iod_groups_partition_by_classification():
    assert all(e.iod_classification == "extreme_positive" for e in EXTREME_IOD_ANALOGUES)
    assert all(e.iod_classification == "weak_positive" for e in WEAK_IOD_ANALOGUES)
    # 2015-16 is the only weak-positive-IOD event in the record, despite having
    # the highest ONI of any event -- this is the whole point of the module.
    assert len(WEAK_IOD_ANALOGUES) == 1
    assert WEAK_IOD_ANALOGUES[0].year == "2015-16 Deyr"
    assert WEAK_IOD_ANALOGUES[0].oni_peak == max(e.oni_peak for e in DEYR_HISTORICAL_EVENTS)


def test_bracket_estimate_reads_min_max_off_real_events_not_a_synthetic_band():
    low, high, years = bracket_estimate(EXTREME_IOD_ANALOGUES, "deaths")
    # extreme-IOD events with a known death toll: 1997-98 (1500), 2019 (29), 2023 (188)
    assert low == 29
    assert high == 1500
    assert set(years) == {"1997-98 Deyr", "2019 Deyr", "2023 Deyr"}


def test_bracket_estimate_on_single_event_group_has_zero_width():
    low, high, years = bracket_estimate(WEAK_IOD_ANALOGUES, "displaced")
    assert low == high == 42000
    assert years == ["2015-16 Deyr"]


def test_bracket_estimate_returns_none_when_no_event_has_the_field():
    # No extreme-IOD event in this record has a verified econ_loss_usd except 2023.
    low, high, years = bracket_estimate(WEAK_IOD_ANALOGUES, "econ_loss_usd")
    assert (low, high, years) == (None, None, [])


def test_bracket_estimate_rejects_unsupported_field():
    with pytest.raises(ValueError, match="unsupported field"):
        bracket_estimate(DEYR_HISTORICAL_EVENTS, "oni_peak")


def test_classify_iod_scenario_exact_match_returns_only_matching_events():
    note, matching, bracketing = classify_iod_scenario("weak_positive")
    assert matching == WEAK_IOD_ANALOGUES
    assert bracketing == ()
    assert "matches" in note


def test_classify_iod_scenario_with_no_exact_match_returns_both_brackets():
    note, matching, bracketing = classify_iod_scenario("moderate_to_strong")
    assert matching == ()
    assert set(bracketing) == set(EXTREME_IOD_ANALOGUES) | set(WEAK_IOD_ANALOGUES)
    assert "no exact match" in note


def test_historical_base_rate_matches_the_dataset_composition():
    assert HISTORICAL_BASE_RATE_EXTREME_IOD == pytest.approx(4 / 5)
    assert HISTORICAL_BASE_RATE_EXTREME_IOD in EXPECTED_VALUE_SENSITIVITY


def test_weighted_expected_value_is_a_real_function_of_p_extreme():
    low_e, high_e, _ = bracket_estimate(EXTREME_IOD_ANALOGUES, "displaced")
    low_w, high_w, _ = bracket_estimate(WEAK_IOD_ANALOGUES, "displaced")

    lo0, hi0 = weighted_expected_value("displaced", 0.0)
    assert lo0 == pytest.approx(low_w)
    assert hi0 == pytest.approx(high_w)

    lo1, hi1 = weighted_expected_value("displaced", 1.0)
    assert lo1 == pytest.approx(low_e)
    assert hi1 == pytest.approx(high_e)

    lo_half, hi_half = weighted_expected_value("displaced", 0.5)
    assert lo_half == pytest.approx((low_e + low_w) / 2)
    assert hi_half == pytest.approx((high_e + high_w) / 2)
    # higher weight on the extreme branch should never lower the expected range
    assert lo1 >= lo_half >= lo0
    assert hi1 >= hi_half >= hi0


def test_weighted_expected_value_rejects_out_of_range_probability():
    with pytest.raises(ValueError, match=r"p_extreme must be in \[0, 1\]"):
        weighted_expected_value("displaced", 1.5)


def test_weighted_expected_value_refuses_to_blend_a_field_missing_from_one_branch():
    # The weak-IOD branch (2015-16) has no verified deaths or econ_loss_usd figure;
    # blending it with the populated extreme-IOD branch would silently treat the
    # missing branch as zero, which this function must refuse to do.
    for field in ("deaths", "econ_loss_usd"):
        with pytest.raises(InsufficientDataError):
            weighted_expected_value(field, 0.5)
