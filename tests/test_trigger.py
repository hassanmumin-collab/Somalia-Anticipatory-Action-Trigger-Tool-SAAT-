"""Tests for the trigger evaluation module with fail-loud mechanism."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile

from saat.trigger import (
    DataStatus,
    TierStatus,
    IndicatorReading,
    TierEvaluation,
    SystemEvaluation,
    TierEvaluator,
    SystemEvaluator,
)


class TestDataStatus:
    """Test data status enum."""

    def test_status_values(self):
        """Test that all status values exist."""
        assert DataStatus.OK.value == "OK"
        assert DataStatus.DEGRADED.value == "DEGRADED"
        assert DataStatus.MISSING.value == "MISSING"
        assert DataStatus.STALE.value == "STALE"


class TestIndicatorReading:
    """Test indicator readings."""

    def test_threshold_met_greater_than_or_equal(self):
        """Test >= operator."""
        reading = IndicatorReading(
            indicator_name="test",
            value=10.0,
            threshold=5.0,
            operator=">=",
            data_status=DataStatus.OK,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow(),
            update_age_hours=0.5,
        )
        assert reading.is_met() is True

        reading.value = 4.0
        assert reading.is_met() is False

    def test_threshold_met_greater_than(self):
        """Test > operator."""
        reading = IndicatorReading(
            indicator_name="test",
            value=6.0,
            threshold=5.0,
            operator=">",
            data_status=DataStatus.OK,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow(),
            update_age_hours=0.5,
        )
        assert reading.is_met() is True

        reading.value = 5.0
        assert reading.is_met() is False

    def test_threshold_met_with_none_value(self):
        """Test that None value returns False."""
        reading = IndicatorReading(
            indicator_name="test",
            value=None,
            threshold=5.0,
            operator=">=",
            data_status=DataStatus.MISSING,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow(),
            update_age_hours=48.0,
        )
        assert reading.is_met() is False

    def test_is_usable_ok_and_degraded(self):
        """Test that OK and DEGRADED are usable."""
        ok_reading = IndicatorReading(
            indicator_name="ok",
            value=10.0,
            threshold=5.0,
            operator=">=",
            data_status=DataStatus.OK,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow(),
            update_age_hours=0.5,
        )
        assert ok_reading.is_usable() is True

        degraded_reading = IndicatorReading(
            indicator_name="degraded",
            value=10.0,
            threshold=5.0,
            operator=">=",
            data_status=DataStatus.DEGRADED,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow(),
            update_age_hours=30.0,
        )
        assert degraded_reading.is_usable() is True

    def test_is_usable_missing_and_stale(self):
        """Test that MISSING and STALE are not usable."""
        missing_reading = IndicatorReading(
            indicator_name="missing",
            value=None,
            threshold=5.0,
            operator=">=",
            data_status=DataStatus.MISSING,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow() - timedelta(hours=50),
            update_age_hours=50.0,
        )
        assert missing_reading.is_usable() is False

        stale_reading = IndicatorReading(
            indicator_name="stale",
            value=10.0,
            threshold=5.0,
            operator=">=",
            data_status=DataStatus.STALE,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow() - timedelta(hours=72),
            update_age_hours=72.0,
        )
        assert stale_reading.is_usable() is False

    def test_requires_escalation(self):
        """Test escalation detection."""
        missing = IndicatorReading(
            indicator_name="missing",
            value=None,
            threshold=5.0,
            operator=">=",
            data_status=DataStatus.MISSING,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow() - timedelta(hours=50),
            update_age_hours=50.0,
        )
        assert missing.requires_escalation() is True

        ok = IndicatorReading(
            indicator_name="ok",
            value=10.0,
            threshold=5.0,
            operator=">=",
            data_status=DataStatus.OK,
            source="test",
            timestamp=datetime.utcnow(),
            last_update=datetime.utcnow(),
            update_age_hours=0.5,
        )
        assert ok.requires_escalation() is False


class TestTierEvaluator:
    """Test tier evaluation logic."""

    def test_and_logic_all_met(self):
        """Test AND logic when all thresholds met."""
        evaluator = TierEvaluator("Test Tier", 1, combination_logic="and")

        readings = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
            IndicatorReading(
                indicator_name="ind2",
                value=20.0,
                threshold=15.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        eval_result = evaluator.evaluate(readings)
        assert eval_result.status == TierStatus.ACTIVE
        assert eval_result.threshold_met is True

    def test_and_logic_one_not_met(self):
        """Test AND logic when one threshold not met."""
        evaluator = TierEvaluator("Test Tier", 1, combination_logic="and")

        readings = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
            IndicatorReading(
                indicator_name="ind2",
                value=10.0,
                threshold=15.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        eval_result = evaluator.evaluate(readings)
        assert eval_result.status == TierStatus.INACTIVE
        assert eval_result.threshold_met is False

    def test_or_logic_one_met(self):
        """Test OR logic when one threshold met."""
        evaluator = TierEvaluator("Test Tier", 1, combination_logic="or")

        readings = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
            IndicatorReading(
                indicator_name="ind2",
                value=10.0,
                threshold=15.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        eval_result = evaluator.evaluate(readings)
        assert eval_result.status == TierStatus.ACTIVE
        assert eval_result.threshold_met is True

    def test_missing_data_escalation(self):
        """Test that missing data triggers escalation."""
        evaluator = TierEvaluator("Test Tier", 1, combination_logic="and")

        readings = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
            IndicatorReading(
                indicator_name="ind2",
                value=None,
                threshold=15.0,
                operator=">=",
                data_status=DataStatus.MISSING,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow() - timedelta(hours=50),
                update_age_hours=50.0,
            ),
        ]

        eval_result = evaluator.evaluate(readings)
        assert eval_result.status == TierStatus.ESCALATION
        assert "ESCALATION" in eval_result.rationale

    def test_stale_data_escalation(self):
        """Test that stale data triggers escalation."""
        evaluator = TierEvaluator("Test Tier", 1, combination_logic="and")

        readings = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
            IndicatorReading(
                indicator_name="ind2",
                value=20.0,
                threshold=15.0,
                operator=">=",
                data_status=DataStatus.STALE,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow() - timedelta(hours=72),
                update_age_hours=72.0,
            ),
        ]

        eval_result = evaluator.evaluate(readings)
        assert eval_result.status == TierStatus.ESCALATION

    def test_degraded_data_but_threshold_met(self):
        """Test ACTIVE status with degraded data when threshold met."""
        evaluator = TierEvaluator("Test Tier", 1, combination_logic="and")

        readings = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.DEGRADED,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow() - timedelta(hours=30),
                update_age_hours=30.0,
            ),
            IndicatorReading(
                indicator_name="ind2",
                value=20.0,
                threshold=15.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        eval_result = evaluator.evaluate(readings)
        assert eval_result.status == TierStatus.ACTIVE
        assert eval_result.threshold_met is True

    def test_majority_logic_tier_0(self):
        """Test majority logic (at least 2 of 3)."""
        evaluator = TierEvaluator("Tier 0: Seasonal Readiness", 0, combination_logic="majority")

        readings = [
            IndicatorReading(
                indicator_name="icpac",
                value=0.5,
                threshold=0.45,
                operator=">=",
                data_status=DataStatus.OK,
                source="ICPAC",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=1.0,
            ),
            IndicatorReading(
                indicator_name="c3s",
                value=0.25,
                threshold=0.25,
                operator=">=",
                data_status=DataStatus.OK,
                source="CDS",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=2.0,
            ),
            IndicatorReading(
                indicator_name="enso_iod",
                value=0.9,
                threshold=1.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="NOAA",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=1.0,
            ),
        ]

        eval_result = evaluator.evaluate(readings)
        # 2 of 3 met, so should be ACTIVE
        assert eval_result.status == TierStatus.ACTIVE

    def test_tier_evaluation_to_dict(self):
        """Test conversion to dictionary for logging."""
        evaluator = TierEvaluator("Test Tier", 1, combination_logic="and")

        readings = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        eval_result = evaluator.evaluate(readings)
        result_dict = eval_result.to_dict()

        assert "tier_name" in result_dict
        assert "status" in result_dict
        assert result_dict["status"] == "ACTIVE"
        assert "readings" in result_dict


class TestSystemEvaluator:
    """Test system-wide trigger evaluation."""

    def test_system_evaluation_active_tier(self):
        """Test system evaluation with active tier."""
        system = SystemEvaluator()

        tier1_eval = TierEvaluator("Tier 1", 1, combination_logic="and")
        tier2_eval = TierEvaluator("Tier 2", 2, combination_logic="or")

        system.add_tier(1, tier1_eval)
        system.add_tier(2, tier2_eval)

        readings_1 = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        readings_2 = [
            IndicatorReading(
                indicator_name="ind2",
                value=10.0,
                threshold=15.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        system_eval = system.evaluate({1: readings_1, 2: readings_2})

        assert system_eval.highest_active_tier == 1
        assert system_eval.system_status == TierStatus.ACTIVE

    def test_system_evaluation_escalation(self):
        """Test system evaluation with escalation."""
        system = SystemEvaluator()

        tier1_eval = TierEvaluator("Tier 1", 1, combination_logic="and")

        system.add_tier(1, tier1_eval)

        readings_1 = [
            IndicatorReading(
                indicator_name="ind1",
                value=None,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.MISSING,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow() - timedelta(hours=50),
                update_age_hours=50.0,
            ),
        ]

        system_eval = system.evaluate({1: readings_1})

        assert system_eval.system_status == TierStatus.ESCALATION

    def test_system_evaluation_absent_tier_escalation(self):
        """Test that absent tier produces escalation, not silence."""
        system = SystemEvaluator()

        tier1_eval = TierEvaluator("Tier 1", 1, combination_logic="and")
        tier2_eval = TierEvaluator("Tier 2", 2, combination_logic="or")

        system.add_tier(1, tier1_eval)
        system.add_tier(2, tier2_eval)

        readings_1 = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        # Missing Tier 2 readings entirely
        system_eval = system.evaluate({1: readings_1})

        assert TierStatus.ESCALATION in [e.status for e in system_eval.tier_evaluations.values()] or len(
            system_eval.escalations
        ) > 0
        assert "Tier 2 missing" in system_eval.overall_rationale or len(system_eval.escalations) > 0

    def test_system_evaluation_logging(self):
        """Test JSONL logging."""
        system = SystemEvaluator()
        tier1_eval = TierEvaluator("Tier 1", 1, combination_logic="and")
        system.add_tier(1, tier1_eval)

        readings_1 = [
            IndicatorReading(
                indicator_name="ind1",
                value=10.0,
                threshold=5.0,
                operator=">=",
                data_status=DataStatus.OK,
                source="test",
                timestamp=datetime.utcnow(),
                last_update=datetime.utcnow(),
                update_age_hours=0.5,
            ),
        ]

        system_eval = system.evaluate({1: readings_1})

        # Test JSONL conversion
        jsonl_line = system_eval.to_jsonl()
        parsed = json.loads(jsonl_line)

        assert "evaluation_time" in parsed
        assert "system_status" in parsed
        assert parsed["system_status"] == "ACTIVE"

        # Test file logging
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "trigger_log.jsonl"
            system_eval.log_to_file(log_file)

            assert log_file.exists()
            with open(log_file) as f:
                logged = json.loads(f.readline())
            assert logged["system_status"] == "ACTIVE"
