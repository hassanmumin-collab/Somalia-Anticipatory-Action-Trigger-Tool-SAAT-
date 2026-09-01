"""
Data source clients for SAAT.

Clients for:
- CHIRPS: Rainfall (including upstream Ethiopian catchments)
- GloFAS: Discharge (fallback for FRRIMS when gauge is down)
- C3S/SEAS5: Seasonal climate forecast
- FRRIMS: River stage (primary trigger source)
- ACLED: Conflict events
- NOAA CPC ONI, BoM DMI: ENSO and IOD conditioning

All sources are open or free-registration. No partnership agreement needed to start.

Reference: Section 10 of the build prompt.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import requests
from io import StringIO
from gzip import decompress
from pathlib import Path
import tempfile


def _get(url: str, timeout: int = 30, **kwargs):
    """Make an HTTP request with a consistent timeout and error handling."""
    response = requests.get(url, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response


def _create_cds_client(api_key: str):
    """Create the official CDS client from a configured key."""
    import cdsapi

    return cdsapi.Client(key=api_key, quiet=True)


def _read_forecast_at_point(path: Path, coordinates: Tuple[float, float], lead_days: int):
    """Read discharge and probability variables from a downloaded GloFAS NetCDF."""
    import xarray as xr

    latitude, longitude = coordinates
    with xr.open_dataset(path) as dataset:
        discharge_name = next(
            (name for name in dataset.data_vars if "discharge" in name.lower()), None
        )
        probability_name = next(
            (name for name in dataset.data_vars if "exceed" in name.lower() and "prob" in name.lower()),
            None,
        )
        if discharge_name is None or probability_name is None:
            raise ValueError(
                "GloFAS NetCDF must contain discharge and exceedance-probability variables"
            )
        discharge = dataset[discharge_name]
        probability = dataset[probability_name]
        for dimension in ("latitude", "lat"):
            if dimension in discharge.dims:
                discharge = discharge.sel({dimension: latitude}, method="nearest")
                probability = probability.sel({dimension: latitude}, method="nearest")
                break
        for dimension in ("longitude", "lon"):
            if dimension in discharge.dims:
                discharge = discharge.sel({dimension: longitude}, method="nearest")
                probability = probability.sel({dimension: longitude}, method="nearest")
                break
        discharge_values = np.asarray(discharge).reshape(-1)[:lead_days]
        probability_values = np.asarray(probability).reshape(-1)[:lead_days]
    if len(discharge_values) < lead_days or len(probability_values) < lead_days:
        raise ValueError("GloFAS response contains fewer values than requested lead_days")
    return discharge_values.astype(float), probability_values.astype(float)


def _read_precipitation_anomaly(path: Path) -> float:
    """Read a verified anomaly variable from a C3S NetCDF response."""
    import xarray as xr

    with xr.open_dataset(path) as dataset:
        anomaly_name = next(
            (name for name in dataset.data_vars if "anom" in name.lower()), None
        )
        if anomaly_name is None:
            raise ValueError(
                "C3S response contains precipitation but no anomaly variable; "
                "provide a verified climatology dataset before calculating anomalies"
            )
        value = float(dataset[anomaly_name].mean(skipna=True).values)
    if not np.isfinite(value):
        raise ValueError("C3S anomaly response contained no finite values")
    return value


@dataclass
class CHIRPSClient:
    """Client for CHIRPS rainfall data (data.chc.ucsb.edu)."""

    base_url: str = "https://data.chc.ucsb.edu"
    timeout_seconds: int = 60

    def _daily_raster_url(self, date: datetime) -> str:
        """Return the published CHIRPS daily 0.05-degree GeoTIFF URL."""
        return (
            f"{self.base_url.rstrip('/')}/products/CHIRPS-2.0/global_daily/tifs/p05/"
            f"{date:%Y}/chirps-v2.0.{date:%Y.%m.%d}.tif.gz"
        )

    def _read_daily_raster(self, date: datetime):
        """Download and open one CHIRPS raster in memory."""
        import rasterio
        from rasterio.io import MemoryFile

        response = _get(self._daily_raster_url(date), timeout=self.timeout_seconds)
        with MemoryFile(decompress(response.content)) as memory_file:
            with memory_file.open() as raster:
                yield raster.read(1), raster.transform, raster.nodata

    def fetch_daily_rainfall(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Fetch daily rainfall at point location.

        Args:
            lat: Latitude
            lon: Longitude
            start_date: Start date
            end_date: End date

        Returns:
            (rainfall_mm_array, dates_array)

        Raises:
            NotImplementedError: Network fetch not yet implemented
        """
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("lat/lon are outside valid geographic bounds")
        rainfall = []
        dates = []
        import rasterio

        for date in pd.date_range(start_date, end_date, freq="D"):
            date_value = date.to_pydatetime()
            try:
                raster_data = next(self._read_daily_raster(date_value))
            except requests.HTTPError as error:
                raise RuntimeError(f"CHIRPS raster unavailable for {date_value:%Y-%m-%d}: {error}") from error
            values, transform, nodata = raster_data
            row, column = rasterio.transform.rowcol(transform, lon, lat)
            value = values[row, column]
            rainfall.append(np.nan if nodata is not None and value == nodata else float(value))
            dates.append(date_value)
        return np.asarray(rainfall, dtype=float), np.asarray(dates, dtype="datetime64[ns]")

    def fetch_catchment_rainfall(
        self,
        catchment_bbox: Tuple[float, float, float, float],
        start_date: datetime,
        end_date: datetime,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Fetch spatially-averaged rainfall over catchment bbox.

        Args:
            catchment_bbox: (north, south, east, west)
            start_date: Start date
            end_date: End date

        Returns:
            (daily_rainfall_mm_array, dates_array)

        Raises:
            NotImplementedError: Network fetch not yet implemented
        """
        north, south, east, west = catchment_bbox
        if south >= north or west >= east:
            raise ValueError("catchment_bbox must be (north, south, east, west)")
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        rainfall = []
        dates = []
        import rasterio

        for date in pd.date_range(start_date, end_date, freq="D"):
            date_value = date.to_pydatetime()
            try:
                values, transform, nodata = next(self._read_daily_raster(date_value))
            except requests.HTTPError as error:
                raise RuntimeError(f"CHIRPS raster unavailable for {date_value:%Y-%m-%d}: {error}") from error
            window = rasterio.windows.from_bounds(west, south, east, north, transform=transform)
            rows, columns = window.toslices()
            sample = values[rows, columns].astype(float)
            if nodata is not None:
                sample[sample == nodata] = np.nan
            rainfall.append(float(np.nanmean(sample)) if np.isfinite(sample).any() else np.nan)
            dates.append(date_value)
        return np.asarray(rainfall, dtype=float), np.asarray(dates, dtype="datetime64[ns]")

    # ------------------------------------------------------------------
    # Monthly product (used for the district-month displacement panel)
    # ------------------------------------------------------------------

    def _monthly_raster_url(self, year: int, month: int, region: str = "africa") -> str:
        """Published CHIRPS monthly 0.05-degree GeoTIFF URL.

        ``region='africa'`` is the Africa subset (~4.5 MB/month) and covers both
        Somalia and the Ethiopian highland catchments; ``region='global'`` is the
        full grid (~15 MB/month).
        """
        subset = "africa_monthly" if region == "africa" else "global_monthly"
        return (
            f"{self.base_url.rstrip('/')}/products/CHIRPS-2.0/{subset}/tifs/"
            f"chirps-v2.0.{year:04d}.{month:02d}.tif.gz"
        )

    def _monthly_raster_path(self, year: int, month: int, cache_dir: Path, region: str) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"chirps-v2.0.{year:04d}.{month:02d}.{region}.tif"

    def _download_monthly_geotiff(self, year: int, month: int, region: str) -> bytes:
        """Download and decompress one monthly raster, retrying transient drops."""
        import time

        url = self._monthly_raster_url(year, month, region)
        last_error: Optional[Exception] = None
        for attempt in range(4):
            try:
                return decompress(_get(url, timeout=self.timeout_seconds).content)
            except (requests.RequestException, OSError, EOFError) as error:
                last_error = error
                time.sleep(2**attempt)
        raise RuntimeError(f"CHIRPS monthly download failed for {url}: {last_error}") from last_error

    def _read_monthly_raster(
        self, year: int, month: int, cache_dir: Optional[Path], region: str = "africa"
    ):
        """Return (values, transform, nodata) for one monthly raster, caching the
        decompressed GeoTIFF on disk so repeated panel builds do not re-download.
        Writes are atomic (temp file + rename) so an interrupted download never
        leaves a half-written file that later looks cached."""
        import os

        import rasterio

        if cache_dir is not None:
            path = self._monthly_raster_path(year, month, Path(cache_dir), region)
            if not path.exists():
                data = self._download_monthly_geotiff(year, month, region)
                tmp = path.with_suffix(path.suffix + f".part{os.getpid()}")
                tmp.write_bytes(data)
                os.replace(tmp, path)
            with rasterio.open(path) as raster:
                return raster.read(1), raster.transform, raster.nodata

        from rasterio.io import MemoryFile

        with MemoryFile(self._download_monthly_geotiff(year, month, region)) as memory_file:
            with memory_file.open() as raster:
                return raster.read(1), raster.transform, raster.nodata

    def fetch_monthly_series(
        self,
        start: datetime,
        end: datetime,
        points: Optional[dict] = None,
        bboxes: Optional[dict] = None,
        cache_dir: Optional[Path] = None,
        window_deg: float = 0.15,
        region: str = "africa",
    ) -> pd.DataFrame:
        """Spatially-sampled monthly CHIRPS rainfall over a set of points and/or bboxes.

        Iterates each month once (downloading/caching a single raster), then
        samples every requested location from it.

        Args:
            start, end: inclusive month range.
            points: ``{name: (lat, lon)}`` -- sampled as the mean of a
                ``window_deg`` box around the point.
            bboxes: ``{name: (north, south, east, west)}`` -- area mean.
            cache_dir: directory for the decompressed monthly GeoTIFFs.
            window_deg: full side length, in degrees, of the box averaged around each point.
            region: ``'africa'`` (default) or ``'global'``.

        Returns:
            Long DataFrame: ``[location, kind, year_month, rainfall_mm]`` where
            ``kind`` is ``'point'`` or ``'catchment'``.
        """
        import rasterio

        if not points and not bboxes:
            raise ValueError("Provide at least one of points or bboxes")
        points = points or {}
        bboxes = bboxes or {}
        cache = Path(cache_dir) if cache_dir is not None else None

        records = []
        months = pd.date_range(
            pd.Timestamp(start).to_period("M").to_timestamp(),
            pd.Timestamp(end).to_period("M").to_timestamp(),
            freq="MS",
        )
        for stamp in months:
            try:
                values, transform, nodata = self._read_monthly_raster(
                    stamp.year, stamp.month, cache, region
                )
            except requests.HTTPError as error:
                raise RuntimeError(
                    f"CHIRPS monthly raster unavailable for {stamp:%Y-%m}: {error}"
                ) from error
            grid = values.astype(float)
            if nodata is not None:
                grid[grid == nodata] = np.nan
            grid[grid < 0] = np.nan  # CHIRPS uses -9999 for sea / no-data

            for name, (lat, lon) in points.items():
                half = window_deg / 2.0
                window = rasterio.windows.from_bounds(
                    lon - half, lat - half, lon + half, lat + half, transform=transform
                )
                rows, cols = window.toslices()
                sample = grid[rows, cols]
                records.append(
                    {
                        "location": name,
                        "kind": "point",
                        "year_month": stamp,
                        "rainfall_mm": float(np.nanmean(sample))
                        if np.isfinite(sample).any()
                        else np.nan,
                    }
                )

            for name, (north, south, east, west) in bboxes.items():
                window = rasterio.windows.from_bounds(
                    west, south, east, north, transform=transform
                )
                rows, cols = window.toslices()
                sample = grid[rows, cols]
                records.append(
                    {
                        "location": name,
                        "kind": "catchment",
                        "year_month": stamp,
                        "rainfall_mm": float(np.nanmean(sample))
                        if np.isfinite(sample).any()
                        else np.nan,
                    }
                )

        return pd.DataFrame.from_records(records)


@dataclass
class GloFASClient:
    """Client for Copernicus GloFAS discharge forecast (cds.climate.copernicus.eu)."""

    cds_api_key: Optional[str] = None
    station_coordinates: Optional[dict] = None
    cds_client: object = None

    def fetch_discharge_forecast(
        self,
        station_name: str,
        lead_days: int = 5,
        return_period: str = "default",
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Fetch 5-day discharge forecast with exceedance probability.

        Args:
            station_name: Name of GloFAS station (e.g., "Shabelle at Belet Weyne")
            lead_days: Lead time (1-5 days)
            return_period: Return period for exceedance (default, 2yr, 5yr, 20yr)

        Returns:
            (discharge_m3s_array, exceedance_probability_array)

        Raises:
            NotImplementedError: Fetch not yet implemented
        """
        if not 1 <= lead_days <= 5:
            raise ValueError("lead_days must be between 1 and 5")
        coordinates = (self.station_coordinates or {}).get(station_name)
        if coordinates is None:
            raise ValueError(
                f"No verified coordinates configured for GloFAS station '{station_name}'; "
                "provide station_coordinates rather than guessing a grid cell"
            )
        if not self.cds_api_key and self.cds_client is None:
            raise ValueError("CDS API credentials are required for GloFAS retrieval")
        client = self.cds_client or _create_cds_client(self.cds_api_key)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "glofas.nc"
            today = datetime.utcnow()
            request = {
                "system_version": "operational",
                "hydrological_model": "lisflood",
                "product_type": "consolidated reforecast",
                "variable": "river_discharge_in_the_last_24_hours",
                "year": f"{today:%Y}", "month": f"{today:%m}", "day": f"{today:%d}",
                "format": "netcdf",
            }
            client.retrieve("cems-glofas-forecast", request, str(target))
            discharge, probability = _read_forecast_at_point(target, coordinates, lead_days)
        if np.isnan(probability).all():
            raise ValueError(
                "GloFAS response did not contain exceedance probability; "
                "configure a verified return-period dataset before using it as a trigger"
            )
        return discharge, probability


@dataclass
class C3SClient:
    """Client for Copernicus C3S seasonal forecasts."""

    cds_api_key: Optional[str] = None
    cds_client: object = None

    def fetch_seasonal_precip_anomaly(
        self,
        season: str,  # "OND", "JFMA", "AMJ", "JJAS"
        catchment_bbox: Tuple[float, float, float, float],
    ) -> float:
        """
        Fetch seasonal precipitation anomaly vs. 1991-2020.

        Args:
            season: Season code
            catchment_bbox: (north, south, east, west)

        Returns:
            Anomaly as fraction (e.g., 0.25 = +25%)

        Raises:
            NotImplementedError: Fetch not yet implemented
        """
        if season not in {"OND", "JFMA", "AMJ", "JJAS"}:
            raise ValueError("season must be one of OND, JFMA, AMJ, or JJAS")
        north, south, east, west = catchment_bbox
        if not south < north or not west < east:
            raise ValueError("catchment_bbox must be (north, south, east, west)")
        if not self.cds_api_key and self.cds_client is None:
            raise ValueError("CDS API credentials are required for C3S retrieval")
        client = self.cds_client or _create_cds_client(self.cds_api_key)
        months = {"OND": ["10", "11", "12"], "JFMA": ["01", "02", "03", "04"], "AMJ": ["04", "05", "06"], "JJAS": ["07", "08", "09", "10"]}[season]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "c3s.nc"
            request = {
                "originating_centre": "ecmwf",
                "system": "51",
                "variable": "total_precipitation",
                "year": str(datetime.utcnow().year), "month": months,
                "leadtime_month": ["1", "2", "3", "4"],
                "area": [north, west, south, east], "format": "netcdf",
            }
            client.retrieve("seasonal-original-single-levels", request, str(target))
            return _read_precipitation_anomaly(target)


@dataclass
class FRRIMSClient:
    """Client for FAO SWALIM FRRIMS river gauge data."""

    base_url: str = "http://frrims.faoswalim.org/rivers/levels"
    scraper_timeout_seconds: int = 30

    def scrape_current_levels(self) -> dict:
        """
        Scrape current river levels from FRRIMS.

        Returns:
            Dict mapping station name -> {stage_m, timestamp, data_status}

        Raises:
            NotImplementedError: Scraper not yet implemented
        """
        response = _get(self.base_url, timeout=self.scraper_timeout_seconds)
        tables = pd.read_html(StringIO(response.text))
        if not tables:
            raise ValueError("FRRIMS response contained no HTML tables")
        levels = {}
        for row in tables[0].to_dict(orient="records"):
            values = {str(key).lower(): value for key, value in row.items()}
            station = next((str(value) for key, value in values.items() if "station" in key), None)
            stage = next((value for key, value in values.items() if "level" in key or "stage" in key), None)
            if station is None or pd.isna(stage):
                continue
            levels[station] = {"stage_m": float(stage), "timestamp": datetime.utcnow(), "data_status": "OK"}
        return levels

    def check_gauge_status(self, station_name: str) -> str:
        """
        Check status of individual gauge (OK, DEGRADED, MISSING, STALE).

        Args:
            station_name: Station name

        Returns:
            Status string ("OK", "DEGRADED", "MISSING", or "STALE")

        Raises:
            NotImplementedError: Status check not yet implemented
        """
        levels = self.scrape_current_levels()
        reading = levels.get(station_name)
        if reading is None:
            return "MISSING"
        age_hours = (datetime.utcnow() - reading["timestamp"]).total_seconds() / 3600
        if age_hours > 48:
            return "STALE"
        if age_hours > 24:
            return "DEGRADED"
        return "OK"


@dataclass
class ACLEDClient:
    """Client for ACLED conflict events (acleddata.com)."""

    api_key: Optional[str] = None
    base_url: str = "https://api.acleddata.com"

    def fetch_events(
        self,
        country: str = "Somalia",
        admin1: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list:
        """
        Fetch ACLED conflict events.

        Args:
            country: Country name
            admin1: Region/state name (optional)
            start_date: Start date
            end_date: End date

        Returns:
            List of event dicts with date, location, event_type, fatalities, etc.

        Raises:
            NotImplementedError: Fetch not yet implemented
        """
        if not self.api_key:
            raise ValueError("ACLED API credentials are required")
        params = {"country": country, "key": self.api_key, "limit": 5000}
        if admin1:
            params["admin1"] = admin1
        if start_date:
            params["event_date"] = start_date.strftime("%Y-%m-%d|%Y-%m-%d")
        if end_date:
            params["event_date"] = f"{start_date:%Y-%m-%d}|{end_date:%Y-%m-%d}" if start_date else f"|{end_date:%Y-%m-%d}"
        payload = _get(f"{self.base_url.rstrip('/')}/acled/read", params=params).json()
        if not payload.get("success", True):
            raise ValueError(f"ACLED request failed: {payload}")
        return payload.get("data", [])

    def aggregate_events_by_district_month(self, events: list) -> dict:
        """
        Aggregate events by district and month.

        Args:
            events: List of ACLED events

        Returns:
            Dict mapping (district, month) -> {event_count, fatalities, ...}

        Raises:
            NotImplementedError: Aggregation not yet implemented
        """
        aggregate = {}
        for event in events:
            district = event.get("admin2") or event.get("district")
            date = pd.to_datetime(event.get("event_date"), errors="coerce")
            if not district or pd.isna(date):
                continue
            key = (district, date.to_period("M").to_timestamp())
            bucket = aggregate.setdefault(key, {"event_count": 0, "fatalities": 0})
            bucket["event_count"] += 1
            bucket["fatalities"] += float(event.get("fatalities", 0) or 0)
        return aggregate


class ENSOIODClient:
    """Client for ENSO and IOD indices."""

    @staticmethod
    def fetch_oni() -> Tuple[np.ndarray, np.ndarray]:
        """
        Fetch NOAA CPC ONI (Oceanic Niño Index).

        Returns:
            (oni_values, months) where months are "YYYY-MM"

        Raises:
            NotImplementedError: Fetch not yet implemented
        """
        response = _get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt")
        rows = []
        for line in response.text.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].isdigit():
                rows.append((f"{parts[0]}-{int(parts[1]):02d}", float(parts[3])))
        if not rows:
            raise ValueError("NOAA ONI response contained no parseable records")
        return np.asarray([value for _, value in rows]), np.asarray([month for month, _ in rows])

    @staticmethod
    def fetch_dmi() -> Tuple[np.ndarray, np.ndarray]:
        """
        Fetch BoM DMI (Dipole Mode Index).

        Returns:
            (dmi_values, months)

        Raises:
            NotImplementedError: Fetch not yet implemented
        """
        response = _get("http://www.bom.gov.au/climate/iod/indices.shtml")
        tables = pd.read_html(StringIO(response.text))
        if not tables:
            raise ValueError("BoM DMI response contained no tables")
        table = tables[0]
        value_column = next((column for column in table.columns if "dmi" in str(column).lower()), None)
        if value_column is None:
            raise ValueError("BoM DMI response did not expose a DMI column")
        values = pd.to_numeric(table[value_column], errors="coerce").dropna().to_numpy()
        return values, np.asarray(table.loc[table[value_column].notna()].index.astype(str))

    @staticmethod
    def classify_enso_phase(oni: float) -> str:
        """
        Classify ENSO phase from ONI.

        Args:
            oni: ONI value

        Returns:
            Phase ("La Niña", "Neutral", "El Niño")
        """
        if oni >= 0.5:
            return "El Niño"
        elif oni <= -0.5:
            return "La Niña"
        else:
            return "Neutral"

    @staticmethod
    def classify_iod_phase(dmi: float) -> str:
        """
        Classify IOD phase from DMI.

        Args:
            dmi: DMI value

        Returns:
            Phase ("Negative", "Neutral", "Positive")
        """
        if dmi >= 0.4:
            return "Positive"
        elif dmi <= -0.4:
            return "Negative"
        else:
            return "Neutral"


@dataclass
class ICPACClient:
    """Client for ICPAC seasonal outlooks."""

    base_url: str = "https://www.icpac.net"

    def fetch_seasonal_outlook(
        self,
        season: str,  # "OND", "JFMA", "etc."
        region: str = "Greater Horn",
    ) -> dict:
        """
        Fetch ICPAC seasonal outlook.

        Returns tercile probabilities for below/normal/above rainfall.

        Args:
            season: Season code
            region: Geographic region

        Returns:
            Dict with tercile probabilities and confidence

        Raises:
            NotImplementedError: Fetch not yet implemented
        """
        raise NotImplementedError("ICPAC does not expose a stable public API; configure a verified bulletin parser")

    @staticmethod
    def extract_tercile_probability(outlook: dict, tercile: str = "above") -> float:
        """
        Extract specific tercile probability.

        Args:
            outlook: ICPAC outlook dict
            tercile: "below", "normal", or "above"

        Returns:
            Probability (0-1)
        """
        if tercile not in {"below", "normal", "above"}:
            raise ValueError("tercile must be below, normal, or above")
        candidates = (f"{tercile}_probability", f"probability_{tercile}", tercile)
        for key in candidates:
            if key in outlook:
                value = float(outlook[key])
                if not 0 <= value <= 1:
                    raise ValueError("tercile probability must be in [0, 1]")
                return value
        raise KeyError(f"Outlook does not contain a probability for '{tercile}'")


class SourceHealthChecker:
    """Utility to check health of all data sources (for `saat preflight`)."""

    SOURCES = {
        "CHIRPS": "https://data.chc.ucsb.edu",
        "FRRIMS": "http://frrims.faoswalim.org/rivers/levels",
        "GloFAS": "https://cds.climate.copernicus.eu",
        "ICPAC": "https://www.icpac.net",
        "ACLED": "https://acleddata.com",
        "NOAA CPC": "https://ggweather.com/enso/oni.htm",
        "BoM": "http://www.bom.gov.au/climate/iod/",
        "HAPI": "https://hapi.humdata.org/api/v2",
        "CKAN": "https://data.humdata.org/api/3/action",
    }

    @staticmethod
    def check_all_sources(timeout: int = 10) -> dict:
        """
        Check reachability and currency of all sources.

        Returns:
            Dict mapping source -> {is_reachable, is_current, last_update_days_ago}

        Raises:
            NotImplementedError: Health check not yet implemented
        """
        results = {}
        for name, url in SourceHealthChecker.SOURCES.items():
            checked_at = datetime.utcnow()
            try:
                response = requests.get(url, timeout=timeout)
                results[name] = {
                    # Receiving any HTTP response proves network reachability;
                    # endpoint/authentication status is reported separately.
                    "url": url, "is_reachable": True, "is_current": None,
                    "last_update": checked_at, "status_code": response.status_code,
                    "http_ok": response.ok,
                    "error_message": None if response.ok else response.reason,
                }
            except (requests.RequestException, OSError, ConnectionError) as error:
                results[name] = {
                    "url": url, "is_reachable": False, "is_current": None,
                    "last_update": checked_at, "status_code": None, "http_ok": False,
                    "error_message": f"{type(error).__name__}: {error}",
                }
        return results
