"""
Two-stage displacement model: generation and allocation.

**Stage 1, generation:** How many leave district i in month t?
- Two-part model: classifier for material displacement, regressor on log1p(count)
- Uses LightGBM for both components
- Blocked forward-chaining cross-validation with embargo gap

**Stage 2, allocation:** Where do they go?
- Gravity model by Poisson regression
- Key insight: destination choice follows clan/kin networks, NOT distance
- Existing IDP population at destination is strongest attractiveness term

Rahanweyn households from Bay/Bakool move to Baidoa/Mogadishu on established
corridors. Pure distance-decay model sends them to the wrong towns.

Output: `site_pressure` = forecast arrivals as % of standing IDP population.
A site absorbing 5% needs nothing. One absorbing 40% needs land, WASH, site
management secured BEFORE arrivals (cannot be done reactively).

Reference: Section 8 of the build prompt.

CRITICAL WARNINGS:
1. Exclude IPC and FEWS NET from features. Including them makes the model
   an expensive reproduction of FEWS NET judgement and validates circularly.
2. Expose vulnerability_multiplier as scenario parameter (default 1.0).
   This captures the 2026 asset-depletion effect from four failed seasons.
3. Accept coverage_weight correction. PRMN coverage correlates with humanitarian
   presence. Model learns where displacement is OBSERVED, not where it OCCURS.
4. Conflict features are entangled (conflict drives displacement AND suppresses
   observation). Coefficient cannot be separated without external information.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from saat.verification import ContingencyMetrics

EXCLUDED_FEATURE_TERMS = ("ipc", "fews", "food_security_phase")


@dataclass
class GenerationModelConfig:
    """Configuration for Stage 1 generation model."""

    material_threshold: int = 5000  # Minimum arrivals to count as "material"
    classifier_type: str = "lightgbm"
    regressor_type: str = "lightgbm"
    validation_strategy: str = "blocked_temporal"  # Blocked forward-chaining with embargo
    embargo_gap_months: int = 3  # Embargo gap between train and test
    cv_folds: int = 5

    # Feature engineering
    rainfall_lags_months: Tuple[int, int, int] = (1, 2, 3)
    price_anomaly_percentile: int = 50
    terms_of_trade_lag_months: int = 1
    prior_outflow_lags_months: Tuple[int, int] = (1, 12)


@dataclass
class AllocationModelConfig:
    """Configuration for Stage 2 gravity model."""

    model_type: str = "poisson_regression"
    distance_friction: Optional[float] = None  # Estimated from data
    origin_offset: bool = True  # Log(outflow_origin) as offset for mass conservation
    same_region_premium: float = 1.5  # Multiplier for same-region destination


class GenerationModel:
    """Stage 1: Classifier + regressor for displacement generation."""

    def __init__(self, config: GenerationModelConfig = None):
        """
        Initialize generation model.

        Args:
            config: Model configuration
        """
        self.config = config or GenerationModelConfig()
        self.classifier = None
        self.regressor = None
        self.feature_names = None
        self.cv_results = None
        self._district_codes = {}
        self._train_features = None
        self._train_flows = None
        self._train_material = None
        self._train_months = None
        self._train_districts = None

    def get_features(self, panel_df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract features for generation model.

        Features: rainfall anomalies lagged 1-3 months, flash index, stage
        exceedance days, flood extent, NDVI/VCI anomaly, WRSI, cereal price
        anomaly, goat-to-cereal terms of trade, water price anomaly, ACLED
        conflict events and fatalities, prior IDP stock, own outflow lagged
        1 and 12 months, population, livelihood zone shares.

        **EXCLUDE IPC and FEWS NET phase classifications.**
        Including them makes the model an expensive reproduction of FEWS NET
        judgement and validates circularly against it.

        Args:
            panel_df: District-month panel

        Returns:
            Feature matrix

        Raises:
            NotImplementedError: Feature engineering not yet implemented
        """
        if panel_df.empty:
            raise ValueError("Panel cannot be empty")

        features = panel_df.copy()
        if "district" in features:
            for district in sorted(features["district"].dropna().astype(str).unique()):
                self._district_codes.setdefault(district, len(self._district_codes))
            features["district_code"] = features["district"].astype(str).map(self._district_codes).fillna(-1)
        date_column = next(
            (column for column in ("year_month", "date") if column in features), None
        )
        if date_column is not None:
            features[date_column] = pd.to_datetime(features[date_column], errors="coerce")
            features = features.sort_values(["district", date_column] if "district" in features else [date_column])
            # Calendar month is the Gu / Hagaa / Deyr / Jilaal seasonality signal
            # and must be available to the model; the raw date parts are not.
            features["calendar_month"] = features[date_column].dt.month.astype(float)

        # Create the requested temporal lags from canonical source columns when present.
        for column in list(features.columns):
            name = str(column).lower()
            if "rainfall" in name and "anomaly" in name:
                for lag in self.config.rainfall_lags_months:
                    group = features.groupby("district")[column] if "district" in features else features[column]
                    features[f"{column}_lag_{lag}"] = group.shift(lag) if "district" in features else features[column].shift(lag)
            if ("outflow" in name or name == "flow") and "lag" not in name:
                for lag in self.config.prior_outflow_lags_months:
                    group = features.groupby("district")[column] if "district" in features else features[column]
                    features[f"{column}_lag_{lag}"] = group.shift(lag) if "district" in features else features[column].shift(lag)

        # `outflow` / `arrivals` at time t are the target series itself (material
        # displacement is defined as outflow >= threshold): keeping the
        # contemporaneous value is target leakage. Only their explicit lags,
        # generated above, are admissible predictors.
        excluded = {
            "district", "origin", "destination", "date", "year_month", "month", "year",
            "flow", "outflow", "arrivals", "new_arrivals", "movement_count", "is_material",
            "target", "log1p_flow", "log_flow",
        }
        numeric = features.select_dtypes(include=[np.number]).copy()
        keep = [
            column for column in numeric.columns
            if column.lower() not in excluded
            and not any(term in column.lower() for term in EXCLUDED_FEATURE_TERMS)
        ]
        if not keep:
            raise ValueError("Panel has no usable numeric displacement features")
        result = numeric[keep].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        # Lags are computed on a district/time-sorted copy; restore the caller's
        # row order so the feature matrix stays aligned with the target vector.
        result = result.reindex(panel_df.index)
        self.feature_names = list(result.columns)
        return result

    def fit(
        self,
        panel_df: pd.DataFrame,
        target_df: pd.DataFrame,
        validation_only: bool = False,
    ) -> Dict[str, float]:
        """
        Fit classifier and regressor.

        Uses blocked forward-chaining cross-validation with embargo gap.
        Reports skill against persistence and climatology, never against zero.

        Args:
            panel_df: District-month panel
            target_df: Displacement targets with binary (is_material) and continuous (log1p_flow)
            validation_only: If True, only validate without fitting

        Returns:
            CV results dict with skill metrics

        Raises:
            NotImplementedError: Model fitting not yet implemented
        """
        if len(panel_df) != len(target_df):
            raise ValueError("panel_df and target_df must have the same number of rows")
        self._district_codes = {
            district: index
            for index, district in enumerate(sorted(panel_df["district"].dropna().astype(str).unique()))
        } if "district" in panel_df else {}
        features = self.get_features(panel_df)
        flows = self._extract_flow(target_df)
        material = target_df["is_material"].to_numpy(dtype=int) if "is_material" in target_df else (flows >= self.config.material_threshold).astype(int)
        if material.sum() == 0 or material.sum() == len(material):
            raise ValueError("Training requires both material and non-material displacement cases")

        from lightgbm import LGBMClassifier, LGBMRegressor

        self.classifier = LGBMClassifier(
            n_estimators=100, learning_rate=0.05, num_leaves=15, verbosity=-1, random_state=42
        )
        self.regressor = LGBMRegressor(
            n_estimators=100, learning_rate=0.05, num_leaves=15, verbosity=-1, random_state=42
        )
        features = features.reset_index(drop=True)
        self.classifier.fit(features, material)
        positive = material == 1
        self.regressor.fit(features.loc[positive], np.log1p(flows[positive]))

        # Retain the aligned training arrays so temporal holdouts can be run
        # without the caller re-supplying the panel.
        self._train_features = features
        self._train_flows = flows
        self._train_material = material
        self._train_months = (
            pd.to_datetime(panel_df["year_month"]).to_numpy()
            if "year_month" in panel_df
            else None
        )
        self._train_districts = (
            panel_df["district"].astype(str).to_numpy() if "district" in panel_df else None
        )

        self.cv_results = self._evaluate_blocked_cv(features, flows, material, panel_df)
        return self.cv_results

    def predict(
        self,
        features_df: pd.DataFrame,
        vulnerability_multiplier: float = 1.0,
    ) -> pd.DataFrame:
        """
        Predict displacement generation.

        Args:
            features_df: Features for prediction
            vulnerability_multiplier: Scale forecast for asset-depletion effect (default 1.0)

        Returns:
            DataFrame with predictions:
            - prob_material: P(displacement > threshold)
            - predicted_flow: Expected displacement count
            - predicted_flow_scaled: With vulnerability multiplier applied

        Raises:
            NotImplementedError: Prediction not yet implemented
        """
        if self.classifier is None or self.regressor is None or self.feature_names is None:
            raise RuntimeError("Generation model must be fitted before prediction")
        if vulnerability_multiplier < 0:
            raise ValueError("vulnerability_multiplier must be non-negative")
        features = features_df.reindex(columns=self.feature_names, fill_value=0.0)
        features = features.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        probability = self.classifier.predict_proba(features)[:, 1]
        conditional = np.expm1(self.regressor.predict(features)).clip(min=0.0)
        predicted = probability * conditional
        return pd.DataFrame(
            {
                "prob_material": probability,
                "predicted_flow": predicted,
                "predicted_flow_scaled": predicted * vulnerability_multiplier,
            },
            index=features_df.index,
        )

    def validate_against_2023_flood(self) -> Dict[str, float]:
        """
        Temporal holdout on the 2023 flood season.

        The published PRMN panel ends August 2023, so the Oct-Dec 2023 Deyr
        floods are outside the training data. The available 2023 flood signal is
        the Gu / early-Hagaa riverine flooding (the Belet Weyne displacement
        spike of ~257,000 in May 2023). The holdout window is 2023-04 to
        2023-08, with the model trained only on data strictly before it (minus
        the embargo gap). Skill is reported against persistence and climatology.
        """
        return self._temporal_holdout("2023-04-01", "2023-08-31", label="2023_flood_season")

    def validate_against_2022_drought(self) -> Dict[str, float]:
        """
        Temporal holdout on the 2022 drought peak (2022-06 to 2022-10), with the
        model trained only on data strictly before the window (minus the embargo
        gap). Skill is reported against persistence and climatology.
        """
        return self._temporal_holdout("2022-06-01", "2022-10-31", label="2022_drought_peak")

    @staticmethod
    def _extract_flow(target_df: pd.DataFrame) -> np.ndarray:
        for column in ("flow", "arrivals", "new_arrivals", "movement_count"):
            if column in target_df:
                values = target_df[column].to_numpy(dtype=float)
                if np.any(values < 0):
                    raise ValueError("Displacement flow cannot be negative")
                return values
        raise ValueError("target_df must contain a flow or arrivals column")

    @staticmethod
    def _contingency(observed: np.ndarray, predicted: np.ndarray) -> ContingencyMetrics:
        """Build a contingency table from binary observed/predicted arrays."""
        observed = np.asarray(observed, dtype=int)
        predicted = np.asarray(predicted, dtype=int)
        return ContingencyMetrics(
            hits=int(np.sum((predicted == 1) & (observed == 1))),
            false_alarms=int(np.sum((predicted == 1) & (observed == 0))),
            misses=int(np.sum((predicted == 0) & (observed == 1))),
            correct_negatives=int(np.sum((predicted == 0) & (observed == 0))),
        )

    @staticmethod
    def _generation_skill(
        obs: np.ndarray,
        actual_flow: np.ndarray,
        model_prob: np.ndarray,
        model_flow: np.ndarray,
        persist_flag: np.ndarray,
        persist_flow: np.ndarray,
        clim_flow: np.ndarray,
    ) -> Dict[str, float]:
        """Score the generation forecast against persistence and climatology.

        Discrimination is reported threshold-free (ROC AUC) plus PSS / POD / FAR
        at a base-rate-matched operating point (fire on the top-``s`` fraction of
        predicted probabilities) -- a fixed 0.5 probability cut is meaningless at
        a ~4-8% event rate. The final operating threshold is a cost-loss decision
        (`saat verify`), not fixed here. Magnitude skill is pooled MAE of the
        combined forecast versus persistence and climatology.
        """
        from sklearn.metrics import roc_auc_score

        obs = np.asarray(obs, dtype=int)
        actual_flow = np.asarray(actual_flow, dtype=float)
        model_prob = np.asarray(model_prob, dtype=float)
        persist_flag = np.asarray(persist_flag, dtype=float)
        both_classes = obs.min() != obs.max()
        base_rate = float(obs.mean()) if len(obs) else float("nan")

        model_auc = float(roc_auc_score(obs, model_prob)) if both_classes else float("nan")
        persist_auc = float(roc_auc_score(obs, persist_flag)) if both_classes else float("nan")

        if both_classes and 0.0 < base_rate < 1.0:
            threshold = float(np.quantile(model_prob, 1.0 - base_rate))
            model_bin = (model_prob >= threshold).astype(int)
        else:
            threshold = 0.5
            model_bin = (model_prob >= 0.5).astype(int)
        model_ct = GenerationModel._contingency(obs, model_bin)
        persist_ct = GenerationModel._contingency(obs, (persist_flag >= 0.5).astype(int))

        model_mae = float(np.mean(np.abs(np.asarray(model_flow, dtype=float) - actual_flow)))
        persist_mae = float(np.mean(np.abs(np.asarray(persist_flow, dtype=float) - actual_flow)))
        clim_mae = float(np.mean(np.abs(np.asarray(clim_flow, dtype=float) - actual_flow)))

        return {
            "held_out_obs": int(len(obs)),
            "held_out_events": int(obs.sum()),
            "operating_threshold_prob": threshold,
            # Discrimination -- threshold-free.
            "model_auc": model_auc,
            "persistence_auc": persist_auc,
            # Discrimination at the base-rate-matched operating point.
            "model_pss": float(model_ct.pss),
            "model_pod": float(model_ct.pod),
            "model_far": float(model_ct.far),
            "model_csi": float(model_ct.csi),
            "model_frequency_bias": float(model_ct.frequency_bias),
            "persistence_pss": float(persist_ct.pss),
            "persistence_pod": float(persist_ct.pod),
            "persistence_far": float(persist_ct.far),
            "climatology_pss": 0.0,  # always-"no material" at a <50% base rate
            # Magnitude -- combined forecast vs baselines.
            "model_flow_mae": model_mae,
            "persistence_flow_mae": persist_mae,
            "climatology_flow_mae": clim_mae,
            "flow_skill_vs_persistence": float(1.0 - model_mae / persist_mae)
            if persist_mae > 0
            else float("nan"),
            "flow_skill_vs_climatology": float(1.0 - model_mae / clim_mae)
            if clim_mae > 0
            else float("nan"),
            # Conservative, spec-aligned bar: better rank discrimination (AUC),
            # no worse at the operating point (PSS), and sharper on magnitude (MAE).
            "beats_persistence": bool(
                both_classes
                and model_auc > persist_auc
                and float(model_ct.pss) >= float(persist_ct.pss)
                and model_mae < persist_mae
            ),
            "sharper_than_persistence_on_magnitude": bool(model_mae < persist_mae),
        }

    def _persistence_series(self) -> Tuple[np.ndarray, np.ndarray]:
        """Previous-month outflow and material flag per district, positionally aligned.

        Requires that ``fit`` has been called (uses the retained training arrays).
        Returns (persist_flow, persist_material); entries with no prior month are NaN / -1.
        """
        frame = pd.DataFrame(
            {
                "pos": np.arange(len(self._train_flows)),
                "district": self._train_districts,
                "month": self._train_months,
                "flow": self._train_flows,
                "material": self._train_material,
            }
        ).sort_values(["district", "month"])
        frame["persist_flow"] = frame.groupby("district")["flow"].shift(1)
        frame["persist_material"] = frame.groupby("district")["material"].shift(1)
        frame = frame.sort_values("pos")
        return (
            frame["persist_flow"].to_numpy(dtype=float),
            frame["persist_material"].fillna(-1).to_numpy(dtype=int),
        )

    def _evaluate_baselines(self, flows: np.ndarray, material: np.ndarray) -> Dict[str, float]:
        prevalence = float(material.mean())
        return {
            "material_rate": prevalence,
            "observations": float(len(flows)),
            "material_events": int(material.sum()),
        }

    def _evaluate_blocked_cv(
        self,
        features: pd.DataFrame,
        flows: np.ndarray,
        material: np.ndarray,
        panel_df: pd.DataFrame,
    ) -> Dict[str, float]:
        """Blocked forward-chaining CV over a balanced monthly panel.

        Chronological month blocks are held out one at a time; each training set
        is everything strictly earlier than the block, minus an embargo of
        ``embargo_gap_months`` months. Discrimination is reported with PSS / POD /
        FAR (not accuracy or Brier alone: at a ~4% base rate accuracy is
        meaningless), pooled across folds, alongside the persistence baseline.
        Regressor skill is the pooled MAE against persistence and climatology.
        """
        from lightgbm import LGBMClassifier, LGBMRegressor

        results = self._evaluate_baselines(flows, material)
        results["embargo_gap_months"] = float(self.config.embargo_gap_months)

        if "year_month" not in panel_df:
            results["blocked_cv_folds"] = 0.0
            results["blocked_cv_note"] = "no year_month column; blocked CV skipped"
            return results

        months = pd.to_datetime(panel_df["year_month"]).to_numpy()
        unique_months = np.array(sorted(pd.unique(months)))
        if len(unique_months) < 12:
            results["blocked_cv_folds"] = 0.0
            results["blocked_cv_note"] = "fewer than 12 months; blocked CV skipped"
            return results

        persist_flow_all, persist_material_all = (
            self._persistence_series()
            if self._train_flows is not None
            else (np.full(len(flows), np.nan), np.full(len(flows), -1))
        )

        fold_count = max(2, min(self.config.cv_folds, len(unique_months) // 6))
        month_blocks = np.array_split(unique_months, fold_count)

        p_obs, p_prob, p_persist_flag = [], [], []
        p_actual_flow, p_model_flow, p_persist_flow, p_clim_flow = [], [], [], []
        folds_used = 0
        embargo = pd.DateOffset(months=int(self.config.embargo_gap_months))

        for block in month_blocks:
            if len(block) == 0:
                continue
            cutoff = pd.Timestamp(block.min()) - embargo
            train_mask = months < np.datetime64(cutoff)
            test_mask = np.isin(months, block)
            if train_mask.sum() < 50 or test_mask.sum() == 0:
                continue
            train_material = material[train_mask]
            if train_material.min() == train_material.max():
                continue
            folds_used += 1

            classifier = LGBMClassifier(
                n_estimators=100, learning_rate=0.05, num_leaves=15, verbosity=-1, random_state=42
            )
            classifier.fit(features.iloc[train_mask], train_material)
            test_prob = classifier.predict_proba(features.iloc[test_mask])[:, 1]
            test_flow = flows[test_mask]

            p_obs.append(material[test_mask])
            p_prob.append(test_prob)
            pm = persist_material_all[test_mask]
            p_persist_flag.append(np.where(pm >= 0, pm, 0).astype(float))

            # Combined generation forecast: P(material) x E[flow | material].
            if train_material.sum() >= 5:
                regressor = LGBMRegressor(
                    n_estimators=100, learning_rate=0.05, num_leaves=15, verbosity=-1, random_state=42
                )
                pos = train_material == 1
                regressor.fit(features.iloc[train_mask].loc[pos], np.log1p(flows[train_mask][pos]))
                cond = np.expm1(regressor.predict(features.iloc[test_mask])).clip(min=0.0)
            else:
                cond = np.full(test_mask.sum(), float(np.mean(flows[train_mask])))
            p_actual_flow.append(test_flow)
            p_model_flow.append(test_prob * cond)

            pf = persist_flow_all[test_mask]
            p_persist_flow.append(
                np.where(np.isfinite(pf), pf, float(np.nanmean(flows[train_mask])))
            )

            train_frame = pd.DataFrame(
                {"district": self._train_districts[train_mask], "flow": flows[train_mask]}
            )
            district_mean = train_frame.groupby("district")["flow"].mean()
            global_mean = float(flows[train_mask].mean())
            p_clim_flow.append(
                np.array(
                    [district_mean.get(d, global_mean) for d in self._train_districts[test_mask]]
                )
            )

        if folds_used == 0:
            results["blocked_cv_folds"] = 0.0
            results["blocked_cv_note"] = "no fold had a usable train/test split"
            return results

        results["blocked_cv_folds"] = float(folds_used)
        results.update(
            self._generation_skill(
                obs=np.concatenate(p_obs),
                actual_flow=np.concatenate(p_actual_flow),
                model_prob=np.concatenate(p_prob),
                model_flow=np.concatenate(p_model_flow),
                persist_flag=np.concatenate(p_persist_flag),
                persist_flow=np.concatenate(p_persist_flow),
                clim_flow=np.concatenate(p_clim_flow),
            )
        )
        return results

    def _temporal_holdout(self, start: str, end: str, label: str) -> Dict[str, float]:
        """Train on everything strictly before ``start`` (minus the embargo) and
        score the classifier + combined forecast on the [start, end] window."""
        if self._train_features is None:
            raise RuntimeError("Fit the generation model before running a temporal holdout")
        if self._train_months is None:
            raise RuntimeError("Temporal holdout requires a 'year_month' column in the panel")

        from lightgbm import LGBMClassifier, LGBMRegressor

        months = self._train_months
        features = self._train_features
        flows = self._train_flows
        material = self._train_material

        window_start = np.datetime64(pd.Timestamp(start))
        window_end = np.datetime64(pd.Timestamp(end))
        embargo = pd.DateOffset(months=int(self.config.embargo_gap_months))
        train_cutoff = np.datetime64(pd.Timestamp(start) - embargo)

        train_mask = months < train_cutoff
        test_mask = (months >= window_start) & (months <= window_end)
        result: Dict[str, float] = {
            "holdout": label,
            "window": f"{start}..{end}",
            "validation_strategy": self.config.validation_strategy,
            "embargo_gap_months": float(self.config.embargo_gap_months),
            "train_obs": int(train_mask.sum()),
            "test_obs": int(test_mask.sum()),
            "test_material_events": int(material[test_mask].sum()) if test_mask.any() else 0,
        }
        if train_mask.sum() < 50 or test_mask.sum() == 0:
            result["note"] = "insufficient train history or empty window for this holdout"
            return result
        train_material = material[train_mask]
        if train_material.min() == train_material.max():
            result["note"] = "training window has only one displacement class"
            return result

        classifier = LGBMClassifier(
            n_estimators=100, learning_rate=0.05, num_leaves=15, verbosity=-1, random_state=42
        )
        classifier.fit(features.iloc[train_mask], train_material)
        prob = classifier.predict_proba(features.iloc[test_mask])[:, 1]
        obs = material[test_mask]
        test_flow = flows[test_mask]

        persist_flow_all, persist_material_all = self._persistence_series()
        pm = persist_material_all[test_mask]
        pf = persist_flow_all[test_mask]
        pf = np.where(np.isfinite(pf), pf, float(np.nanmean(flows[train_mask])))

        if train_material.sum() >= 5:
            regressor = LGBMRegressor(
                n_estimators=100, learning_rate=0.05, num_leaves=15, verbosity=-1, random_state=42
            )
            pos = train_material == 1
            regressor.fit(features.iloc[train_mask].loc[pos], np.log1p(flows[train_mask][pos]))
            cond = np.expm1(regressor.predict(features.iloc[test_mask])).clip(min=0.0)
        else:
            cond = np.full(int(test_mask.sum()), float(np.mean(flows[train_mask])))

        train_frame = pd.DataFrame(
            {"district": self._train_districts[train_mask], "flow": flows[train_mask]}
        )
        district_mean = train_frame.groupby("district")["flow"].mean()
        global_mean = float(flows[train_mask].mean())
        clim_flow = np.array(
            [district_mean.get(d, global_mean) for d in self._train_districts[test_mask]]
        )

        result.update(
            self._generation_skill(
                obs=obs,
                actual_flow=test_flow,
                model_prob=prob,
                model_flow=prob * cond,
                persist_flag=np.where(pm >= 0, pm, 0).astype(float),
                persist_flow=pf,
                clim_flow=clim_flow,
            )
        )
        return result


class AllocationModel:
    """Stage 2: Gravity model for destination choice."""

    def __init__(self, config: AllocationModelConfig = None):
        """
        Initialize allocation model.

        Args:
            config: Model configuration
        """
        self.config = config or AllocationModelConfig()
        self.model = None
        self.distance_matrix = None
        self.distance_friction = None
        self.gravity_fit_converged = None

    def fit_gravity_model(
        self,
        origin_destination_flows: pd.DataFrame,
        population_df: pd.DataFrame,
        distance_matrix: np.ndarray,
        aid_presence_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, float]:
        """
        Fit Poisson regression gravity model.

        Model destination choice conditional on outflow from origin.
        Uses log(outflow_origin) as offset so coefficients describe
        destination attractiveness conditional on number leaving.

        Terms: log destination IDP stock, log destination population,
        log distance, aid presence, same-region indicator.

        Args:
            origin_destination_flows: OD matrix with observed flows
            population_df: Population by district
            distance_matrix: Distance matrix between districts
            aid_presence_df: Binary matrix of humanitarian presence

        Returns:
            Model coefficients and fit statistics

        Raises:
            NotImplementedError: Model fitting not yet implemented
        """
        required = {"origin", "destination", "flow"}
        if not required.issubset(origin_destination_flows.columns):
            raise ValueError(f"origin_destination_flows must contain {sorted(required)}")
        if len(distance_matrix) == 0 or distance_matrix.shape[0] != distance_matrix.shape[1]:
            raise ValueError("distance_matrix must be square")
        self.distance_matrix = np.asarray(distance_matrix, dtype=float)
        self.distance_friction = self.config.distance_friction
        destination_idp = self._population_values(population_df, "idp_stock")
        destination_population = self._population_values(population_df, "population")
        aid = np.zeros_like(self.distance_matrix) if aid_presence_df is None else aid_presence_df.to_numpy(dtype=float)
        rows = []
        for record in origin_destination_flows.itertuples(index=False):
            origin = int(record.origin)
            destination = int(record.destination)
            distance = max(self.distance_matrix[origin, destination], 1e-6)
            outflow = origin_destination_flows.loc[origin_destination_flows["origin"] == origin, "flow"].sum()
            rows.append([
                np.log1p(destination_idp[destination]), np.log1p(destination_population[destination]),
                np.log(distance), aid[origin, destination], float(origin == destination),
                float(record.flow), max(float(outflow), 1.0),
            ])
        data = np.asarray(rows, dtype=float)
        design = data[:, :5]
        counts = data[:, 5]
        offsets = np.log(data[:, 6]) if self.config.origin_offset else np.zeros(len(data))

        # Standardise the design so the Poisson NLL is well scaled; per-origin
        # softmax renormalisation in allocate_flows absorbs any constant shift,
        # so no intercept term is needed and coefficients map back by /sigma.
        mu = design.mean(axis=0)
        sigma = design.std(axis=0)
        # A (near-)zero-variance term -- e.g. a placeholder-constant population or
        # distance matrix -- is not identifiable: pin its coefficient at 0 rather
        # than let the optimiser amplify rounding noise. The tolerance is
        # relative so log-scale constants (std ~1e-13) are caught.
        identifiable = sigma > 1e-8 * (np.abs(mu) + 1.0)
        sigma_safe = np.where(identifiable, sigma, 1.0)
        z_design = np.where(identifiable, (design - mu) / sigma_safe, 0.0)
        unidentified_terms = [
            name
            for name, ok in zip(
                ["dest_idp_stock", "dest_population", "distance", "aid_presence", "same_region"],
                identifiable,
            )
            if not ok
        ]

        n_pairs = len(counts)

        def objective(beta):
            linear = np.clip(z_design @ beta + offsets, -30, 30)
            rate = np.exp(linear)
            # Mean (not sum) Poisson NLL so the gradient scale is O(1) regardless
            # of caseload magnitude and the convergence tolerance is meaningful.
            value = float(np.sum(rate - counts * linear)) / n_pairs
            grad = (z_design.T @ (rate - counts)) / n_pairs
            return value, grad

        # Poisson NLL is convex; BFGS with the analytic gradient converges on the
        # standardised design. (L-BFGS-B is avoided: its Fortran extension is not
        # loadable in every SciPy/Windows build.)
        result = minimize(objective, np.zeros(z_design.shape[1]), method="BFGS", jac=True)
        gradient_norm = float(np.max(np.abs(objective(result.x)[1])))
        if not result.success and gradient_norm > 1e-4:
            raise ValueError(
                f"Gravity model fitting failed to converge ({result.message}); "
                f"max|gradient|={gradient_norm:.3g}"
            )
        self.gravity_fit_converged = bool(result.success)
        beta = np.where(identifiable, result.x, 0.0)
        self.model = beta / sigma_safe
        return {
            **{f"coefficient_{index}": float(value) for index, value in enumerate(self.model)},
            "converged": bool(result.success),
            "max_abs_gradient": gradient_norm,
            "unidentified_terms": unidentified_terms,
            "n_pairs": int(len(counts)),
        }

    def allocate_flows(
        self,
        origin_outflows: np.ndarray,
        destination_idp_stock: np.ndarray,
        destination_population: np.ndarray,
        distance_matrix: np.ndarray,
        coverage_weight: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Allocate predicted outflows to destinations.

        Renormalises predicted flows within each origin so allocation is
        mass-conserving.

        Args:
            origin_outflows: Predicted outflow from each origin
            destination_idp_stock: Standing IDP population at each destination
            destination_population: Total population at each destination
            distance_matrix: Distance matrix
            coverage_weight: Explicit correction for PRMN monitoring bias

        Returns:
            (destination_inflows, site_pressure)
            where site_pressure = arrivals / standing_idp_population

        Raises:
            NotImplementedError: Allocation not yet implemented
        """
        origin_outflows = np.asarray(origin_outflows, dtype=float)
        stock = np.asarray(destination_idp_stock, dtype=float)
        population = np.asarray(destination_population, dtype=float)
        distances = np.asarray(distance_matrix, dtype=float)
        n_origins, n_destinations = distances.shape
        if len(origin_outflows) != n_origins or len(stock) != n_destinations or len(population) != n_destinations:
            raise ValueError("Flow arrays and distance_matrix dimensions do not match")
        if np.any(origin_outflows < 0) or np.any(stock < 0) or np.any(population < 0):
            raise ValueError("Flow and population values cannot be negative")
        if coverage_weight is not None and coverage_weight <= 0:
            raise ValueError("coverage_weight must be positive when provided")

        flows = np.zeros((n_origins, n_destinations), dtype=float)
        for origin in range(n_origins):
            distance_term = np.zeros(n_destinations) if self.distance_friction is None else -self.distance_friction * np.log(np.maximum(distances[origin], 1e-6))
            if self.model is None:
                score = np.log1p(stock) + distance_term
            else:
                design = np.column_stack([
                    np.log1p(stock), np.log1p(population), np.log(np.maximum(distances[origin], 1e-6)),
                    np.zeros(n_destinations), (np.arange(n_destinations) == origin).astype(float),
                ])
                score = design @ self.model
            weights = np.exp(np.clip(score, -30, 30))
            weights /= weights.sum()
            flows[origin] = origin_outflows[origin] * weights
        arrivals = flows.sum(axis=0)
        if coverage_weight is not None:
            arrivals = arrivals / coverage_weight
            flows *= (origin_outflows.sum() / max(arrivals.sum(), 1e-12))
            arrivals = flows.sum(axis=0)
        return arrivals, self.calculate_site_pressure(arrivals, stock)

    @staticmethod
    def _population_values(population_df: pd.DataFrame, column: str) -> np.ndarray:
        if column not in population_df:
            raise ValueError(f"population_df must contain '{column}'")
        return population_df[column].to_numpy(dtype=float)

    def calculate_site_pressure(
        self,
        forecast_arrivals: np.ndarray,
        standing_idp_population: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate site pressure.

        Site pressure = forecast arrivals as % of standing IDP population.
        A site absorbing 5% needs nothing. One absorbing 40% needs land,
        WASH, site management secured before arrivals.

        Args:
            forecast_arrivals: Predicted arrivals at each site
            standing_idp_population: Current IDP population at each site

        Returns:
            Site pressure as decimal (0 = 0%, 1 = 100%)
        """
        site_pressure = np.zeros_like(forecast_arrivals, dtype=float)
        for i in range(len(forecast_arrivals)):
            if standing_idp_population[i] > 0:
                site_pressure[i] = forecast_arrivals[i] / standing_idp_population[i]
        return site_pressure


@dataclass
class DisplacementForecast:
    """Complete displacement forecast with generation and allocation."""

    date: pd.Timestamp
    generation_forecast: pd.DataFrame  # District-level outflow forecasts
    allocation_forecast: pd.DataFrame  # OD matrix of allocated flows
    site_pressure: pd.DataFrame  # Site-level pressure (arrivals / IDP stock)
    vulnerability_multiplier_used: float
    coverage_weight_used: Optional[float]
    skill_metrics_2023: Optional[Dict[str, float]] = None
    skill_metrics_2022: Optional[Dict[str, float]] = None

    def validate_mass_conservation(self, tolerance: float = 0.01) -> bool:
        """
        Check that total outflow == total inflow (within tolerance).

        Args:
            tolerance: Acceptable relative difference

        Returns:
            True if mass conserved, False otherwise
        """
        total_outflow = self.generation_forecast["predicted_flow"].sum()
        total_inflow = self.allocation_forecast.sum().sum()
        relative_diff = abs(total_outflow - total_inflow) / total_outflow
        return relative_diff <= tolerance
