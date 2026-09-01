# SAAT notebooks

Exploratory and diagnostic notebooks. Nothing here is part of the package or the
test suite; treat outputs as scratch.

Suggested notebooks to build against live data once credentials are in `.env`:

- `01_preflight_prmn_currency.ipynb` — resolve the PRMN currency question
  (does the HDX resource end in August 2023?) and decide whether HAPI / IOM DTM
  ETT is needed for the operational tail.
- `02_threshold_verification.ipynb` — sweep FRRIMS / GloFAS thresholds through
  `saat.verification.CostLossModel`, plot relative economic value vs FAR, and
  record the contingency table for each candidate operating point.
- `03_displacement_backtest.ipynb` — blocked forward-chaining CV of the Stage 1
  generation model; skill vs persistence and climatology on the 2023 Deyr flood
  and 2022 drought peak holdouts.
- `04_economic_sensitivity.ipynb` — second-order irrigation penalty and RVF
  conditional probabilities as headline sensitivities.

Keep credentials out of notebook cells and outputs.
