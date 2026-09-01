# SAAT: Somalia Anticipatory Action Trigger Tool

A Python package that turns El Niño flood forecasts into pre-agreed, verifiable financing triggers, with displacement caseload forecasting and monetised economic loss.

## Critical Directional Premise

**El Niño in Somalia is a flood signal, not a drought signal.**

The Horn of Africa teleconnection runs opposite to southern and eastern Africa. El Niño, especially coupled with a positive Indian Ocean Dipole, enhances the October to December Deyr rains. La Niña suppresses them.

- Somalia's 2020–2023 near-famine was a **La Niña** sequence, five failed seasons.
- The catastrophic late-2023 Belet Weyne, Luuq and Jowhar floods were an **El Niño plus positive IOD** sequence.

## What Makes This a Trigger Tool

A risk map answers "where is exposure high." A trigger answers "at what forecast value do I release money, for which action, at what lead time, and what is my false alarm cost."

This tool implements the **cost-loss decision model**: given the cost of action, loss if the event occurs unmitigated, mitigation effectiveness, and climatological base rate, it finds the operating point that minimises expected expense subject to operational constraints.

Key principle: **The optimal threshold is generally NOT the one maximising skill scores.** When action is cheap relative to avoided loss, the optimum tolerates a high false alarm ratio. A trigger with FAR 0.67 can have relative economic value 0.76.

### Companion documents (`docs/`)

- [`docs/el-nino-preparedness-brief.html`](docs/el-nino-preparedness-brief.html) —
  "Somalia El Niño Anticipatory Action", a ministerial brief authored by Hassan Mumin:
  the flood premise with a world teleconnection map, an exposure map of the river
  corridor, an **interactive 2026 Deyr displacement and cash-planning scenario**
  (reference event, asset-depletion multiplier, transfer value; live district/timing/
  map panels), the four economic loss channels each with its own chart and an
  interactive Rift Valley Fever probability chain, an embedded Trigger Economics
  module, the readiness ladder, and a decisions-and-owners table. Real ONI/DMI, PRMN,
  geoBoundaries and Natural Earth data; economic and displacement figures are scenario
  or analogue outputs from stated, uncalibrated assumptions.
  Hosted: <https://claude.ai/code/artifact/f79d37b4-ec0c-4f0e-b60a-c6a61c955a20>
- [`docs/trigger-economics.html`](docs/trigger-economics.html) — an interactive page
  that runs this exact cost-loss model on synthetic data: move `C`, `L`, `f`, `s` and
  watch the optimal release threshold, its contingency table, and its relative economic
  value respond. Built for showing the working group *why* the threshold is a decision,
  not a skill-score.
  Hosted: <https://claude.ai/code/artifact/5e61bd40-489f-40e3-808b-1f0cffee0abf>

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

Four trigger tiers, each specifying indicator, source, threshold, lead time, combination logic, actions, envelope share, and deactivation condition:

| Tier | Lead Time | Purpose | Key Indicators |
|------|-----------|---------|-----------------|
| 0 | 60–120 days | Seasonal readiness | ICPAC ≥0.45, C3S ≥+25%, ONI ≥+1.0 & DMI ≥+0.4 |
| 1 | 10–30 days | Sub-seasonal readiness | ECMWF/GEFS ≥80th percentile, AMC-III or AMC-I |
| 2 | 7–21 days | Displacement caseload | District outflow ≥90th percentile, arrivals ≥20% IDP site |
| 3 | 1–7 days | Action | FRRIMS ≥ high-risk level, GloFAS fallback |

## Core Modules

- **verification.py** — Cost-loss decision model, threshold optimization, contingency metrics
- **trigger.py** — Tier evaluation, fail-loud data status mechanism
- **hazard.py** — Catchment routing (lag-and-accumulate), SCS curve number runoff, AMC classification
- **displacement.py** — Two-stage generation model (classifier + regressor), gravity allocation
- **economic.py** — Crop loss, RVF/export ban, irrigation damage, recovery upside, food security
- **panel.py** — Data aggregation from CKAN/HAPI, PRMN loader, district-month assembly
- **sources.py** — CHIRPS, GloFAS, C3S, FRRIMS, ACLED, ONI/DMI scrapers
- **cli.py** — Command-line interface

## Commands

```bash
saat doctor       # Check Python, config, packages, credentials, network
saat preflight    # Which sources are alive and how fresh
saat demo         # Run offline self-tests (no credentials needed)
saat build-panel  # Assemble district-month panel
saat verify       # Optimize threshold against historical record
saat evaluate     # Run engine over current readings
```

## Configuration

Trigger definitions are in `config/triggers.yml`, never in code. This ensures:

1. **No discretion at activation time** — thresholds are pre-set in config with verification evidence attached
2. **Visibility** — anyone can read the decision rules and argue with them
3. **Auditability** — changes leave an auditable trail

### Example Trigger Configuration

See `config/triggers.yml` for the complete specification of:
- Which indicators to evaluate
- Source and ingest method
- Threshold value and rationale
- Combination logic (AND/OR/majority)
- Actions triggered and envelope share
- Deactivation condition
- Cost-loss parameters for verification

## Data Sources

All sources are open or free-registration:

