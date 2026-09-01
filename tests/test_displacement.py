"""Operational tests for displacement generation and allocation."""

import numpy as np
import pandas as pd
import pytest

from saat.displacement import AllocationModel, AllocationModelConfig, GenerationModel


def _training_data():
    months = pd.date_range("2020-01-01", periods=24, freq="MS")
    panel = pd.DataFrame(
        {
            "district": np.repeat(["bay", "gedo"], len(months)),
            "year_month": list(months) * 2,
            "rainfall_anomaly": np.tile(np.linspace(-1, 1, len(months)), 2),
            "flash_index": np.tile([0, 1, 0, 2], 12),
            "population": 100000,
            "ipc_phase": 4,
        }
    )
    flows = np.tile([0, 0, 6000, 0, 8000, 0, 0, 7000], 6)
    return panel, pd.DataFrame({"flow": flows})


def _long_panel(n_months=48, districts=("bay", "gedo", "hiiraan", "banadir"), seed=0):
    """A balanced district-month panel long enough for blocked forward-chaining CV,
    with material displacement driven by a lagged rainfall signal plus noise."""
    rng = np.random.default_rng(seed)
    months = pd.date_range("2019-01-01", periods=n_months, freq="MS")
    rows, flows = [], []
    for d_i, district in enumerate(districts):
        rain = rng.normal(0, 1, n_months)
        for t, month in enumerate(months):
            driver = rain[t - 1] if t else 0.0  # last month's rainfall anomaly
            base = 800 + 400 * d_i + rng.normal(0, 300)
            flow = max(0.0, base + (9000 if driver > 1.0 else 0.0) + rng.normal(0, 400))
            rows.append(
                {
                    "district": district,
                    "year_month": month,
                    "rainfall_anomaly": rain[t],
                    "population": 120000 + 20000 * d_i,
                }
            )
            flows.append(flow)
    panel = pd.DataFrame(rows)
    return panel, pd.DataFrame({"flow": flows})


def test_generation_excludes_circular_food_security_features():
    panel, _ = _training_data()
    features = GenerationModel().get_features(panel)
    assert not any("ipc" in column.lower() for column in features.columns)
    assert not any("fews" in column.lower() for column in features.columns)
    assert any("rainfall_anomaly_lag_1" == column for column in features.columns)


def test_generation_predicts_scaled_vulnerability_forecast():
    panel, target = _training_data()
    model = GenerationModel()
    model.fit(panel, target)
    features = model.get_features(panel)
    predictions = model.predict(features, vulnerability_multiplier=1.5)
    assert (predictions["predicted_flow"] >= 0).all()
    assert np.allclose(
        predictions["predicted_flow_scaled"], predictions["predicted_flow"] * 1.5
    )


def test_generation_rejects_negative_vulnerability_multiplier():
    panel, target = _training_data()
    model = GenerationModel()
    model.fit(panel, target)
    with pytest.raises(ValueError, match="non-negative"):
        model.predict(model.get_features(panel), vulnerability_multiplier=-1)


def test_allocation_conserves_mass_and_calculates_site_pressure():
    model = AllocationModel()
    outflows = np.array([100.0, 200.0, 300.0])
    arrivals, pressure = model.allocate_flows(
        outflows,
        destination_idp_stock=np.array([1000.0, 2000.0, 3000.0]),
        destination_population=np.array([5000.0, 6000.0, 7000.0]),
        distance_matrix=np.ones((3, 3)),
    )
    assert arrivals.sum() == pytest.approx(outflows.sum())
    assert pressure == pytest.approx(arrivals / np.array([1000.0, 2000.0, 3000.0]))


def test_allocation_rejects_incompatible_dimensions():
    with pytest.raises(ValueError, match="dimensions"):
        AllocationModel().allocate_flows(
            np.array([100.0]),
            np.array([1000.0, 2000.0]),
            np.array([5000.0, 6000.0]),
            np.ones((2, 2)),
        )


def test_generation_features_exclude_contemporaneous_outflow():
    """Material displacement is defined as outflow >= threshold, so the raw
    contemporaneous outflow column must not enter the feature matrix - only its
    explicit lags."""
    panel, _ = _long_panel()
    panel = panel.assign(outflow=np.linspace(0, 20000, len(panel)), arrivals=1.0)
    features = GenerationModel().get_features(panel)
    assert "outflow" not in features.columns
    assert "arrivals" not in features.columns
    assert {"outflow_lag_1", "outflow_lag_12"}.issubset(features.columns)


def test_blocked_cv_reports_discrimination_and_persistence_baseline():
    panel, target = _long_panel()
    model = GenerationModel()
    cv = model.fit(panel, target)
    # discrimination is reported threshold-free and against persistence, not zero
    for key in (
        "model_auc",
        "persistence_auc",
        "model_pss",
        "persistence_pss",
        "model_flow_mae",
        "persistence_flow_mae",
        "beats_persistence",
    ):
        assert key in cv
    assert cv["blocked_cv_folds"] >= 2
    assert 0.0 <= cv["model_auc"] <= 1.0
    # climatology (always "no material" at a <50% base rate) has zero PSS by construction
    assert cv["climatology_pss"] == 0.0


def test_temporal_holdout_trains_only_before_the_window():
    panel, target = _long_panel(n_months=60)
    model = GenerationModel()
    model.fit(panel, target)
    holdout = model._temporal_holdout("2022-06-01", "2022-10-31", label="probe")
    assert holdout["window"] == "2022-06-01..2022-10-31"
    assert holdout["train_obs"] > 0
    assert holdout["test_obs"] > 0
    # skill vs persistence is reported, never vs zero
    assert "model_auc" in holdout and "persistence_pss" in holdout


def test_gravity_fit_pins_unidentified_constant_terms_and_conserves_mass():
    rng = np.random.default_rng(1)
    n = 6
    od = pd.DataFrame(
        {
            "origin": np.repeat(np.arange(n), n),
            "destination": np.tile(np.arange(n), n),
            "flow": rng.integers(0, 500, n * n).astype(float),
        }
    )
    idp_stock = np.array([5000.0, 1000.0, 8000.0, 300.0, 12000.0, 900.0])
    population = np.full(n, 250000.0)  # placeholder constant -> not identifiable
    distance = np.full((n, n), 100.0)
    np.fill_diagonal(distance, 1.0)

    model = AllocationModel(AllocationModelConfig(origin_offset=True))
    stats = model.fit_gravity_model(
        od, pd.DataFrame({"idp_stock": idp_stock, "population": population}), distance
    )
    assert "dest_population" in stats["unidentified_terms"]
    assert stats["coefficient_1"] == 0.0  # population term pinned, not amplified
    assert abs(stats["coefficient_1"]) < 1e6

    outflows = np.zeros(n)
    outflows[0] = 10000.0
    arrivals, pressure = model.allocate_flows(outflows, idp_stock, population, distance)
    assert arrivals.sum() == pytest.approx(outflows.sum())
    assert pressure == pytest.approx(arrivals / idp_stock)
