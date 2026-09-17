"""
Analogues module: scale the 2023 Deyr floods by this event's ENSO strength.

Somalia's 2023 Deyr floods are the most recent, most thoroughly documented
flood disaster in the country, with an independently verified death toll,
displacement figure and economic-loss total (Government of
Somalia/UN/World Bank/EU Rapid Post-Disaster Needs Assessment, cross-checked
against a SoDMA press release and OCHA situation reporting). This module
scales that documented baseline by the ratio of this event's forecast peak
ocean strength to 2023's confirmed peak, giving a single, transparent
planning projection for the 2026 Deyr rather than a fresh, uncalibrated
prediction built from first principles.

The scaling factor, ``ENSO_STRENGTH_RATIO_2026_VS_2023``, is the WMO's
median forecast peak Nino 3.4 anomaly for October-December 2026
(+2.67 degC) divided by 2023-24's confirmed peak (+2.0 degC), rounded to
1.3. It is a named, documented constant rather than a recomputed magic
number, so the derivation stays visible at the call site.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Baseline2023:
    """The 2023 Deyr floods: confirmed impact figures used as the scaling baseline."""

    deaths: int = 188
    displaced: int = 417_791  # PRMN-sourced, flood-attributed figure
    econ_loss_usd: float = 176_000_000.0  # $126.6M direct damage + $49.5M losses

    data_quality: str = (
        "Deaths, damage and losses are the confirmed figures from the joint Government "
        "of Somalia/UN/World Bank/EU Rapid Post-Disaster Needs Assessment, cross-checked "
        "directly against a Somali Disaster Management Agency (SoDMA) press release "
        "($176.0M = $126.6M direct damage + $49.5M losses; $230M recovery needs). "
        "Displacement (417,791) is the flood-attributed total from the project's PRMN "
        "dataset; the PDNA separately reports a much larger 'over 2 million displaced' "
        "figure using a broader, cumulative, multi-hazard definition across the full "
        "2023 season -- that is a different metric, not a competing estimate of the "
        "same quantity, and is not used here."
    )
    sources: tuple = (
        "Government of Somalia, UN, World Bank and EU, 'Somalia 2023 Deyr Floods: Rapid "
        "Post-Disaster Needs Assessment', 2024",
        "SoDMA press release, 'Somalia needs US$230m to support post-flood recovery...', "
        "2024",
        "OCHA Somalia, '2023 Deyr Season Floods' Situation Reports No. 1-5",
        "PRMN-derived displacement data (project-internal)",
    )


BASELINE_2023 = Baseline2023()

# WMO's median forecast peak Nino 3.4 anomaly for October-December 2026 (+2.67 degC)
# divided by 2023-24's confirmed peak (+2.0 degC) is 1.335; rounded to 1.3.
ENSO_STRENGTH_RATIO_2026_VS_2023: float = 1.3


def scaled_2023_projection(multiplier: float = ENSO_STRENGTH_RATIO_2026_VS_2023) -> dict:
    """
    Scale the 2023 Deyr baseline by the ENSO strength ratio.

    Args:
        multiplier: defaults to the current ENSO strength ratio; callers
            may pass a different value to explore sensitivity.

    Returns:
        dict with deaths/displaced/econ_loss_usd scaled from the 2023
        baseline, plus the multiplier and a plain-text basis string.
    """
    return {
        "multiplier": multiplier,
        "basis": (
            "2023 Deyr baseline (188 deaths / 417,791 displaced / $176.0M) x this "
            "event's forecast ENSO strength relative to 2023's"
        ),
        "deaths": round(BASELINE_2023.deaths * multiplier),
        "displaced": round(BASELINE_2023.displaced * multiplier),
        "econ_loss_usd": BASELINE_2023.econ_loss_usd * multiplier,
    }
