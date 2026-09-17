# SAAT: Somalia Anticipatory Action Trigger Tool

A Python package that turns El Niño flood forecasts into a monetised, displacement-aware impact model for Somalia: expected casualties (urban Mogadishu and riverine), displacement caseload, riverine agricultural loss, and Mogadishu productivity loss from urban pluvial flooding.

## Critical Directional Premise

**El Niño in Somalia is a flood signal, not a drought signal.**

The Horn of Africa teleconnection runs opposite to southern and eastern Africa. El Niño, especially coupled with a positive Indian Ocean Dipole, enhances the October to December Deyr rains. La Niña suppresses them.

- Somalia's 2020–2023 near-famine was a **La Niña** sequence, five failed seasons.
- The catastrophic late-2023 Belet Weyne, Luuq and Jowhar floods were an **El Niño plus positive IOD** sequence.

## What This Models

A risk map answers "where is exposure high." This tool goes one step further and
puts a number on the consequence: how many people are expected to die, how many
are expected to be displaced, and how much money is expected to be lost, for a
given flood forecast.

Four impact channels, each in its own module:

1. **Casualties** (`casualties.py`) — expected deaths in two distinct settings
   modelled separately, because the causal pathway differs: **urban pluvial**
   (Mogadishu, where poor drainage lets rainfall pond in streets and naked/exposed
   low-voltage wiring adds an electrocution risk with no riverine equivalent) and
   **riverine** (Shabelle/Juba gauge towns, where drowning risk is governed by
   depth and by the routing-lag warning lead time from `hazard.py`).
2. **Displacement** (`displacement.py`) — two-stage generation + gravity
   allocation model forecasting who leaves and where they go.
3. **Agricultural loss** (`economic.py`) — direct crop loss and second-order
   irrigation damage in the riverine flood zone (Shabelle/Juba).
4. **Urban productivity loss** (`urban_flood.py`) — the hardest of the four to
   model credibly: Mogadishu's road-network disruption (stagnant water cutting
   arterial roads such as Airport Road / Aden Adde corridor) and business
   interruption from flooded market premises.

None of the four is calibrated for Somalia yet; every module says so explicitly
in its docstrings and flags each placeholder assumption.

### Companion documents (`docs/`)

- [`docs/el-nino-preparedness-brief.html`](docs/el-nino-preparedness-brief.html) —
  "The Somalia El Niño Anticipatory Action", a ministerial brief authored by Hassan Mumin:
  the flood premise with a world teleconnection map, an exposure map of the river
  corridor, an **interactive 2026 Deyr displacement and cash-planning scenario**
  (reference event, asset-depletion multiplier, transfer value; live district/timing/
  map panels), the readiness ladder, and a decisions-and-owners table. Real ONI/DMI,
  PRMN, geoBoundaries and Natural Earth data; displacement figures are scenario or
  analogue outputs from stated, uncalibrated assumptions.
  **Not yet updated for the casualties/urban-productivity revamp** — the old
  economic-loss-channel section (crop/livestock/irrigation/recovery) and the
  cost-loss "Trigger Economics" widget have been removed from the brief, but it
  does not yet describe the new casualties.py / urban_flood.py channels either.
  Hosted: <https://claude.ai/code/artifact/f79d37b4-ec0c-4f0e-b60a-c6a61c955a20>

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/hassanmumin-collab/Somalia-Anticipatory-Action-Trigger-Tool-SAAT-.git
cd Somalia-Anticipatory-Action-Trigger-Tool-SAAT-

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package with all extras (dev tooling + geospatial + plotting)
pip install -e ".[full]"

# Verify installation
saat --help
```

### Running Offline Self-Tests

```bash
# No network or credentials required
saat demo
```

This runs all module self-tests with synthetic data.

### System Check

```bash
# Check Python version, packages, config, and network reachability
saat doctor
```

## Architecture

The impact pipeline runs hazard detection into four consequence modules:

```
hazard.py (routing lag, AMC/runoff) ──┬─→ casualties.py   (urban + riverine deaths)
                                       ├─→ displacement.py (caseload + allocation)
                                       ├─→ economic.py     (riverine agricultural loss)
                                       └─→ urban_flood.py  (Mogadishu productivity loss)
