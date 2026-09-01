"""Focused tests for raster and forecast response parsing."""

from datetime import datetime

import numpy as np
import pytest
from rasterio.transform import from_origin

from saat.sources import CHIRPSClient


def test_chirps_point_sampling_returns_daily_values(monkeypatch):
    transform = from_origin(40, 5, 1, 1)

    def fake_raster(_date):
        yield np.array([[12.5]], dtype=float), transform, -9999.0

    client = CHIRPSClient()
    monkeypatch.setattr(client, "_read_daily_raster", fake_raster)
    rainfall, dates = client.fetch_daily_rainfall(
        lat=4.5,
        lon=40.5,
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 1, 2),
    )
    assert rainfall.tolist() == [12.5, 12.5]
    assert len(dates) == 2


def test_chirps_rejects_invalid_coordinates():
    with pytest.raises(ValueError, match="geographic bounds"):
        CHIRPSClient().fetch_daily_rainfall(
            95, 40, datetime(2026, 1, 1), datetime(2026, 1, 1)
        )


def test_chirps_monthly_series_samples_points_and_bboxes(monkeypatch):
    # 10x10 grid at 1 deg, origin (40 E, 15 N): a rainfall gradient by row.
    transform = from_origin(40, 15, 1, 1)
    grid = np.tile(np.arange(10, dtype=float)[:, None] * 10.0, (1, 10))

    def fake_read(_year, _month, _cache, _region="africa"):
        return grid, transform, -9999.0

    client = CHIRPSClient()
    monkeypatch.setattr(client, "_read_monthly_raster", fake_read)
    df = client.fetch_monthly_series(
        start=datetime(2023, 1, 1),
        end=datetime(2023, 3, 1),
        points={"town": (10.5, 45.5)},
        bboxes={"basin": (15.0, 5.0, 50.0, 40.0)},
        cache_dir=None,
    )
    assert set(df["kind"]) == {"point", "catchment"}
    assert len(df) == 6  # 2 locations x 3 months
    assert (df["rainfall_mm"] >= 0).all()


def test_chirps_monthly_series_requires_a_target():
    with pytest.raises(ValueError, match="points or bboxes"):
        CHIRPSClient().fetch_monthly_series(datetime(2023, 1, 1), datetime(2023, 1, 1))
