"""
Analogues module: multi-event historical evidence for Deyr flood severity.

This module replaces a single-analogue-times-ratio approach (take the 2023
Deyr floods, multiply by a strength ratio) with an explicit historical
record spanning five documented Deyr seasons. The reason is empirical, not
stylistic: Somalia's Deyr flood severity tracks the *joint* ENSO+IOD state,
not ENSO (Nino 3.4 / ONI) strength alone.

The clearest evidence for this is the contrast between two real events:

- **2015-16 Deyr**: ONI +2.6, the strongest El Nino on record at the time --
  yet the positive Indian Ocean Dipole that year was weak and terminated in
  November, before the Deyr climatological peak (Hong et al., J. Climate,
  2017, explicitly contrasts this against 1997-98). Somalia's flood impact
  that Deyr was comparatively contained.
- **2019 Deyr**: ONI only weakly positive/neutral (~0.5) -- not a proper El
  Nino by most thresholds -- yet the Indian Ocean Dipole was one of the most
  extreme positive events on record. Somalia's flood impact was severe
  (3.4M people affected) despite the absence of a strong El Nino.

Record-strength ENSO alone (2015-16) did not reproduce 1997/2023-scale
impact; a weak-ENSO/extreme-IOD combination (2019) did. Any estimate for a
new Deyr season that scales solely off an ONI ratio is therefore built on
the wrong variable in isolation. This module instead exposes the historical
record directly, classified by each event's joint ENSO/IOD state, so a
current forecast can be matched against the analogues that actually share
its ocean state -- and, where the current forecast falls between historical
states (as the 2026 IOD trajectory does as of this module's last update),
that gap is reported explicitly rather than resolved by inventing a number.

Every field below is sourced; where a figure could not be verified to a
specific, defensible value, the field is left ``None`` rather than
back-filled -- the same "no hidden default" discipline as
``casualties.DrowningRiskCurve`` and ``economic.SubmergenceDamageCurve``.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class HistoricalDeyrEvent:
    """One documented Deyr-season flood event and its ocean-state context."""

    year: str
    oni_peak: Optional[float]  # traditional-method ONI / Nino 3.4 seasonal peak, degC
    iod_classification: str  # "extreme_positive" | "weak_positive" | "weak_enso_neutral_iod"
    dmi_peak: Optional[float]  # Dipole Mode Index peak, degC, where verified
    deaths: Optional[int]
    displaced: Optional[int]  # PRMN-sourced flood-attributed figure where available
    econ_loss_usd: Optional[float]
    data_quality: str  # what is uncertain, approximate, or a different metric than it looks
    sources: Tuple[str, ...]


DEYR_HISTORICAL_EVENTS: Tuple[HistoricalDeyrEvent, ...] = (
    HistoricalDeyrEvent(
        year="1997-98 Deyr",
        oni_peak=2.3,
        iod_classification="extreme_positive",
        dmi_peak=None,
        deaths=1500,
        displaced=230000,
        econ_loss_usd=None,
        data_quality=(
            "Deaths reported as 1,500 (FAO/GIEWS) to ~2,000 (regional estimate, most in "
            "Somalia) depending on source; treat as an order-of-magnitude figure, not a "
            "precise count. ONI reported as 2.3-2.4 degC depending on dataset version. No "
            "reliable aggregate USD damage figure was found -- only sectoral physical damage "
            "(approximately 50,000 ha of farmland destroyed, 35,500 livestock lost), which is "
            "not converted to a USD total here because doing so would require assumptions "
            "this module does not make."
        ),
        sources=(
            "FAO/GIEWS Special Report: Eastern Africa (heavy rains attributed to El Nino), "
            "5 February 1998",
            "CARE International, El Nino 1997-98: Impacts and CARE's Response",
        ),
    ),
    HistoricalDeyrEvent(
        year="2006 Deyr",
        oni_peak=0.7,
        iod_classification="extreme_positive",
        dmi_peak=None,
        deaths=None,
        displaced=60000,
        econ_loss_usd=None,
        data_quality=(
            "ONI reported only qualitatively as a 'weak' El Nino (0.5-0.9 degC bracket); 0.7 "
            "used here as the bracket midpoint, not a verified point figure. Displacement "
            "figure (60,000) covers Beledweyne specifically following the 10-11 November "
            "storms and is very likely an undercount of the full-season, all-Somalia total; "
            "a separate, broader 'affected' figure of 440,000 was also reported for the "
            "2006-07 season but is a different metric (affected, not displaced) and is not "
            "used here. No death toll for the full event was found in available reporting."
        ),
        sources=(
            "OCHA, Somalia: Floods Situation Report, 7 December 2006",
            "FloodList, 'Somalia - Over 70,000 Displaced as Rivers Overflow'",
        ),
    ),
    HistoricalDeyrEvent(
        year="2015-16 Deyr",
        oni_peak=2.6,
        iod_classification="weak_positive",
        dmi_peak=None,
        deaths=None,
        displaced=42000,
        econ_loss_usd=None,
        data_quality=(
            "The positive IOD in 2015 was weak and short-lived, peaking around September and "
            "terminating in November -- before the Deyr climatological peak -- unlike 1997-98 "
            "when an extreme IOD coincided with the El Nino peak (Hong et al., J. Climate, "
            "2017). Displacement reported as 42,000 (OCHA) to 72,000 depending on source; the "
            "lower, OCHA-attributed figure is used here. No direct flood-death toll was found "
            "in available reporting; 84 deaths were separately reported from a cholera "
            "outbreak in flood-affected areas, a distinct causal category not counted as a "
            "direct flood death here."
        ),
        sources=(
            "OCHA, flooding update, Shabelle and Juba regions, November 2015",
            "Hong, C.-C. et al., 'Why Was the Indian Ocean Dipole Weak in the Context of the "
            "Extreme El Nino in 2015?', Journal of Climate, 30(12), 2017",
        ),
    ),
    HistoricalDeyrEvent(
        year="2019 Deyr",
        oni_peak=0.5,
        iod_classification="extreme_positive",
        dmi_peak=2.4,
        deaths=29,
        displaced=409508,
        econ_loss_usd=None,
        data_quality=(
            "ONI was only weakly positive/neutral (~0.5 degC) -- not a conventional El Nino by "
            "most thresholds -- while the IOD was one of the most extreme positive events on "
            "record; peak DMI is reported as 2.4 degC in some analyses and as high as 2.74 "
            "degC in others depending on dataset and smoothing, with lower monthly-mean values "
            "(~1.0 degC in Sep-Nov). Displacement figure (409,508) is the flood-attributed "
            "total from the same PRMN dataset used for the 2023 baseline elsewhere in this "
            "project, not a press estimate. No reliable aggregate USD damage figure was found; "
            "sectoral reporting cites 1,200 farms inundated and 250 livestock drowned in "
            "Gedo/Juba specifically, not a national total."
        ),
        sources=(
            "ACAPS, 'Somalia: Floods in Southern Regions', Briefing Note, 4 November 2019",
            "PRMN-derived displacement data (project-internal, cross-checked against the "
            "same source used for the 2023 Deyr baseline)",
            "Lu, B. & Ren, H.-L., 'What Caused the Extreme Indian Ocean Dipole Event in "
            "2019?', Geophysical Research Letters, 2020",
        ),
    ),
    HistoricalDeyrEvent(
        year="2023 Deyr",
        oni_peak=2.0,
        iod_classification="extreme_positive",
        dmi_peak=None,
        deaths=188,
        displaced=417791,
        econ_loss_usd=176_000_000.0,
        data_quality=(
            "Deaths, damage and losses are the confirmed figures from the joint Government "
            "of Somalia/UN/World Bank/EU Rapid Post-Disaster Needs Assessment, cross-checked "
            "directly against a Somali Disaster Management Agency (SoDMA) press release "
            "($176.0M = $126.6M direct damage + $49.5M losses; $230M recovery needs). "
            "Displacement (417,791) is the flood-attributed total from the same PRMN dataset "
            "as 2019 above; the PDNA separately reports a much larger 'over 2 million "
            "displaced' figure using a broader, cumulative, multi-hazard definition across the "
            "full 2023 season -- that is a different metric, not a competing estimate of the "
            "same quantity, and is not used here."
        ),
        sources=(
            "Government of Somalia, UN, World Bank and EU, 'Somalia 2023 Deyr Floods: Rapid "
            "Post-Disaster Needs Assessment', 2024",
            "SoDMA press release, 'Somalia needs US$230m to support post-flood recovery...', "
            "2024",
            "OCHA Somalia, '2023 Deyr Season Floods' Situation Reports No. 1-5",
            "PRMN-derived displacement data (project-internal)",
        ),
    ),
)


EXTREME_IOD_ANALOGUES: Tuple[HistoricalDeyrEvent, ...] = tuple(
    e for e in DEYR_HISTORICAL_EVENTS if e.iod_classification == "extreme_positive"
)
WEAK_IOD_ANALOGUES: Tuple[HistoricalDeyrEvent, ...] = tuple(
    e for e in DEYR_HISTORICAL_EVENTS if e.iod_classification == "weak_positive"
)


def bracket_estimate(
    events: Sequence[HistoricalDeyrEvent], field: str
) -> Tuple[Optional[float], Optional[float], List[str]]:
    """
    Read a low/high bracket for one impact field straight off the historical record.

    This deliberately does not fit a curve or apply a synthetic +/- band: the
    bracket is exactly the min and max of the events that actually have a
    verified value for this field. With few events, this can mean a bracket
    of width zero (one event) or an empty bracket (no event has this field
    populated) -- both are reported honestly rather than papered over.

    Args:
        events: candidate historical events (e.g. EXTREME_IOD_ANALOGUES)
        field: one of "deaths", "displaced", "econ_loss_usd"

    Returns:
        (low, high, contributing_years) -- low/high are None if no event in
        `events` has a non-None value for `field`.
    """
    if field not in ("deaths", "displaced", "econ_loss_usd"):
        raise ValueError(f"unsupported field: {field!r}")

    values = []
    years = []
    for event in events:
        value = getattr(event, field)
        if value is not None:
            values.append(value)
            years.append(event.year)

    if not values:
        return None, None, []
    return min(values), max(values), years


def classify_iod_scenario(
    forecast_classification: str,
) -> Tuple[str, Tuple[HistoricalDeyrEvent, ...], Tuple[HistoricalDeyrEvent, ...]]:
    """
    Match a forecast IOD classification against the historical record.

    Args:
        forecast_classification: e.g. "extreme_positive", "weak_positive",
            or an intermediate forecaster's term like "moderate_to_strong"
            that does not correspond exactly to a historical bucket in this
            five-event record.

    Returns:
        (note, matching_events, bracketing_events) where:
        - `matching_events` is non-empty only for an exact classification match
        - `bracketing_events` is EXTREME_IOD_ANALOGUES + WEAK_IOD_ANALOGUES
          whenever there is no exact match, so the caller can present both
          sides of the gap explicitly instead of guessing a point estimate
    """
    matching = tuple(
        e for e in DEYR_HISTORICAL_EVENTS if e.iod_classification == forecast_classification
    )
    if matching:
        return (
            f"'{forecast_classification}' matches {len(matching)} historical event(s) directly.",
            matching,
            (),
        )
    return (
        f"'{forecast_classification}' has no exact match in the five-event historical record "
        f"used here (recorded classifications: extreme_positive, weak_positive). Reporting "
        f"both bracketing groups rather than interpolating a point estimate.",
        (),
        EXTREME_IOD_ANALOGUES + WEAK_IOD_ANALOGUES,
    )
