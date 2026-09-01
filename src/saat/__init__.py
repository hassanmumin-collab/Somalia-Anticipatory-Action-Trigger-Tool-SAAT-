"""
SAAT: Somalia Anticipatory Action Trigger tool.

Turns El Niño flood forecasts into pre-agreed, verifiable financing triggers,
with displacement caseload forecasting and monetised economic loss.

Public API: import the pieces you need directly from the package root, e.g.

    from saat import CostLossModel, CostLossParameters, SystemEvaluator
"""

__version__ = "0.1.0"
__author__ = "SAAT Team"

from saat.config import Config, get_config, reset_config
from saat.displacement import (
    AllocationModel,
    AllocationModelConfig,
    DisplacementForecast,
    GenerationModel,
    GenerationModelConfig,
)
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
from saat.hazard import (
    AMCClassifier,
    AntecedentMoistureClass,
    FloodHazardIndicator,
    RouteCalculator,
    SCSRunoffModel,
)
from saat.panel import (
    HAPIClient,
    HDXCKANClient,
    IOMETTLoader,
    PanelAssembler,
    PRMNLoader,
)
from saat.trigger import (
    DataStatus,
    IndicatorReading,
    SystemEvaluation,
    SystemEvaluator,
    TierEvaluation,
    TierEvaluator,
    TierStatus,
)
from saat.verification import (
    ContingencyMetrics,
    CostLossModel,
    CostLossParameters,
    DecisionOutcome,
)

__all__ = [
    "__version__",
    # verification
    "ContingencyMetrics",
    "CostLossModel",
    "CostLossParameters",
    "DecisionOutcome",
    # trigger
    "DataStatus",
    "IndicatorReading",
    "SystemEvaluation",
    "SystemEvaluator",
    "TierEvaluation",
    "TierEvaluator",
    "TierStatus",
    # hazard
    "AMCClassifier",
    "AntecedentMoistureClass",
    "FloodHazardIndicator",
    "RouteCalculator",
    "SCSRunoffModel",
    # displacement
    "AllocationModel",
    "AllocationModelConfig",
    "DisplacementForecast",
    "GenerationModel",
    "GenerationModelConfig",
    # economic
    "CropLoss",
    "CropType",
    "EconomicLossSummary",
    "FoodSecurityTransmission",
    "GrowthStage",
    "LivestockRVFLoss",
    "RecoveryUpside",
    "SecondOrderIrrigationDamage",
    "SubmergenceDamageCurve",
    # panel
    "HAPIClient",
    "HDXCKANClient",
    "IOMETTLoader",
    "PanelAssembler",
    "PRMNLoader",
    # config
    "Config",
    "get_config",
    "reset_config",
]
