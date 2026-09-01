"""Tests for the cost-loss verification model."""

import pytest
import numpy as np
from saat.verification import (
    CostLossModel,
    CostLossParameters,
    ContingencyMetrics,
    DataStatus,
)


class TestContingencyMetrics:
    """Test contingency table metrics."""

    def test_pod(self):
        """Test Probability of Detection calculation."""
        metrics = ContingencyMetrics(hits=8, false_alarms=2, misses=2, correct_negatives=88)
        assert metrics.pod == 0.8  # 8 / (8 + 2)

    def test_pofd(self):
        """Test Probability of False Detection."""
        metrics = ContingencyMetrics(hits=8, false_alarms=2, misses=2, correct_negatives=88)
        assert metrics.pofd == pytest.approx(2 / 90)  # 2 / (2 + 88)

    def test_far(self):
        """Test False Alarm Ratio."""
        metrics = ContingencyMetrics(hits=8, false_alarms=2, misses=2, correct_negatives=88)
        assert metrics.far == 0.2  # 2 / (8 + 2)

    def test_csi(self):
        """Test Critical Success Index."""
        metrics = ContingencyMetrics(hits=8, false_alarms=2, misses=2, correct_negatives=88)
        assert metrics.csi == pytest.approx(8 / 12)  # 8 / (8 + 2 + 2)

    def test_pss(self):
        """Test Peirce Skill Score."""
        metrics = ContingencyMetrics(hits=8, false_alarms=2, misses=2, correct_negatives=88)
        pod = 0.8
        pofd = 2 / 90
        assert metrics.pss == pytest.approx(pod - pofd)

    def test_division_by_zero_handling(self):
        """Test handling of zero denominators."""
        metrics = ContingencyMetrics(hits=0, false_alarms=0, misses=0, correct_negatives=100)
        assert np.isnan(metrics.pod)
        assert np.isnan(metrics.far)


