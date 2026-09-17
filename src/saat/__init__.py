"""
SAAT: Somalia Anticipatory Action Trigger tool.

Turns El Niño flood forecasts into displacement caseload forecasts and
monetised flood impact: expected casualties (urban Mogadishu and riverine),
displacement, agricultural loss, and Mogadishu productivity loss from
pluvial flooding.

Public API: import the pieces you need directly from the package root, e.g.

    from saat import CasualtyEstimate, DisplacementForecast
"""

__version__ = "0.1.0"
__author__ = "SAAT Team"

from saat.casualties import (
    CasualtySummary,
    DrowningExposure,
    DrowningRiskCurve,
    ElectrocutionExposure,
    FloodSetting,
    RiverineFloodCasualties,
    UrbanFloodCasualties,
)
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
    GrowthStage,
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
from saat.metrics import ContingencyMetrics
from saat.panel import (
    HAPIClient,
    HDXCKANClient,
    IOMETTLoader,
    PanelAssembler,
    PRMNLoader,
)
from saat.urban_flood import (
    BusinessInterruptionLoss,
    RoadClosure,
    RoadSegment,
    UrbanPluvialFloodImpact,
)

__all__ = [
    "__version__",
    # casualties
    "CasualtySummary",
    "DrowningExposure",
    "DrowningRiskCurve",
    "ElectrocutionExposure",
    "FloodSetting",
    "RiverineFloodCasualties",
    "UrbanFloodCasualties",
    # metrics
    "ContingencyMetrics",
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
    # economic (agriculture, riverine)
    "CropLoss",
    "CropType",
    "EconomicLossSummary",
    "GrowthStage",
    "SecondOrderIrrigationDamage",
    "SubmergenceDamageCurve",
    # urban_flood (Mogadishu productivity loss)
    "BusinessInterruptionLoss",
    "RoadClosure",
    "RoadSegment",
    "UrbanPluvialFloodImpact",
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
