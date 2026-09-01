"""
Data panel assembly from HDX CKAN and HAPI APIs.

Assembles the district-month panel with:
- Internal displacement (PRMN origin-destination)
- Hazard features (rainfall, discharge, flood extent)
- Economic features (prices, terms of trade)
- IPC food security classifications
- ACLED conflict events

Reference: Section 10 of the build prompt.

CRITICAL GOTCHAS:
1. HAPI caps queries at 10,000 rows and silently truncates. Always page.
2. PRMN column names change across releases. Inspect headers, resolve by fuzzy match.
3. PRMN is a monitoring network, not a census. Coverage correlates with humanitarian
   presence. Model learns where displacement is OBSERVED, not where it OCCURS.
4. The visible PRMN resource may end in Aug 2023. Unverified. Use HAPI or IOM DTM.

Build the generation panel BALANCED: months with no recorded displacement are true
zeros for the classifier. Dropping them destroys the base rate that cost-loss depends on.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List, Any
import warnings
import base64
import pandas as pd
import numpy as np
import requests
from io import BytesIO


@dataclass
class DataSource:
    """Configuration for a data source API."""

    name: str
    url: str
    is_live: bool = False
    last_check: Optional[datetime] = None
    is_fresh: bool = False  # Updated within expected interval
    freshness_days: Optional[float] = None  # Age in days


class HDXCKANClient:
    """Client for HDX CKAN API (https://data.humdata.org/api/3/action)."""

    def __init__(self, base_url: str = "https://data.humdata.org/api/3/action", timeout: int = 30):
        """Initialize CKAN client."""
        self.base_url = base_url
        self.timeout = timeout

    def fetch_dataset(self, dataset_slug: str) -> Dict[str, Any]:
        """
        Fetch dataset metadata.

        Args:
            dataset_slug: HDX dataset slug (e.g., "somalia-internally-displaced-persons-idps")

        Returns:
            Dataset metadata dict

        Raises:
            Placeholder: Will implement network call
        """
        response = requests.get(
            f"{self.base_url.rstrip('/')}/package_show",
            params={"id": dataset_slug},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise ValueError(f"CKAN dataset lookup failed: {payload}")
        return payload["result"]

    def list_resources(self, dataset_slug: str) -> List[Dict[str, Any]]:
        """List resources in dataset."""
        return self.fetch_dataset(dataset_slug).get("resources", [])

    def fetch_resource(self, resource_id: str, format: str = "csv") -> pd.DataFrame:
        """
        Fetch resource data.

        Args:
            resource_id: HDX resource UUID
            format: Data format (csv, json, etc.)

        Returns:
            DataFrame with resource data

        Raises:
            Placeholder: Will implement network call
        """
        response = requests.get(resource_id, timeout=self.timeout)
        response.raise_for_status()
        if format.lower() == "csv":
            return pd.read_csv(BytesIO(response.content))
        if format.lower() == "json":
            payload = response.json()
            return pd.DataFrame(payload.get("result", payload))
        raise ValueError("format must be csv or json")


class HAPIClient:
    """Client for HDX HAPI API (https://hapi.humdata.org/api/v2)."""

    def __init__(self, base_url: str = "https://hapi.humdata.org/api/v2", app_identifier: Optional[str] = None, timeout: int = 30):
        """
        Initialize HAPI client.

        Args:
            base_url: HAPI base URL
            app_identifier: Application identifier for HAPI (required, free key)
        """
        self.base_url = base_url
        self.app_identifier = app_identifier
        self.timeout = timeout

    @staticmethod
    def make_app_identifier(application_name: str, email: str) -> str:
        """Create HAPI's documented base64 application-name/email identifier."""
        if not application_name.strip() or "@" not in email:
            raise ValueError("application_name and a valid email are required")
        value = f"{application_name.strip()}:{email.strip()}".encode("utf-8")
        return base64.b64encode(value).decode("ascii")

    def fetch_idp_statistics(
        self,
        dataset: str,
        limit: int = 10000,
        offset: int = 0,
    ) -> pd.DataFrame:
        """
        Fetch IDP statistics from HAPI.

        **CRITICAL:** HAPI caps at 10,000 rows per query and silently truncates.
        Must page through all results.

        Args:
            dataset: HAPI dataset name
            limit: Rows per page (max 10000)
            offset: Starting row for pagination

        Returns:
            DataFrame with IDP data

        Raises:
            Placeholder: Will implement network call with pagination
        """
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        if not self.app_identifier:
            raise ValueError("HAPI_APP_IDENTIFIER is required for HAPI retrieval")
        dataset_routes = {
            "idp": "affected-people/idps",
            "idps": "affected-people/idps",
            "affected-people/idps": "affected-people/idps",
        }
        route = dataset_routes.get(dataset.lower().strip("/"), dataset.strip("/"))
        response = requests.get(
            f"{self.base_url.rstrip('/')}/{route}",
            params={"limit": limit, "offset": offset},
            headers={"X-HDX-HAPI-APP-IDENTIFIER": self.app_identifier},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", payload.get("results", payload))
        if isinstance(rows, dict):
            rows = rows.get("data", [])
        if not isinstance(rows, list):
            raise ValueError("HAPI response did not contain a row list")
        return pd.DataFrame(rows)

    def paginate_idp_statistics(
        self,
        dataset: str,
        page_size: int = 10000,
    ) -> pd.DataFrame:
        """
        Fetch IDP statistics with automatic pagination.

        Handles HAPI's 10,000 row limit by iterating until no more rows.

        Args:
            dataset: HAPI dataset name
            page_size: Rows per page (max 10000)

        Returns:
            Complete DataFrame with all IDP data

        Raises:
            Placeholder: Will implement pagination logic
        """
        if not 1 <= page_size <= 10000:
            raise ValueError("page_size must be between 1 and 10000")
        pages = []
        offset = 0
        while True:
            page = self.fetch_idp_statistics(dataset, limit=page_size, offset=offset)
            if page.empty:
                break
            pages.append(page)
            if len(page) < page_size:
                break
            offset += len(page)
        return pd.concat(pages, ignore_index=True) if pages else pd.DataFrame()


class PRMNLoader:
    """Load and preprocess PRMN origin-destination displacement data."""

    # Candidate column names (PRMN has restructured this across releases)
    PRMN_COLUMN_CANDIDATES = {
        "date": ["date", "month", "year_month", "reporting_date", "Month End"],
        "origin": [
            "origin", "source_district", "from_district", "district_origin",
            "Previous (Departure) District",
        ],
        "destination": [
            "destination", "dest_district", "to_district", "district_dest",
            "Current (Arrival) District",
        ],
        "flow": ["flow", "arrivals", "new_arrivals", "movement_count", "Number of Individuals"],
    }

    def __init__(self, use_fuzzy_matching: bool = True):
        """
        Initialize PRMN loader.

        Args:
            use_fuzzy_matching: Use fuzzy matching to resolve column names
        """
        self.use_fuzzy_matching = use_fuzzy_matching
        self.observed_columns = None
        self.dropped_invalid_endpoint_rows = 0

    def resolve_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """
        Resolve PRMN column names by fuzzy matching.

        Does NOT hardcode expected columns. Inspects what was actually received,
        prints headers, and raises with observed headers on failure.

        Args:
            df: DataFrame with unknown column structure

        Returns:
            Dict mapping canonical name -> actual column name
            e.g., {"date": "reporting_date", "origin": "from_district", ...}

        Raises:
            ValueError: If columns cannot be resolved, with observed headers in message
        """
        from difflib import get_close_matches

        resolved = {}
        self.observed_columns = list(df.columns)

        for canonical, candidates in self.PRMN_COLUMN_CANDIDATES.items():
            found = None

            # Try exact match first
            for candidate in candidates:
                if candidate in df.columns:
                    found = candidate
                    break

            # Try fuzzy match if enabled
            if found is None and self.use_fuzzy_matching:
                for candidate in candidates:
                    matches = get_close_matches(candidate, df.columns, n=1, cutoff=0.7)
                    if matches:
                        found = matches[0]
                        break

            if found is None:
                raise ValueError(
                    f"Could not resolve column '{canonical}' in PRMN data. "
                    f"Observed headers: {self.observed_columns}. "
                    f"Expected one of: {candidates}"
                )

            resolved[canonical] = found

        return resolved

    def load_prmn(self, df: pd.DataFrame, material_threshold: int = 5000) -> pd.DataFrame:
        """
        Load and preprocess PRMN data.

        Determines material displacement threshold from operational question.
        If actions trigger at 5,000 arrivals, train on threshold of 5,000,
        not 50 (which trains on noise).

        Args:
            df: Raw PRMN data
            material_threshold: Minimum displacement to count as "material" event

        Returns:
            Preprocessed PRMN data with:
            - Resolved column names
            - Date parsing
            - Origin-destination matrix
            - Material vs. non-material indicator
        """
        # Resolve columns
        col_map = self.resolve_columns(df)

        # Rename columns
        df_proc = df.rename(columns={v: k for k, v in col_map.items()}).copy()

        # Parse dates and counts from the published PRMN representation.
        df_proc["date"] = pd.to_datetime(
            df_proc["date"], errors="coerce", format="mixed", dayfirst=True
        )
        df_proc["flow"] = pd.to_numeric(
            df_proc["flow"].astype(str).str.replace(",", "", regex=False), errors="coerce"
        )

        valid_endpoints = (
            df_proc["origin"].map(lambda value: isinstance(value, str) and bool(value.strip()))
            & df_proc["destination"].map(
                lambda value: isinstance(value, str) and bool(value.strip()) and value.strip() != "0"
            )
        )
        self.dropped_invalid_endpoint_rows = int((~valid_endpoints).sum())
        if self.dropped_invalid_endpoint_rows:
            warnings.warn(
                f"Dropped {self.dropped_invalid_endpoint_rows} PRMN rows with invalid origin/destination labels",
                UserWarning,
                stacklevel=2,
            )
            df_proc = df_proc.loc[valid_endpoints].copy()

        # Create material displacement indicator
        df_proc["is_material"] = df_proc["flow"] >= material_threshold

        # Validate
        if df_proc["date"].isna().any():
            raise ValueError("Date parsing failed - some dates remain null after parsing")
        if df_proc["flow"].isna().any() or (df_proc["flow"] < 0).any():
            raise ValueError("Flow parsing failed - counts must be non-negative numbers")

        return df_proc


class IOMETTLoader:
    """Load IOM DTM Emergency Trends Tracking settlement assessments."""

    COLUMN_CANDIDATES = {
        "date": ["Date of Assessment", "assessment_date", "date"],
        "origin": ["Origin_District_country", "Somalia District of Origin", "origin"],
        "destination": ["District Name", "district", "destination"],
        "flow": ["Total new arrivals since last week", "New arrivals since last week", "arrivals"],
    }

    def __init__(self):
        self.observed_columns = None
        self.dropped_invalid_rows = 0

    def resolve_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Resolve the ETT schema and include observed headers in failures."""
        self.observed_columns = list(df.columns)
        resolved = {}
        for canonical, candidates in self.COLUMN_CANDIDATES.items():
            found = next((candidate for candidate in candidates if candidate in df.columns), None)
            if found is None:
                raise ValueError(
                    f"Could not resolve ETT column '{canonical}'. "
                    f"Observed headers: {self.observed_columns}. Expected one of: {candidates}"
                )
            resolved[canonical] = found
        return resolved

    def load_ett(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert weekly settlement assessments into monthly OD flow records."""
        columns = self.resolve_columns(df)
        result = df.rename(columns={value: key for key, value in columns.items()}).copy()
        result["date"] = pd.to_datetime(result["date"], errors="coerce", format="mixed")
        result["flow"] = pd.to_numeric(result["flow"], errors="coerce")
        valid = (
            result["date"].notna()
            & result["flow"].notna()
            & (result["flow"] >= 0)
            & result["origin"].map(lambda value: isinstance(value, str) and bool(value.strip()))
            & result["destination"].map(lambda value: isinstance(value, str) and bool(value.strip()))
        )
        self.dropped_invalid_rows = int((~valid).sum())
        if self.dropped_invalid_rows:
            warnings.warn(
                f"Dropped {self.dropped_invalid_rows} ETT rows with invalid date, flow, or district labels",
                UserWarning,
                stacklevel=2,
            )
        result = result.loc[valid, ["date", "origin", "destination", "flow"]].copy()
        result["date"] = result["date"].dt.to_period("M").dt.to_timestamp()
        return (
            result.groupby(["date", "origin", "destination"], as_index=False)["flow"]
            .sum()
            .sort_values(["date", "origin", "destination"])
            .reset_index(drop=True)
        )

    def load_ett_resources(self, frames: List[pd.DataFrame]) -> pd.DataFrame:
        """Load and combine multiple ETT releases without silently duplicating coverage."""
        if not frames:
            raise ValueError("At least one ETT resource is required")
        loaded = [self.load_ett(frame) for frame in frames]
        combined = pd.concat(loaded, ignore_index=True)
        duplicate_keys = combined.duplicated(["date", "origin", "destination"], keep=False)
        if duplicate_keys.any():
            # Releases may overlap at a reporting boundary; aggregate identical
            # monthly OD keys rather than double-counting repeated assessments.
            combined = (
                combined.groupby(["date", "origin", "destination"], as_index=False)["flow"]
                .sum()
            )
        return combined.sort_values(["date", "origin", "destination"]).reset_index(drop=True)


@dataclass
class PanelSpec:
    """Specification for the district-month panel."""

    districts: List[str]
    start_date: datetime
    end_date: datetime
    include_zero_months: bool = True  # Must be True for valid classifier training

    def validate(self):
        """Validate panel specification."""
        if not self.include_zero_months:
            raise ValueError(
                "Panel must include zero-displacement months. Dropping them "
                "destroys the base rate that cost-loss calculation depends on."
            )


class PanelAssembler:
    """Assemble the full district-month panel."""

    def __init__(self):
        """Initialize panel assembler."""
        self.prmn_data = None
        self.hazard_data = None
        self.economic_data = None
        self.ipc_data = None
        self.conflict_data = None

    def create_district_month_grid(
        self,
        districts: List[str],
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Create balanced panel grid.

        All combinations of district × month in range, including months with
        zero observed displacement (required for proper classifier training).

        Args:
            districts: List of district names
            start_date: Panel start date
            end_date: Panel end date

        Returns:
            DataFrame with columns: [district, year_month, is_zero_month]
        """
        # Create date range (monthly)
        date_range = pd.date_range(start=start_date, end=end_date, freq="MS")

        # Create Cartesian product
        grid_data = []
        for district in districts:
            for date in date_range:
                grid_data.append(
                    {
                        "district": district,
                        "year_month": date,
                        "year": date.year,
                        "month": date.month,
                    }
                )

        grid_df = pd.DataFrame(grid_data)
        return grid_df

    @staticmethod
    def merge_flow_sources(prmn_df: pd.DataFrame, ett_df: pd.DataFrame) -> pd.DataFrame:
        """Merge flow sources without converting an uncovered period into zeros."""
        required = {"date", "origin", "destination", "flow"}
        frames = []
        for source_name, frame in (("PRMN", prmn_df), ("IOM_ETT", ett_df)):
            missing = required.difference(frame.columns)
            if missing:
                raise ValueError(f"{source_name} flow data missing: {sorted(missing)}")
            current = frame[list(required)].copy()
            current["date"] = pd.to_datetime(current["date"], errors="coerce", format="mixed")
            current["flow"] = pd.to_numeric(current["flow"], errors="coerce")
            if current[["date", "flow"]].isna().any().any() or (current["flow"] < 0).any():
                raise ValueError(f"{source_name} flow data contains invalid dates or counts")
            current["source"] = source_name
            frames.append(current)
        merged = pd.concat(frames, ignore_index=True)
        merged["year_month"] = merged["date"].dt.to_period("M").dt.to_timestamp()
        return merged.sort_values(["year_month", "origin", "destination", "source"]).reset_index(drop=True)

    @staticmethod
    def merge_verified_features(
        panel_df: pd.DataFrame,
        rainfall_df: Optional[pd.DataFrame] = None,
        population_df: Optional[pd.DataFrame] = None,
        price_df: Optional[pd.DataFrame] = None,
        conflict_df: Optional[pd.DataFrame] = None,
        flood_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Join verified district-month features without filling absent history."""
        if not {"district", "date"}.issubset(panel_df.columns):
            raise ValueError("panel_df must contain district and date columns")
        result = panel_df.copy()
        result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
        specs = [
            (rainfall_df, "rainfall", ["rainfall_anomaly_pct", "rainfall"]),
            (population_df, "idp_stock", ["population"]),
            (price_df, "price", ["price"]),
            (conflict_df, "conflict", ["events", "fatalities"]),
            (flood_df, "flood", ["flood_extent", "stage_exceedance_days", "flash_index"]),
        ]
        for frame, prefix, value_columns in specs:
            if frame is None:
                continue
            source = frame.copy()
            district_column = next((column for column in ("district", "admin2_name", "District Name") if column in source), None)
            date_column = next((column for column in ("date", "reference_period_start", "Date of Assessment") if column in source), None)
            if district_column is None or date_column is None:
                raise ValueError(f"{prefix}_df must contain a district and date column")
            source["district"] = source[district_column].astype(str).str.strip()
            source["date"] = pd.to_datetime(source[date_column], errors="coerce", format="mixed").dt.to_period("M").dt.to_timestamp()
            usable = [column for column in value_columns if column in source]
            if not usable:
                raise ValueError(f"{prefix}_df contains none of the expected value columns: {value_columns}")
            for column in usable:
                source[column] = pd.to_numeric(source[column], errors="coerce")
            grouped = source.dropna(subset=["date"]).groupby(["district", "date"], as_index=False)[usable].mean()
            renamed = {column: f"{prefix}_{column}" for column in usable}
            result = result.merge(grouped.rename(columns=renamed), on=["district", "date"], how="left")
        return result

    def assemble(
        self,
        prmn_df: pd.DataFrame,
        hazard_df: Optional[pd.DataFrame] = None,
        economic_df: Optional[pd.DataFrame] = None,
        districts: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        material_threshold: int = 5000,
    ) -> pd.DataFrame:
        """
        Assemble full panel.

        Args:
            prmn_df: PRMN displacement data (preprocessed)
            hazard_df: Hazard features by district-month
            economic_df: Economic features by district-month
            districts: List of districts (if None, inferred from data)
            start_date: Panel start (if None, from data)
            end_date: Panel end (if None, from data)

        Returns:
            Full panel with all features and balanced zero-displacement records

        Raises:
            ValueError: If PRMN or optional feature keys are invalid
        """
        required = {"date", "origin", "destination", "flow"}
        missing = required.difference(prmn_df.columns)
        if missing:
            raise ValueError(
                f"prmn_df must be preprocessed with canonical columns; missing: {sorted(missing)}"
            )
        if prmn_df.empty:
            raise ValueError("prmn_df cannot be empty")
        data = prmn_df.copy()
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data["flow"] = pd.to_numeric(data["flow"], errors="coerce")
        if data[["date", "flow"]].isna().any().any() or (data["flow"] < 0).any():
            raise ValueError("PRMN dates and flows must be valid, non-negative values")
        data["year_month"] = data["date"].dt.to_period("M").dt.to_timestamp()

        inferred_districts = sorted(set(data["origin"]).union(data["destination"]))
        districts = districts or inferred_districts
        start = pd.Timestamp(start_date) if start_date is not None else data["year_month"].min()
        end = pd.Timestamp(end_date) if end_date is not None else data["year_month"].max()
        start, end = start.to_period("M").to_timestamp(), end.to_period("M").to_timestamp()
        if start > end or not districts:
            raise ValueError("Panel dates and districts must define a non-empty range")

        grid = self.create_district_month_grid(districts, start, end)
        outflows = data.groupby(["origin", "year_month"], as_index=False)["flow"].sum()
        outflows = outflows.rename(columns={"origin": "district", "flow": "outflow"})
        arrivals = data.groupby(["destination", "year_month"], as_index=False)["flow"].sum()
        arrivals = arrivals.rename(columns={"destination": "district", "flow": "arrivals"})
        panel = grid.merge(outflows, on=["district", "year_month"], how="left")
        panel = panel.merge(arrivals, on=["district", "year_month"], how="left")
        panel[["outflow", "arrivals"]] = panel[["outflow", "arrivals"]].fillna(0.0)
        if material_threshold < 0:
            raise ValueError("material_threshold must be non-negative")
        panel["is_material"] = panel["outflow"] >= material_threshold

        for optional, name in ((hazard_df, "hazard_df"), (economic_df, "economic_df")):
            if optional is None:
                continue
            feature = optional.copy()
            if "year_month" not in feature and "date" in feature:
                feature["year_month"] = pd.to_datetime(feature["date"]).dt.to_period("M").dt.to_timestamp()
            keys = {"district", "year_month"}
            if not keys.issubset(feature.columns):
                raise ValueError(f"{name} must contain district and year_month columns")
            if feature.duplicated(["district", "year_month"]).any():
                raise ValueError(f"{name} must contain at most one row per district-month")
            panel = panel.merge(feature, on=["district", "year_month"], how="left", suffixes=("", f"_{name[:-3]}"))

        self.prmn_data = data
        self.hazard_data = hazard_df
        self.economic_data = economic_df
        return panel.sort_values(["district", "year_month"]).reset_index(drop=True)


def _fuzzy_align_districts(names: List[str], reference: List[str]) -> Dict[str, str]:
    """Map each name in ``names`` to the closest name in ``reference`` (or itself)."""
    from difflib import get_close_matches

    ref_lower = {r.lower(): r for r in reference}
    mapping = {}
    for name in names:
        key = str(name).strip()
        if key.lower() in ref_lower:
            mapping[name] = ref_lower[key.lower()]
            continue
        match = get_close_matches(key.lower(), list(ref_lower), n=1, cutoff=0.82)
        mapping[name] = ref_lower[match[0]] if match else key
    return mapping


def build_catchment_rainfall_panel(
    chirps_client,
    district_reference: pd.DataFrame,
    catchment_bboxes: Dict[str, tuple],
    basin_regions: Dict[str, List[str]],
    panel_districts: List[str],
    start: datetime,
    end: datetime,
    cache_dir=None,
    lags: tuple = (1, 2, 3),
    district_aliases: Optional[Dict[str, str]] = None,
    extra_centroids: Optional[Dict[str, tuple]] = None,
) -> pd.DataFrame:
    """Assemble the CHIRPS monthly rainfall feature block for the district-month panel.

    Local (own-district) rainfall is sampled at each district centroid. For
    riverine districts, upstream Ethiopian-highland catchment rainfall is attached
    from the placeholder catchment bboxes via the admin-1 -> catchment map.
    Anomalies are relative to the **within-sample** month-of-year climatology
    (2016-2023), explicitly not the WMO 1991-2020 baseline -- extend the record
    before treating these as standardised anomalies.

    Args:
        chirps_client: a ``saat.sources.CHIRPSClient``.
        district_reference: columns ``district``, ``center_lat``, ``center_lon``,
            ``adm1_name`` (COD som_admin2 attributes).
        catchment_bboxes: ``{catchment_key: (north, south, east, west)}``.
        basin_regions: ``{catchment_key: [adm1_name, ...]}``.
        panel_districts: the district list the panel is built on (PRMN names).
        start, end: inclusive month range.
        cache_dir: passed through to the CHIRPS monthly cache.
        district_aliases: ``{panel_name: reference_name}`` for districts whose
            PRMN and COD spellings differ beyond fuzzy tolerance
            (e.g. ``{"Baidoa": "Baydhaba"}``).
        extra_centroids: ``{panel_name: (lat, lon)}`` for panel districts absent
            from ``district_reference`` (e.g. contested far-north districts).

    Returns:
        DataFrame keyed ``[district, year_month]`` with local / upstream rainfall,
        in-sample anomalies, an ``is_riverine`` flag, and the requested lags.
    """
    aliases = {k.strip(): v.strip() for k, v in (district_aliases or {}).items()}
    ref = district_reference.copy()
    ref["district"] = ref["district"].astype(str).str.strip()

    # Resolve COD adm2 names to panel (PRMN) names: explicit aliases first, then
    # fuzzy match on the remainder.
    alias_targets = {v: k for k, v in aliases.items()}
    ref["panel_district"] = ref["district"].map(alias_targets).astype("object")
    unresolved = ref["panel_district"].isna()
    fuzzy = _fuzzy_align_districts(
        list(ref.loc[unresolved, "district"]), list(panel_districts)
    )
    ref.loc[unresolved, "panel_district"] = ref.loc[unresolved, "district"].map(fuzzy)
    ref = ref[ref["panel_district"].isin(set(panel_districts))]
    ref = ref.drop_duplicates("panel_district", keep="first")

    # Fuzzy-align the reference admin-1 names to the region names used in the
    # basin map (COD "Hiraan" vs config "Hiiraan", etc.).
    config_regions = sorted({r for regions in basin_regions.values() for r in regions})
    region_alias = _fuzzy_align_districts(
        sorted(ref["adm1_name"].astype(str).str.strip().unique()), config_regions
    )
    region_to_catchment = {
        region: key for key, regions in basin_regions.items() for region in regions
    }
    ref["catchment"] = (
        ref["adm1_name"].astype(str).str.strip().map(region_alias).map(region_to_catchment)
    )

    points = {
        row.panel_district: (float(row.center_lat), float(row.center_lon))
        for row in ref.itertuples(index=False)
        if row.panel_district in set(panel_districts)
    }
    for name, (lat, lon) in (extra_centroids or {}).items():
        points.setdefault(name, (float(lat), float(lon)))
    series = chirps_client.fetch_monthly_series(
        start=start, end=end, points=points, bboxes=catchment_bboxes, cache_dir=cache_dir
    )
    series["year_month"] = pd.to_datetime(series["year_month"]).dt.to_period("M").dt.to_timestamp()

    local = (
        series[series["kind"] == "point"]
        .rename(columns={"location": "district", "rainfall_mm": "local_rain_mm"})
        .loc[:, ["district", "year_month", "local_rain_mm"]]
    )
    catch = (
        series[series["kind"] == "catchment"]
        .rename(columns={"location": "catchment", "rainfall_mm": "upstream_rain_mm"})
        .loc[:, ["catchment", "year_month", "upstream_rain_mm"]]
    )

    panel = local.copy()
    panel["month"] = panel["year_month"].dt.month
    panel["local_rain_anom_insample"] = panel["local_rain_mm"] - panel.groupby(
        ["district", "month"]
    )["local_rain_mm"].transform("mean")

    district_catchment = ref.set_index("panel_district")["catchment"].to_dict()
    panel["catchment"] = panel["district"].map(district_catchment)
    panel["is_riverine"] = panel["catchment"].notna().astype(int)

    catch["c_month"] = catch["year_month"].dt.month
    catch["upstream_rain_anom_insample"] = catch["upstream_rain_mm"] - catch.groupby(
        ["catchment", "c_month"]
    )["upstream_rain_mm"].transform("mean")
    panel = panel.merge(
        catch.drop(columns=["c_month"]), on=["catchment", "year_month"], how="left"
    )
    for column in ("upstream_rain_mm", "upstream_rain_anom_insample"):
        panel[column] = panel[column].fillna(0.0)

    panel = panel.sort_values(["district", "year_month"])
    lag_columns = [
        "local_rain_mm",
        "local_rain_anom_insample",
        "upstream_rain_mm",
        "upstream_rain_anom_insample",
    ]
    for column in lag_columns:
        for lag in lags:
            panel[f"{column}_lag_{lag}"] = panel.groupby("district")[column].shift(lag)

    return panel.drop(columns=["month", "catchment"]).reset_index(drop=True)


# Utility functions for `saat preflight` command
@dataclass
class DataSourceStatus:
    """Status of a single data source."""

    name: str
    url: str
    is_reachable: bool
    is_current: bool
    last_update: Optional[datetime] = None
    age_days: Optional[float] = None
    error_message: Optional[str] = None


def check_data_sources() -> Dict[str, DataSourceStatus]:
    """
    Check availability and currency of all data sources.

    Thin adapter over :class:`saat.sources.SourceHealthChecker` (the single
    implementation used by ``saat preflight``) that returns typed
    :class:`DataSourceStatus` records. Currency (last-update freshness) is not
    resolved here: it needs per-source metadata parsing and is reported by
    ``saat preflight`` per source, so ``is_current``/``age_days`` stay null
    rather than carrying an invented value.
    """
    from saat.sources import SourceHealthChecker

    statuses: Dict[str, DataSourceStatus] = {}
    for name, raw in SourceHealthChecker.check_all_sources().items():
        statuses[name] = DataSourceStatus(
            name=name,
            url=raw["url"],
            is_reachable=raw["is_reachable"],
            is_current=False,
            last_update=raw.get("last_update"),
            age_days=None,
            error_message=raw.get("error_message"),
        )
    return statuses