class TestCostLossParameters:
    """Test cost-loss parameter validation."""

    def test_valid_parameters(self):
        """Test that valid parameters pass validation."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        is_feasible, error = params.validate()
        assert is_feasible
        assert error is None

    def test_infeasible_high_cost(self):
        """Test that C/L >= f raises infeasibility error."""
        # C/L = 1.0 >= f = 0.8
        params = CostLossParameters(
            cost_action=8.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        is_feasible, error = params.validate()
        assert not is_feasible
        assert "INFEASIBLE" in error

    def test_invalid_effectiveness(self):
        """Test invalid mitigation effectiveness."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=1.5,
            climatological_base_rate=0.1,
        )
        is_feasible, error = params.validate()
        assert not is_feasible

    def test_invalid_base_rate(self):
        """Test invalid climatological base rate."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=1.5,
        )
        is_feasible, error = params.validate()
        assert not is_feasible


class TestCostLossModel:
    """Test the cost-loss decision model."""

    def test_initialization_valid(self):
        """Test initialization with valid parameters."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)
        assert model.params == params

    def test_initialization_invalid(self):
        """Test initialization with invalid parameters raises."""
        params = CostLossParameters(
            cost_action=8.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        with pytest.raises(ValueError, match="INFEASIBLE"):
            CostLossModel(params)

    def test_expected_expense_always_act(self):
        """Test expected expense for always-act strategy."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)
        # C + (1-f)*s*L = 1 + (1-0.8)*0.1*10 = 1 + 0.2 = 1.2
        assert model._expected_expense_always_act() == pytest.approx(1.2)

    def test_expected_expense_never_act(self):
        """Test expected expense for never-act strategy."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)
        # s*L = 0.1*10 = 1.0
        assert model._expected_expense_never_act() == pytest.approx(1.0)

    def test_expected_expense_perfect(self):
        """Test expected expense for perfect forecast."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)
        # s*(C + (1-f)*L) = 0.1*(1 + (1-0.8)*10) = 0.1*3 = 0.3
        assert model._expected_expense_perfect() == pytest.approx(0.3)

    def test_expected_expense_forecast(self):
        """Test expected expense calculation for a specific forecast."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)

        metrics = ContingencyMetrics(hits=8, false_alarms=2, misses=2, correct_negatives=88)
        # Counts are converted to rates over N = 100 opportunities before the
        # formula is applied, so the result is per-opportunity and comparable
        # with always/never/perfect act:
        # (0.08 + 0.02)*1 + 0.08*0.2*10 + 0.02*10
        # = 0.10 + 0.16 + 0.20 = 0.46
        assert model.expected_expense_forecast(metrics) == pytest.approx(0.46)

    def test_relative_economic_value(self):
        """Test relative economic value calculation."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)

        metrics = ContingencyMetrics(hits=8, false_alarms=2, misses=2, correct_negatives=88)
        # POD 0.8, FAR 0.2 at a 10% base rate with C/L = 0.1 is a skilful,
        # decision-improving forecast:
        # E_reference = min(always=1.2, never=1.0) = 1.0
        # E_forecast  = 0.46  (per opportunity)
        # E_perfect   = 0.3
        # V = (1.0 - 0.46) / (1.0 - 0.3) = 0.54 / 0.7 = 0.771
        rev = model.relative_economic_value(metrics)
        assert rev == pytest.approx(0.54 / 0.7)

    def test_cheap_action_high_far_still_beats_trivial_strategies(self):
        """Acceptance criterion: a cheap action whose optimal operating point has
        FAR > 0.5 still returns relative economic value > 0.5.

        The forecast cannot cleanly separate events from non-events: catching
        every event (a miss costs L = 100x the action) forces the optimiser to
        accept more false alarms than hits. Two thirds of activations are wrong,
        and acting on the trigger is still strongly worth funding.
        """
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=100.0,
            mitigation_effectiveness=0.9,
            climatological_base_rate=0.2,
        )
        model = CostLossModel(params)

        # 4 events, scores 0.54-0.60, interleaved with a cluster of non-events at
        # 0.55-0.62 that cannot be excluded without dropping a real event.
        events = [0.60, 0.58, 0.56, 0.54]
        near_non_events = [0.62, 0.61, 0.59, 0.57, 0.55]
        far_non_events = [0.30, 0.25, 0.22, 0.20, 0.18, 0.15, 0.12, 0.10, 0.08, 0.05, 0.03]
        forecasts = np.array(events + near_non_events + far_non_events)
        observations = np.array([1] * 4 + [0] * (len(near_non_events) + len(far_non_events)))

        outcome = model.optimize_threshold(observations, forecasts)

        assert outcome.pod == 1.0
        assert outcome.far > 0.5
        assert outcome.relative_economic_value > 0.5

    def test_optimize_threshold(self):
        """Test threshold optimization."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)

        observations = np.array([0, 1, 0, 1, 0, 1, 0, 0, 1, 0])
        forecasts = np.array([0.1, 0.95, 0.2, 0.85, 0.3, 0.9, 0.4, 0.05, 0.88, 0.15])

        outcome = model.optimize_threshold(observations, forecasts)

        assert outcome.threshold is not None
        assert outcome.contingency is not None
        assert not np.isnan(outcome.pod)
        assert not np.isnan(outcome.far)

    def test_optimize_threshold_with_pod_constraint(self):
        """Test threshold optimization with POD constraint."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)

        observations = np.array([0, 1, 0, 1, 0, 1, 0, 0, 1, 0])
        forecasts = np.array([0.1, 0.95, 0.2, 0.85, 0.3, 0.9, 0.4, 0.05, 0.88, 0.15])

        outcome = model.optimize_threshold(observations, forecasts, min_pod=0.5)
        assert outcome.pod >= 0.5

    def test_optimize_threshold_unsatisfiable_constraint(self):
        """Test that unsatisfiable constraints raise an error."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)

        observations = np.array([0, 0, 0, 0, 0])  # No events
        forecasts = np.array([0.1, 0.2, 0.3, 0.4, 0.5])

        # Require POD >= 0.5 but no events to detect
        with pytest.raises(ValueError, match="No threshold meets operational constraints"):
            model.optimize_threshold(observations, forecasts, min_pod=0.5)

    def test_sweep_thresholds(self):
        """Test sweeping all thresholds."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)

        observations = np.array([0, 1, 0, 1, 0, 1, 0, 0, 1, 0])
        forecasts = np.array([0.1, 0.95, 0.2, 0.85, 0.3, 0.9, 0.4, 0.05, 0.88, 0.15])

        outcomes = model.sweep_thresholds(observations, forecasts)

        assert len(outcomes) > 0
        # Check outcomes are sorted by relative economic value
        for i in range(len(outcomes) - 1):
            if not np.isnan(outcomes[i].relative_economic_value):
                if not np.isnan(outcomes[i + 1].relative_economic_value):
                    assert outcomes[i].relative_economic_value >= outcomes[i + 1].relative_economic_value

    def test_input_validation(self):
        """Test input validation for optimize_threshold."""
        params = CostLossParameters(
            cost_action=1.0,
            loss_event=10.0,
            mitigation_effectiveness=0.8,
            climatological_base_rate=0.1,
        )
        model = CostLossModel(params)

        # Mismatched lengths
        with pytest.raises(ValueError):
            model.optimize_threshold(
                np.array([0, 1, 0]),
                np.array([0.1, 0.2]),
            )

        # Empty arrays
        with pytest.raises(ValueError):
            model.optimize_threshold(np.array([]), np.array([]))

        # Invalid observations (not binary)
        with pytest.raises(ValueError):
            model.optimize_threshold(
                np.array([0, 2, 1]),
                np.array([0.1, 0.2, 0.3]),
            )


class TestDataStatus:
    """Test data status enum."""

    def test_status_values(self):
        """Test that all status values exist."""
        assert DataStatus.OK.value == "OK"
        assert DataStatus.DEGRADED.value == "DEGRADED"
        assert DataStatus.MISSING.value == "MISSING"
        assert DataStatus.STALE.value == "STALE"
