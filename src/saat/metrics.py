"""
Forecast verification metrics: contingency table skill scores.

Generic 2x2 contingency-table statistics used to score any binary forecast
against observations (e.g. the displacement generation model's blocked
cross-validation). Kept separate from any decision-cost framework: these are
plain discrimination/skill metrics, reportable regardless of what, if
anything, is triggered off the forecast.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class ContingencyMetrics:
    """Contingency table metrics for binary forecast evaluation."""

    hits: int
    false_alarms: int
    misses: int
    correct_negatives: int

    @property
    def pod(self) -> float:
        """Probability of Detection: hits / (hits + misses)."""
        denominator = self.hits + self.misses
        if denominator == 0:
            return np.nan
        return self.hits / denominator

    @property
    def pofd(self) -> float:
        """Probability of False Detection: false_alarms / (false_alarms + correct_negatives)."""
        denominator = self.false_alarms + self.correct_negatives
        if denominator == 0:
            return np.nan
        return self.false_alarms / denominator

    @property
    def far(self) -> float:
        """False Alarm Ratio: false_alarms / (hits + false_alarms)."""
        denominator = self.hits + self.false_alarms
        if denominator == 0:
            return np.nan
        return self.false_alarms / denominator

    @property
    def csi(self) -> float:
        """Critical Success Index: hits / (hits + false_alarms + misses)."""
        denominator = self.hits + self.false_alarms + self.misses
        if denominator == 0:
            return np.nan
        return self.hits / denominator

    @property
    def pss(self) -> float:
        """Peirce Skill Score (True Skill Statistic): POD - POFD."""
        return self.pod - self.pofd

    @property
    def frequency_bias(self) -> float:
        """Frequency Bias: (hits + false_alarms) / (hits + misses)."""
        denominator = self.hits + self.misses
        if denominator == 0:
            return np.nan
        return (self.hits + self.false_alarms) / denominator

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ContingencyMetrics(hits={self.hits}, fa={self.false_alarms}, "
            f"misses={self.misses}, cn={self.correct_negatives}, "
            f"POD={self.pod:.3f}, FAR={self.far:.3f}, PSS={self.pss:.3f})"
        )