```

`hazard.py`'s routing lag (~4 days Shabelle, ~6 days Juba) is not just usable
lead time for logistics — it is the warning lead time that `casualties.py`
uses to discount riverine drowning mortality.

## Core Modules

- **casualties.py** — Expected deaths: urban (Mogadishu drowning + electrocution) and riverine (drowning, lead-time discounted)
- **hazard.py** — Catchment routing (lag-and-accumulate), SCS curve number runoff, AMC classification
- **displacement.py** — Two-stage generation model (classifier + regressor), gravity allocation
- **economic.py** — Riverine agricultural loss: direct crop loss, second-order irrigation damage
- **urban_flood.py** — Mogadishu productivity loss: road-network disruption, business interruption
- **metrics.py** — Contingency-table forecast verification metrics (POD/FAR/PSS/CSI)
- **panel.py** — Data aggregation from CKAN/HAPI, PRMN loader, district-month assembly
- **sources.py** — CHIRPS, GloFAS, C3S, FRRIMS, ACLED, ONI/DMI scrapers
- **cli.py** — Command-line interface

## Commands

```bash
saat doctor       # Check Python, config, packages, credentials, network
saat preflight    # Which sources are alive and how fresh
saat demo         # Run offline self-tests (no credentials needed)
saat build-panel  # Assemble district-month panel
```

## Configuration

Geography, gauges, and zone definitions are in `config/geography.yml`, never
hardcoded in the model code. This ensures:

1. **Visibility** — anyone can read the gauge/catchment/zone definitions and argue with them
2. **Auditability** — changes leave an auditable trail

See `config/geography.yml` for the complete specification of:
- River gauges and routing lags (Shabelle, Juba) that feed `hazard.py` and the
  warning lead time used by `casualties.py`
- Catchment bounding boxes for upstream rainfall accumulation (placeholders,
  pending HydroSHEDS basin polygons)
- IDP settlements and livelihood zones, including the `urban_informal`
  Mogadishu/Baidoa/Kismayo zone flagged for "inadequate drainage"

## Data Sources

All sources are open or free-registration:

| Source | Access | Purpose |
|--------|--------|---------|
| CHIRPS | open | Rainfall (including upstream Ethiopian catchments) |
| NOAA CPC ONI, BoM DMI | open | ENSO and IOD conditioning |
| ICPAC | open | Seasonal outlook |
| Copernicus CDS | free key | GloFAS discharge, C3S seasonal forecast |
| Copernicus CDSE | free key | Sentinel-1 SAR flood extent |
| FAO SWALIM FRRIMS | open, scraped | River stage (drives the routing lag / warning lead time) |
| HDX CKAN | open | PRMN, IPC, CCCM IDP sites, boundaries, WorldPop |
| HDX HAPI | free app identifier | Standardised IDP indicators, live tail |
| ACLED | free key | Conflict events |
| FSNAU bulletins | published | Production baselines, prices, terms of trade |

Create `.env` from `.env.example` and fill in API keys.

## Current Model Status (2026-09-01)

| Component | State | Evidence |
|---|---|---|
| Hazard: routing + inverted-AMC runoff | **Working** on synthetic input | `saat demo` |
| Displacement panel | **Built from real PRMN** | 7,084 rows = 77 districts x 92 months (2016-01..2023-08); 4.0% material base rate |
| CHIRPS rainfall features | **Wired** — monthly Africa CHIRPS, local (district centroid) + upstream (Ethiopian-highland catchment bbox) rainfall & lags | `panel.build_catchment_rainfall_panel`; 76/77 districts, 31 riverine |
| Displacement Stage 1 (generation) | **Fitted + blocked-CV validated on PRMN + CHIRPS; still does NOT beat persistence on event PSS** | see below |
| Displacement Stage 2 (gravity) | **Fitter runs on 1,283 real OD pairs; needs real distances + WorldPop** | see below |
| Casualties module (urban + riverine) | **Working**, mortality curves `null` | `saat demo` |
| Economic module (riverine agriculture) | **Working**, calibration params `null` | `saat demo` |
| Urban flood module (Mogadishu productivity) | **Working**, traffic/business values `null` | `saat demo` |

**Stage 1 blocked forward-chaining CV** (4 folds, 3-month embargo, 5,621 held-out
district-months). Features: local & upstream monthly rainfall + 1-3 month lags
(CHIRPS), calendar month, district, own outflow lagged 1 & 12 months. Anomalies
are vs the **within-sample** (2016-2023) month-of-year mean, *not* the WMO
1991-2020 baseline.

| Metric | PRMN only | PRMN + CHIRPS | Persistence | Climatology |
|---|---|---|---|---|
| Discrimination AUC | 0.75 | **0.78** | 0.66 | 0.50 |
| Event PSS (at base-rate operating point) | 0.14 | 0.21 | **0.31** | 0.00 |
| Caseload MAE | 1,309 | **1,270** | 1,741 | 1,500 |

- Adding CHIRPS **improved risk ranking (AUC 0.75 → 0.78)** and **caseload
  sharpness (27% better MAE than persistence, 15% better than climatology)**.
- It still **does not beat persistence on event PSS** at the operating point —
  the classifier is under-confident on rare events. The 2022 drought-peak holdout
  clears the bar (`beats_persistence = True`); the 2023 flood-season holdout does
  not.
- In the 2023 Gu flood the upstream feature is doing its job: Belet Weyne's
  upstream Shabelle catchment rainfall reads **+87 mm above the in-sample March
  mean** — the Ethiopian-highland rain that produced the ~257,000-person Belet
  Weyne displacement, invisible to a local-rainfall-only model.

**Conclusion: still not deployable.** Remaining gaps, in likely order of impact:
HydroSHEDS basin polygons in place of the placeholder catchment bboxes (a bbox
over the Bale highlands includes terrain that does not drain to the Shabelle);
sub-monthly routing to keep the 4-6 day lead time; a 1991-2020 anomaly baseline;
and the other feature families — flash index, WRSI/NDVI, cereal price /
terms-of-trade (FSNAU), ACLED conflict.

**Stage 2:** the Poisson gravity fitter is now numerically robust (converges on
the standardised design, pins non-identifiable terms, conserves mass) and runs on
the 1,283 real origin-destination pairs. A meaningful fit still needs a real
inter-district **distance matrix** (district centroids from the COD boundaries)
and **WorldPop population**; with constant placeholders for both, distance and the
same-region term are collinear and the destination-stock coefficient is not
trustworthy.

## Verification Required Before Operational Use

This tool is a decision-support scaffold, not a calibrated operational system. Every
box below must be checked, by the named counterpart, before any output is used to
brief decision-makers or size a response.

- [ ] **Gauge high-risk levels.** All `high_risk_level_m` in `config/geography.yml`
      are `null`. Populate each from FRRIMS station metadata; these drive both flood
      detection in `hazard.py` and the warning lead time fed into
      `casualties.RiverineFloodCasualties`.
- [ ] **Drowning mortality curves.** `casualties.DrowningRiskCurve` ships with no
      default: every call site must supply an explicit depth-mortality curve for
      the urban and riverine settings. Run casualty estimates as a range across
      plausible curves, not a point estimate, until MOH/WHO EWARS/DMS data exists.
- [ ] **Electrocution contact-fatality rate.** No published Somalia-specific rate
      for electrocution from contact with electrified urban floodwater exists.
      `ElectrocutionExposure.exposed_wiring_prevalence` and `contact_fatality_rate`
      need a Mogadishu electrical-infrastructure survey (e.g. with Benadir
      Regional Administration / electricity providers).
- [ ] **Mogadishu traffic and business values.** `RoadSegment.daily_traffic_value_usd`
      and `BusinessInterruptionLoss.daily_business_value_usd` are placeholders.
      Populate from a transport/trade survey (Benadir RA, Mogadishu Port/Airport
      authorities, market associations) before reporting a headline productivity-loss figure.
- [ ] **PRMN currency.** Run `saat preflight`. Confirm whether the HDX PRMN
      resource ends in August 2023. If so, wire HAPI or IOM DTM ETT for the
      operational tail before the displacement forecast is used live.
- [ ] **Catchment definitions.** Replace the placeholder bounding boxes with
      HydroSHEDS basin polygons before driving the routing model; a bbox over the
      Bale highlands includes terrain that does not drain to the Shabelle.
- [ ] **Inverted AMC-I uplift.** The curve-number inversion for crusted
      semi-arid soils is a modelling judgement with no Somalia-specific
      calibration. Have it reviewed against local impact records.
- [ ] **Submergence damage curves.** Run crop losses as a range across plausible
      curves, not a point estimate, until a Somalia calibration exists.
- [ ] **Second-order irrigation penalty.** Placeholder. Treat as a headline
      sensitivity that decides whether the event is a one- or two-season shock.
- [ ] **Displacement bias corrections.** Decide `coverage_weight` (PRMN is a
      monitoring network, not a census) and `vulnerability_multiplier` (2026
      asset depletion) explicitly. Running with the neutral defaults is itself a
      recorded decision.
- [ ] **Blocked-CV skill.** Confirm the Stage 1 model beats persistence and
      climatology on the 2023 Deyr and 2022 drought holdouts. If it cannot beat
      persistence, do not deploy it.

## Assumptions Register

**Verification required before operational use.** Each assumption is labelled by what supports it. Do not upgrade any to fact.

### Structural Assumptions

- **Inverted AMC-I runoff treatment.** Physically motivated by surface crusting on semi-arid soils, consistent with observed 2023 flash flood behaviour. **No Somalia-specific calibration confirmed.** The uplift factor is a modelling judgement.

### Casualty Assumptions

- **Drowning depth-mortality curves (urban and riverine).** Shapes from general flood-mortality literature. **No published Somalia calibration confirmed.** `casualties.DrowningRiskCurve` requires an explicit curve at every call site rather than a hidden default; run casualty estimates as a range.

- **Electrocution contact-fatality rate.** Judgemental. **No published Somalia-specific rate confirmed** for electrocution from contact with electrified urban floodwater; needs a Mogadishu electrical-infrastructure survey.

- **Warning-lead-time mortality mitigation.** Judgemental slope (`DrowningExposure.lead_time_mitigation_fraction_per_hour`, capped by `max_lead_time_mitigation_fraction`). No Somalia-specific evacuation-compliance data confirms how much a given lead time actually reduces riverine drowning risk.

### Economic Assumptions

- **Submergence damage curves.** Shapes from general agronomic tolerance ranges. **No published Somalia calibration confirmed.** Run losses as a range across plausible curves, not a point estimate.

- **Second-order yield penalty.** Placeholder. **No published Somalia estimate confirmed.** Headline sensitivity.

- **Mogadishu traffic and business values.** `RoadSegment.daily_traffic_value_usd` and `BusinessInterruptionLoss.daily_business_value_usd` are placeholders. **No published transport/trade survey confirmed.** The hardest of the four channels to model credibly: informal-sector activity along corridors like Airport Road is not well captured by any existing survey.

- **Reroutable fraction and detour cost.** Judgemental (`RoadClosure.reroutable_fraction`, `detour_cost_multiplier`). No Somalia-specific rerouting behaviour survey.

### Data Assumptions

- **Vulnerability multiplier.** Judgemental scenario parameter, neutral by default. Exposes the 2026 asset-depletion effect from drought-to-flood compounding as an arguable parameter.

- **PRMN currency. RESOLVED (2026-09-01).** The HDX dataset
  `somalia-internally-displaced-persons-idps` (UUID
  `475e2e3c-3cec-4961-b73c-d8e68791ce60`) reports `dataset_date`
  `2016-01-01 TO 2023-08-31`; the visible resource is
  `SOM_UNHCR-PRMN-Displacement-Dataset-August-2023.xlsx` (62,471 rows, last
  modified 2023-10-16). **The panel is a hindcast training set only.** The
  operational tail (September 2023 onward) requires HAPI (`affected-people/idps`,
  free app identifier) or IOM DTM ETT. `src/saat/panel.py::IOMETTLoader` is the
  ingestion path for the latter.

- **Gauge thresholds.** All `high_risk_level_m` in `config/geography.yml` are null pending FRRIMS station metadata.

- **Catchment bounding boxes.** Placeholders (`config/geography.yml`). The
  monthly-CHIRPS upstream-rainfall feature currently averages over these rectangles;
  replace with HydroSHEDS basin polygons — a bbox over the Bale highlands includes
  terrain that does not drain to the Shabelle.

- **In-sample rainfall anomaly baseline.** `local_rain_anom_insample` /
  `upstream_rain_anom_insample` are relative to the 2016-2023 month-of-year mean,
  not the WMO 1991-2020 climatology. Extend the CHIRPS record before treating
  these as standardised anomalies.

- **District centroids / name crosswalk.** Local rainfall is sampled at COD
  admin-2 polygon centroids; PRMN↔COD name mismatches are handled by
  `district_name_aliases` in `config/geography.yml`, and three districts absent
  from the COD layer (Banadir, Badhan, Dhahar) use placeholder coordinates.

- **Admin-1 river-basin map.** `river_basin_regions` assigns whole admin-1 regions
  to an upstream catchment; refine to the actual riverine districts once basin
  polygons are in.

### Bias in Training Data

- **PRMN monitoring vs. census.** PRMN is a humanitarian monitoring network, not a census. Coverage correlates with humanitarian presence, so Al-Shabaab-controlled and access-constrained areas are systematically undercounted. A model fitted on it learns where displacement is **observed**, which is not where displacement **occurs**. Run with explicit `coverage_weight` correction or document that running without one is a decision.

- **Conflict feature entanglement.** Conflict both drives displacement and suppresses its observation. Any coefficient on ACLED conflict events is a mixture of the two and cannot be separated without external information.

## Testing

```bash
# Run test suite
pytest

