"""Operational tests for balanced panel assembly."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from saat.panel import PanelAssembler, build_catchment_rainfall_panel


def test_panel_is_balanced_and_zero_fills_missing_months():
    prmn = pd.DataFrame(
        {
            "date": ["2026-01-15", "2026-03-15"],
            "origin": ["bay", "bay"],
            "destination": ["gedo", "gedo"],
            "flow": [6000, 1000],
        }
    )
    panel = PanelAssembler().assemble(
        prmn,
        districts=["bay", "gedo"],
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 3, 1),
        material_threshold=5000,
    )
    assert len(panel) == 6
    january_bay = panel[(panel.district == "bay") & (panel.year_month == "2026-01-01")].iloc[0]
    february_bay = panel[(panel.district == "bay") & (panel.year_month == "2026-02-01")].iloc[0]
    assert january_bay.outflow == 6000
    assert january_bay.is_material
    assert february_bay.outflow == 0
    assert not february_bay.is_material


def test_panel_keeps_optional_missing_features_visible():
    prmn = pd.DataFrame(
        {"date": ["2026-01-01"], "origin": ["bay"], "destination": ["gedo"], "flow": [100]}
    )
    hazard = pd.DataFrame({"district": ["bay"], "year_month": [pd.Timestamp("2026-01-01")], "flash_index": [2.0]})
    panel = PanelAssembler().assemble(prmn, hazard_df=hazard, districts=["bay", "gedo"])
    gedo = panel[panel.district == "gedo"].iloc[0]
    assert gedo.flash_index != gedo.flash_index


def test_panel_rejects_duplicate_optional_feature_keys():
    prmn = pd.DataFrame(
        {"date": ["2026-01-01"], "origin": ["bay"], "destination": ["gedo"], "flow": [100]}
    )
    hazard = pd.DataFrame(
        {
            "district": ["bay", "bay"],
            "year_month": [pd.Timestamp("2026-01-01")] * 2,
            "flash_index": [1.0, 2.0],
        }
    )
    with pytest.raises(ValueError, match="at most one row"):
        PanelAssembler().assemble(prmn, hazard_df=hazard)


def test_panel_loader_accepts_published_prmn_headers_and_counts():
    raw = pd.DataFrame(
        {
            "Month End": ["31/01/2023"],
            "Previous (Departure) District": ["Baydhaba"],
            "Current (Arrival) District": ["Jowhar"],
            "Number of Individuals": ["5,001"],
        }
    )
    from saat.panel import PRMNLoader

    loaded = PRMNLoader().load_prmn(raw)
    assert loaded.loc[0, "flow"] == 5001
    assert loaded.loc[0, "is_material"]


def test_panel_loader_reports_and_drops_invalid_endpoint_labels():
    raw = pd.DataFrame(
        {
            "Month End": ["31/01/2023", "28/02/2023"],
            "Previous (Departure) District": ["Baydhaba", "Baydhaba"],
            "Current (Arrival) District": ["Jowhar", 0],
            "Number of Individuals": ["5,001", 3],
        }
    )
    from saat.panel import PRMNLoader

    loader = PRMNLoader()
    with pytest.warns(UserWarning, match="1 PRMN rows"):
        loaded = loader.load_prmn(raw)
    assert loader.dropped_invalid_endpoint_rows == 1
    assert len(loaded) == 1


def test_ett_loader_aggregates_weekly_arrivals_to_monthly_od_flows():
    raw = pd.DataFrame(
        {
            "Date of Assessment": ["2026-06-14", "2026-06-21", "2026-07-01", "metadata"],
            "Origin_District_country": ["Baydhaba", "Baydhaba", "Baydhaba", "Baydhaba"],
            "District Name": ["Jowhar", "Jowhar", "Jowhar", "Jowhar"],
            "Total new arrivals since last week": [10, 15, 20, "#affected+idps+ind"],
        }
    )
    from saat.panel import IOMETTLoader

    loader = IOMETTLoader()
    with pytest.warns(UserWarning, match="1 ETT rows"):
        loaded = loader.load_ett(raw)
    assert loaded.flow.tolist() == [25, 20]
    assert loaded.date.dt.strftime("%Y-%m").tolist() == ["2026-06", "2026-07"]


def test_flow_merge_preserves_source_and_does_not_fill_unobserved_gap():
    from saat.panel import PanelAssembler

    merged = PanelAssembler.merge_flow_sources(
        pd.DataFrame({"date": ["2023-08-01"], "origin": ["bay"], "destination": ["gedo"], "flow": [10]}),
        pd.DataFrame({"date": ["2026-06-01"], "origin": ["bay"], "destination": ["gedo"], "flow": [20]}),
    )
    assert merged.source.tolist() == ["PRMN", "IOM_ETT"]
    assert set(merged.year_month.dt.strftime("%Y-%m")) == {"2023-08", "2026-06"}
    assert "2024-01" not in set(merged.year_month.dt.strftime("%Y-%m"))


def test_ett_loader_combines_multiple_releases():
    from saat.panel import IOMETTLoader

    frame = pd.DataFrame(
        {
            "Date of Assessment": ["2026-06-14"],
            "Origin_District_country": ["Baydhaba"],
            "District Name": ["Jowhar"],
            "Total new arrivals since last week": [10],
        }
    )
    loaded = IOMETTLoader().load_ett_resources([frame, frame])
    assert len(loaded) == 1
    assert loaded.loc[0, "flow"] == 20


def test_verified_features_join_by_district_month_without_imputation():
    from saat.panel import PanelAssembler

    panel = pd.DataFrame({"district": ["Bay", "Bay"], "date": ["2022-01-01", "2022-02-01"], "flow": [10, 20]})
    rainfall = pd.DataFrame(
        {"admin2_name": ["Bay"], "reference_period_start": ["2022-01-01"], "rainfall_anomaly_pct": [25]}
    )
    enriched = PanelAssembler.merge_verified_features(panel, rainfall_df=rainfall)
    assert enriched.loc[0, "rainfall_rainfall_anomaly_pct"] == 25
    assert pd.isna(enriched.loc[1, "rainfall_rainfall_anomaly_pct"])


class _FakeCHIRPS:
    """Deterministic stand-in for CHIRPSClient.fetch_monthly_series."""

    def fetch_monthly_series(self, start, end, points=None, bboxes=None, cache_dir=None, **kw):
        months = pd.date_range(
            pd.Timestamp(start).to_period("M").to_timestamp(),
            pd.Timestamp(end).to_period("M").to_timestamp(),
            freq="MS",
        )
        rows = []
        for i, m in enumerate(months):
            for name in (points or {}):
                rows.append({"location": name, "kind": "point",
                             "year_month": m, "rainfall_mm": 20.0 + i})
            for name in (bboxes or {}):
                rows.append({"location": name, "kind": "catchment",
                             "year_month": m, "rainfall_mm": 100.0 + 2 * i})
        return pd.DataFrame.from_records(rows)


def test_build_catchment_rainfall_panel_attaches_upstream_only_to_riverine():
    ref = pd.DataFrame(
        {
            "district": ["Belet Weyne", "Baki"],
            "adm1_name": ["Hiiraan", "Awdal"],
            "center_lat": [4.7, 10.2],
            "center_lon": [45.2, 43.5],
        }
    )
    clim = build_catchment_rainfall_panel(
        chirps_client=_FakeCHIRPS(),
        district_reference=ref,
        catchment_bboxes={"shabelle_upstream": (10.5, 7.0, 44.0, 41.0)},
        basin_regions={"shabelle_upstream": ["Hiiraan"]},
        panel_districts=["Belet Weyne", "Baki"],
        start=datetime(2020, 1, 1),
        end=datetime(2021, 12, 31),
        cache_dir=None,
    )
    bw = clim[clim["district"] == "Belet Weyne"]
    baki = clim[clim["district"] == "Baki"]
    assert (bw["is_riverine"] == 1).all()
    assert (baki["is_riverine"] == 0).all()
    # upstream rainfall present for the riverine district, zero for the other
    assert (bw["upstream_rain_mm"] > 0).any()
    assert (baki["upstream_rain_mm"] == 0).all()
    # lag columns exist and the 1-month lag matches the shifted own series
    assert "local_rain_mm_lag_1" in clim.columns
    bw = bw.sort_values("year_month").reset_index(drop=True)
    assert bw.loc[1, "local_rain_mm_lag_1"] == pytest.approx(bw.loc[0, "local_rain_mm"])