| Source | Access | Purpose |
|--------|--------|---------|
| CHIRPS | open | Rainfall (including upstream Ethiopian catchments) |
| NOAA CPC ONI, BoM DMI | open | ENSO and IOD conditioning |
| ICPAC | open | Seasonal outlook |
| Copernicus CDS | free key | GloFAS discharge, C3S seasonal forecast |
| Copernicus CDSE | free key | Sentinel-1 SAR flood extent |
| FAO SWALIM FRRIMS | open, scraped | River stage (operational trigger source) |
| HDX CKAN | open | PRMN, IPC, CCCM IDP sites, boundaries, WorldPop |
| HDX HAPI | free app identifier | Standardised IDP indicators, live tail |
| ACLED | free key | Conflict events |
| FSNAU bulletins | published | Production baselines, prices, terms of trade |

Create `.env` from `.env.example` and fill in API keys.

## Current Model Status (2026-09-01)

| Component | State | Evidence |
|---|---|---|
| Cost-loss verification engine | **Working** | `pytest`; `saat demo` |
| Trigger engine (fail-loud, 4 tiers) | **Working**, thresholds `null` | `config/triggers.yml` |
| Hazard: routing + inverted-AMC runoff | **Working** on synthetic input | `saat demo` |
| Displacement panel | **Built from real PRMN** | 7,084 rows = 77 districts x 92 months (2016-01..2023-08); 4.0% material base rate |
| CHIRPS rainfall features | **Wired** — monthly Africa CHIRPS, local (district centroid) + upstream (Ethiopian-highland catchment bbox) rainfall & lags | `panel.build_catchment_rainfall_panel`; 76/77 districts, 31 riverine |
| Displacement Stage 1 (generation) | **Fitted + blocked-CV validated on PRMN + CHIRPS; still does NOT beat persistence on event PSS** | see below |
| Displacement Stage 2 (gravity) | **Fitter runs on 1,283 real OD pairs; needs real distances + WorldPop** | see below |
| Economic module | **Working**, calibration params `null` | `saat demo` |

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
box below must be checked, by the named counterpart, before any trigger in
`config/triggers.yml` is used to release money.

- [ ] **Gauge high-risk levels.** All `high_risk_level` / `high_risk_level_m` in
      `config/triggers.yml` and `config/geography.yml` are `null`. Populate each
      from FRRIMS station metadata and confirm with the SoDMA–WFP working group
      that it matches the existing SoDMA action trigger **exactly** (Tier 3 must
      not diverge from the operational framework).
- [ ] **Cost-loss parameters.** Every tier's `cost_action`, `loss_event`,
      `mitigation_effectiveness` and `climatological_base_rate` is `null`. Set
      `C`, `L` with OCHA/SoDMA; `f` from AA programme evaluation; `s` from the
      1991–2020/2025 OND flood frequency. Then run `saat verify` and confirm
      `C/L < f` (feasible) and relative economic value `> 0` at the chosen
      operating point.
- [ ] **PRMN currency.** Run `saat preflight`. Confirm whether the HDX PRMN
      resource ends in August 2023. If so, wire HAPI or IOM DTM ETT for the
      operational tail before Tier 2 is used live.
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
- [ ] **RVF conditional probabilities.** Rest on 1997–98 and 2006–07 only.
      Always report conditional loss alongside expected loss.
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

### Economic Assumptions

- **Submergence damage curves.** Shapes from general agronomic tolerance ranges. **No published Somalia calibration confirmed.** Run losses as a range across plausible curves, not a point estimate.

- **Second-order yield penalty.** Placeholder. **No published Somalia estimate confirmed.** Headline sensitivity.

- **Mitigation effectiveness.** Judgemental. Published AA cost-benefit studies vary widely and few are Somalia-specific.

- **RVF conditional probabilities.** Rest on a small number of reference events (1997-98, 2006-07). Report conditional loss alongside expected loss.

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

- **Gauge thresholds.** All null pending FRRIMS station metadata. Confirm the high-risk level matches the SoDMA action trigger exactly.

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
pytest tests/test_verification.py
```

### Test Philosophy

Tests assert **operational properties**, not implementation detail:

- A cheap action with FAR > 0.5 still returns relative economic value > 0.5
- `C/L >= f` raises an error rather than returning a threshold
- An unsatisfiable POD/FAR constraint raises rather than silently relaxing
- Missing data yields `UNEVALUABLE`, not `INACTIVE`
- An absent tier produces an escalation, not silence
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
│   ├── geography.yml
│   └── triggers.yml
├── src/saat/
│   ├── __init__.py
│   ├── config.py
│   ├── cli.py
│   ├── verification.py
│   ├── trigger.py
│   ├── hazard.py
│   ├── displacement.py
│   ├── economic.py
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

- **Cost-loss decision model:** Mason, I. (1982). A model for assessment of weather forecasts. Australian Meteorological Magazine, 30(4), 291-303.

- **Trigger frameworks:** WFP, FEWS NET, and OCHA anticipatory action guidance.

- **Somalia flood forecasting:** ICPAC seasonal outlooks, FAO SWALIM rainfall monitoring.

- **Displacement modelling:** PRMN documentation, gravity models in human migration literature.

## License

MIT License. See LICENSE file for details.

## Contact

For questions or issues, contact the SAAT team.