# Run with coverage
pytest --cov=src/saat

# Run specific test file
pytest tests/test_casualties.py
```

### Test Philosophy

Tests assert **operational properties**, not implementation detail:

- A drowning curve requires an explicit setting match; a riverine curve against an urban exposure raises
- Warning lead time reduces riverine drowning deaths, but mitigation is capped, not unbounded
- A non-monotonic mortality curve raises rather than silently interpolating nonsense
- Reroutable road traffic loses only its detour cost, not its full value
- Desiccated soil yields a higher runoff coefficient than normal soil
- Routing lag shifts the upstream signal forward by exactly the lag
- The generation panel is balanced (all months × districts, including zero-displacement months)
- Column resolution failure raises with the observed headers in the message

## Development

```bash
# Format with black
black src/ tests/

# Lint with ruff
ruff check src/ tests/

# Type check with mypy
mypy src/

# All in one
make lint
```

## Project Structure

```
saat/
├── .vscode/
│   ├── settings.json
│   ├── launch.json
│   ├── tasks.json
│   └── extensions.json
├── config/
│   └── geography.yml
├── src/saat/
│   ├── __init__.py
│   ├── config.py
│   ├── cli.py
│   ├── casualties.py
│   ├── hazard.py
│   ├── displacement.py
│   ├── economic.py
│   ├── urban_flood.py
│   ├── metrics.py
│   ├── panel.py
│   └── sources.py
├── tests/
│   └── test_*.py
├── notebooks/
├── .env.example
├── .gitignore
├── pyproject.toml
├── Makefile
└── README.md
```

## Key References

- **Anticipatory action frameworks:** WFP, FEWS NET, and OCHA anticipatory action guidance.

- **Somalia flood forecasting:** ICPAC seasonal outlooks, FAO SWALIM rainfall monitoring.

- **Displacement modelling:** PRMN documentation, gravity models in human migration literature.

- **Flood mortality:** general depth-duration flood-mortality literature (no Somalia-specific
  source yet identified); WHO EWARS and Somalia MOH mortality surveillance for eventual
  calibration of `casualties.py`'s drowning and electrocution curves.

## License

MIT License. See LICENSE file for details.

## Contact

For questions or issues, contact the SAAT team.
