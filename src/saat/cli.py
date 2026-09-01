"""
Command-line interface for SAAT.

Commands:
  saat doctor       - Check Python version, config, packages, credentials, network
  saat preflight    - Check which sources are alive and how fresh
  saat build-panel  - Assemble the district-month panel
  saat verify       - Optimize a threshold against a record
  saat evaluate     - Run the engine over current readings
  saat demo         - Run all module self-tests offline, no credentials
"""

import argparse
import sys
import logging
import json
from pathlib import Path

from saat.config import get_config, Config


def setup_logging(verbosity: str = "INFO") -> None:
    """Set up logging configuration."""
    log_level = getattr(logging, verbosity.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_doctor(args) -> int:
    """
    Check Python version, config files, packages, credentials, network reachability.

    Returns:
        0 if all checks pass, 1 otherwise.
    """
    print("SAAT Doctor Report")
    print("=" * 60)

    # Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"✓ Python version: {py_version}")

    # Config
    try:
        config = get_config()
        print(f"✓ Project root: {config.project_root}")
        print(f"✓ Config directory: {config.config_dir} (exists: {config.config_dir.exists()})")
        print(f"✓ Data directory: {config.data_dir} (exists: {config.data_dir.exists()})")
    except Exception as e:
        print(f"✗ Config error: {e}")
        return 1

    # Packages
    required_packages = ["numpy", "pandas", "yaml", "requests"]
    print("\nPackage checks:")
    for pkg in required_packages:
        try:
            __import__(pkg)
            print(f"  ✓ {pkg}")
        except ImportError:
            print(f"  ✗ {pkg} not installed")
            return 1

    # Credentials (check for .env)
    print("\nCredentials:")
    env_file = config.project_root / ".env"
    if env_file.exists():
        print(f"  ✓ .env file found")
        # Don't print actual credentials
        if config.acled_key:
            print(f"    - ACLED_KEY: set")
        if config.cds_key:
            print(f"    - CDS_KEY: set")
    else:
        print(f"  ⊘ .env file not found (optional for doctor/demo)")

    # Network reachability
    print("\nNetwork reachability:")
    import socket

    hosts = [
        ("CHIRPS", "data.chc.ucsb.edu"),
        ("FRRIMS", "frrims.faoswalim.org"),
        ("HAPI", "hapi.humdata.org"),
        ("CKAN", "data.humdata.org"),
        ("CDS", "cds.climate.copernicus.eu"),
    ]

    for name, host in hosts:
        try:
            socket.create_connection((host, 443), timeout=5)
            print(f"  ✓ {name}: {host} (reachable)")
        except (socket.timeout, socket.error) as e:
            print(f"  ⊘ {name}: {host} (unreachable: {type(e).__name__})")

    print("\n" + "=" * 60)
    print("Doctor check complete. All critical checks passed.")
    return 0


class _DemoCheckError(Exception):
    """Raised by a demo self-test when an operational property does not hold."""


def _demo_verification() -> list:
    """Cost-loss engine: infeasibility guard, cheap-action/high-FAR value, metrics."""
    import numpy as np
    from saat.verification import CostLossModel, CostLossParameters, ContingencyMetrics

    lines = []

    # Feasibility guard: C/L >= f must raise, not return a threshold.
    try:
        CostLossModel(
            CostLossParameters(
                cost_action=10.0, loss_event=10.0,
                mitigation_effectiveness=0.5, climatological_base_rate=0.1,
            )
        )
        raise _DemoCheckError("infeasible C/L >= f did not raise")
    except ValueError as error:
        if "INFEASIBLE" not in str(error):
            raise _DemoCheckError(f"unexpected feasibility error: {error}")
        lines.append(f"infeasible params rejected: {str(error).split('.')[0]}.")

    # Cheap action, forecast that cannot separate events cleanly: the optimum
    # keeps POD = 1, tolerates FAR > 0.5, and still beats both trivial strategies.
    params = CostLossParameters(
        cost_action=1.0, loss_event=100.0,
        mitigation_effectiveness=0.9, climatological_base_rate=0.2,
    )
    model = CostLossModel(params)
    forecasts = np.array(
        [0.60, 0.58, 0.56, 0.54]
        + [0.62, 0.61, 0.59, 0.57, 0.55]
        + [0.30, 0.25, 0.22, 0.20, 0.18, 0.15, 0.12, 0.10, 0.08, 0.05, 0.03]
    )
    observations = np.array([1] * 4 + [0] * 16)
    outcome = model.optimize_threshold(observations, forecasts)
    if not (outcome.pod == 1.0 and outcome.far > 0.5 and outcome.relative_economic_value > 0.5):
        raise _DemoCheckError(
            f"cheap-action operating point wrong: POD={outcome.pod}, "
            f"FAR={outcome.far}, V={outcome.relative_economic_value}"
        )
    lines.append(
        f"cheap action: threshold={outcome.threshold:.2f}, POD={outcome.pod:.2f}, "
        f"FAR={outcome.far:.2f} (>0.5), V={outcome.relative_economic_value:.2f} (>0.5)"
    )

    # An unsatisfiable POD/FAR constraint must raise, not silently relax.
    try:
        model.optimize_threshold(
            np.array([0, 0, 0, 0, 0]), np.array([0.1, 0.2, 0.3, 0.4, 0.5]), min_pod=0.5
        )
        raise _DemoCheckError("unsatisfiable POD constraint did not raise")
    except ValueError as error:
        lines.append(f"unsatisfiable constraint rejected: {str(error).split('.')[0]}.")

    metrics = ContingencyMetrics(hits=8, false_alarms=2, misses=2, correct_negatives=88)
    lines.append(
        f"contingency metrics: POD={metrics.pod:.2f}, FAR={metrics.far:.2f}, "
        f"PSS={metrics.pss:.2f}, bias={metrics.frequency_bias:.2f}"
    )
    return lines


def _demo_trigger() -> list:
    """Fail-loud engine: missing data escalates, an absent tier is never silent."""
    from datetime import datetime
    from saat.trigger import (
        DataStatus, IndicatorReading, SystemEvaluator, TierEvaluator, TierStatus,
    )

    now = datetime(2026, 10, 1)
    lines = []

    def reading(value, status):
        return IndicatorReading(
            indicator_name="frrims_stage", value=value, threshold=6.0, operator=">=",
            data_status=status, source="FRRIMS", timestamp=now, last_update=now,
            update_age_hours=1.0,
        )

    evaluator = TierEvaluator("Immediate Action", 3, "or")

    # A value that WOULD clear the threshold, but the feed is MISSING: the tier
    # must escalate for human review, not report calm.
    escalated = evaluator.evaluate([reading(7.5, DataStatus.MISSING)])
    if escalated.status != TierStatus.ESCALATION:
        raise _DemoCheckError(f"missing data gave {escalated.status}, expected ESCALATION")
    lines.append("missing feed that could have activated -> ESCALATION (not INACTIVE)")

    healthy = evaluator.evaluate([reading(7.5, DataStatus.OK)])
    if healthy.status != TierStatus.ACTIVE:
        raise _DemoCheckError(f"healthy over-threshold reading gave {healthy.status}")
    lines.append("healthy reading over threshold -> ACTIVE")

    system = SystemEvaluator()
    for tier in range(3):
        system.add_tier(tier, TierEvaluator(f"Tier {tier}", tier, "or"))
    system.add_tier(3, evaluator)
    # Tier 2 omitted from the readings entirely.
    result = system.evaluate({0: [], 1: [], 3: [reading(2.0, DataStatus.OK)]})
    if not any("Tier 2" in item for item in result.escalations):
        raise _DemoCheckError("absent tier did not produce an escalation")
    lines.append("tier absent from input -> escalation, not silence")
    return lines


def _demo_hazard() -> list:
    """Drought-to-flood compounding and exact routing-lag shift."""
    import numpy as np
    from datetime import datetime, timedelta
    from saat.hazard import AMCClassifier, RouteCalculator, SCSRunoffModel

    lines = []

    # Desiccated (crusted) soil must yield a HIGHER runoff coefficient than a
    # normally wetted profile -- the inverted AMC-I treatment.
    classifier = AMCClassifier(climate_90day_15th_percentile=20.0)
    desiccated = classifier.classify(prior_5day_mm=0.0, prior_90day_mm=5.0)
    normal = classifier.classify(prior_5day_mm=20.0, prior_90day_mm=120.0)
    model = SCSRunoffModel(use_inverted_amc_i=True)
    dry_runoff = model.simulate_event_runoff(60.0, desiccated)
    normal_runoff = model.simulate_event_runoff(60.0, normal)
    if not dry_runoff > normal_runoff:
        raise _DemoCheckError(
            f"desiccated soil runoff {dry_runoff:.1f} mm did not exceed normal {normal_runoff:.1f} mm"
        )
    lines.append(
        f"60 mm event: crusted AMC-I ({desiccated.class_type}) -> {dry_runoff:.1f} mm runoff "
        f"vs normal AMC-II -> {normal_runoff:.1f} mm  [MODELLING JUDGEMENT: inversion not "
        f"Somalia-calibrated]"
    )

    # Routing lag must shift the upstream signal forward by exactly the lag.
    lag = 4
    rain = np.zeros(30)
    rain[10] = 55.0
    dates = np.array([datetime(2026, 10, 1) + timedelta(days=i) for i in range(30)])
    routed_rain, routed_dates = RouteCalculator(lag, "Shabelle").route_rainfall(rain, dates)
    spike = int(np.argmax(routed_rain))
    if spike != 10 + lag:
        raise _DemoCheckError(f"routing spike landed at index {spike}, expected {10 + lag}")
    lines.append(f"upstream spike at day 10 arrives at gauge on day {spike} (lag {lag}, exact)")
    return lines


def _demo_displacement() -> list:
    """Two-stage model: circular features excluded, allocation conserves mass."""
    import numpy as np
    import pandas as pd
    from saat.displacement import AllocationModel, AllocationModelConfig, GenerationModel

    lines = []

    # IPC / FEWS NET phase columns must never enter the feature matrix.
    panel = pd.DataFrame(
        {
            "district": ["Baidoa"] * 6 + ["Luuq"] * 6,
            "year_month": list(pd.date_range("2023-01-01", periods=6, freq="MS")) * 2,
            "rainfall_anomaly_pct": np.linspace(-20, 80, 12),
            "flash_index": np.linspace(0, 1, 12),
            "cereal_price_anomaly": np.linspace(0, 40, 12),
            "ipc_phase": [3, 3, 4, 4, 5, 5] * 2,
            "fews_net_projection": [3, 4, 4, 5, 5, 4] * 2,
        }
    )
    features = GenerationModel().get_features(panel)
    leaked = [c for c in features.columns if "ipc" in c.lower() or "fews" in c.lower()]
    if leaked:
        raise _DemoCheckError(f"circular features leaked into matrix: {leaked}")
    lines.append(f"generation features: {list(features.columns)} (IPC/FEWS excluded)")

    # Gravity allocation must be mass-conserving and yield site pressure.
    # Destination choice blends clan-corridor pull (destination IDP stock) with
    # distance decay -- not distance-minimising.
    allocator = AllocationModel(AllocationModelConfig(distance_friction=1.3))
    allocator.distance_friction = 1.3  # used directly by allocate_flows without a prior fit
    origin_outflows = np.array([9000.0, 4000.0, 0.0])
    idp_stock = np.array([50000.0, 2000.0, 15000.0])
    population = np.array([300000.0, 40000.0, 120000.0])
    distance = np.array([[1.0, 120.0, 240.0], [120.0, 1.0, 90.0], [240.0, 90.0, 1.0]])
    arrivals, pressure = allocator.allocate_flows(
        origin_outflows, idp_stock, population, distance
    )
    if abs(arrivals.sum() - origin_outflows.sum()) > 1e-6:
        raise _DemoCheckError(
            f"allocation not mass-conserving: in={origin_outflows.sum()}, out={arrivals.sum()}"
        )
    lines.append(
        f"allocated {origin_outflows.sum():,.0f} arrivals mass-conservingly; "
        f"site pressure = {np.round(pressure, 2).tolist()} (arrivals / standing IDP pop)"
    )
    lines.append(
        "NOTE: vulnerability_multiplier defaults to 1.0 and coverage_weight to none; "
        "running with the defaults is a documented decision."
    )
    return lines


def _demo_economic() -> list:
    """Four loss channels: conditional vs expected RVF, recovery kept separate."""
    from saat.economic import (
        CropLoss, CropType, GrowthStage, LivestockRVFLoss, RecoveryUpside,
        SecondOrderIrrigationDamage, SubmergenceDamageCurve,
    )

    lines = []

    curve = SubmergenceDamageCurve(
        crop_type=CropType.MAIZE, growth_stage=GrowthStage.VEGETATIVE,
        critical_duration_days=5.0,
        loss_fraction_at_duration={1: 0.15, 3: 0.8, 5: 0.97, 10: 1.0},
    )
    crop = CropLoss(
        crop_type=CropType.MAIZE, growth_stage=GrowthStage.VEGETATIVE,
        inundated_area_hectares=1000.0, submergence_duration_days=4.0,
        yield_kg_per_hectare=1200.0, price_usd_per_kg=0.45,
    )
    crop_loss = crop.calculate_loss(curve)
    lines.append(
        f"crop loss (4-day submergence, illustrative curve): ${crop_loss:,.0f} "
        f"[curve shape not Somalia-calibrated]"
    )

    rvf = LivestockRVFLoss(
        livestock_type="goats", monthly_export_value_usd=40_000_000.0,
        p_outbreak_given_flood=0.3, p_ban_given_outbreak=0.6,
        expected_ban_duration_months=6.0,
    )
    lines.append(
        f"RVF/export ban: expected ${rvf.calculate_expected_loss():,.0f}  |  "
        f"conditional-on-outbreak ${rvf.calculate_conditional_loss():,.0f} "
        f"[probabilities poorly constrained: 1997-98, 2006-07 only]"
    )

    second_order = SecondOrderIrrigationDamage(
        canal_length_km=80.0, canal_desilting_cost_per_km_usd=12000.0,
        embankment_repair_cost_usd=2_500_000.0, barrage_damage_fraction=0.4,
        irrigated_area_hectares_next=15000.0, yield_loss_fraction_next_season=0.35,
        yield_kg_per_hectare=1400.0, price_usd_per_kg=0.4,
    )
    lines.append(
        f"second-order irrigation damage (headline sensitivity): "
        f"${second_order.calculate_total_second_order_cost():,.0f} -- decides one- vs "
        f"two-season shock [placeholder penalty]"
    )

    recovery = RecoveryUpside(
        pasture_recovery_gain_fraction=0.5, breeding_rate_improvement_percent=15.0,
        post_flood_herd_size=200000, next_season_yield_improvement_fraction=0.3,
    )
    lines.append(
        f"recovery upside reported on a SEPARATE 12-18 month axis "
        f"(+{recovery.calculate_recovery_benefit(45.0):,.0f} kg herd productivity); "
        f"never netted against the immediate caseload"
    )
    return lines


def _demo_panel() -> list:
    """Panel assembly is balanced; PRMN column resolution fails loudly."""
    import pandas as pd
    from saat.panel import PanelAssembler, PRMNLoader

    lines = []

    prmn = pd.DataFrame(
        {
            "Month End": ["2023-01-31", "2023-01-31", "2023-03-31"],
            "Previous (Departure) District": ["Baidoa", "Luuq", "Baidoa"],
            "Current (Arrival) District": ["Mogadishu", "Doolow", "Mogadishu"],
            "Number of Individuals": ["7,500", "1,200", "9,000"],
        }
    )
    loaded = PRMNLoader().load_prmn(prmn, material_threshold=5000)
    panel = PanelAssembler().assemble(loaded, material_threshold=5000)
    districts = panel["district"].nunique()
    months = panel["year_month"].nunique()
    if len(panel) != districts * months:
        raise _DemoCheckError(
            f"panel not balanced: {len(panel)} rows != {districts} districts x {months} months"
        )
    zero_months = int((panel["outflow"] == 0).sum())
    lines.append(
        f"balanced panel: {districts} districts x {months} months = {len(panel)} rows, "
        f"{zero_months} true-zero district-months kept (base rate preserved)"
    )

    try:
        PRMNLoader().resolve_columns(
            pd.DataFrame({"when": [], "who_left": [], "who_arrived": [], "how_many": []})
        )
        raise _DemoCheckError("unrecognised PRMN headers did not raise")
    except ValueError as error:
        if "Observed headers" not in str(error):
            raise _DemoCheckError(f"column-resolution error missing observed headers: {error}")
        lines.append("unknown PRMN headers -> ValueError naming the observed headers")
    return lines


def cmd_demo(args) -> int:
    """
    Run every module's offline self-test with synthetic data.

    No network and no credentials are used. All inputs are synthetic and are
    labelled as such in the output.

    Returns:
        0 if all self-tests pass, 1 otherwise.
    """
    print("SAAT Demo - Offline Module Self-Tests")
    print("=" * 60)
    print("All data below is SYNTHETIC and illustrative. No network, no credentials.")
    print("Numbers here are not estimates for Somalia.")

    suites = [
        ("verification  (cost-loss decision engine)", _demo_verification),
        ("trigger       (fail-loud tier evaluation)", _demo_trigger),
        ("hazard        (routing + AMC runoff)", _demo_hazard),
        ("displacement  (generation + gravity allocation)", _demo_displacement),
        ("economic      (four monetised loss channels)", _demo_economic),
        ("panel         (balanced district-month assembly)", _demo_panel),
    ]

    failures = 0
    for title, suite in suites:
        print(f"\n[SYNTHETIC] {title}")
        try:
            for line in suite():
                print(f"  - {line}")
            print("  PASS")
        except Exception as error:  # noqa: BLE001 - demo reports every failure
            failures += 1
            print(f"  FAIL: {error}")
            if not isinstance(error, _DemoCheckError):
                import traceback

                traceback.print_exc()

    print("\n" + "=" * 60)
    if failures:
        print(f"Demo FAILED: {failures} module self-test(s) did not pass (synthetic data).")
        return 1
    print("Demo complete. All module self-tests passed (synthetic data).")
    return 0


def cmd_preflight(args) -> int:
    """Check which sources are alive and how fresh."""
    print("SAAT Preflight - Data Source Status")
    print("=" * 60)
    from saat.sources import SourceHealthChecker

    statuses = SourceHealthChecker.check_all_sources()
    failures = 0
    for name, status in statuses.items():
        marker = "✓" if status["is_reachable"] else "✗"
        if status["status_code"] and not status.get("http_ok", True):
            detail = f"reachable; HTTP {status['status_code']} ({status['error_message']})"
        else:
            detail = f"HTTP {status['status_code']}" if status["status_code"] else status["error_message"]
        print(f"  {marker} {name}: {detail}")
        if not status["is_reachable"]:
            failures += 1
    print(f"\nChecked {len(statuses)} sources; {failures} unreachable.")
    return 1 if failures else 0


def cmd_build_panel(args) -> int:
    """Assemble the district-month panel."""
    print("SAAT Build Panel")
    print("=" * 60)
    if not args.prmn_csv:
        print("Provide --prmn-csv with a PRMN export; no data source was silently assumed.")
        return 2
    try:
        import pandas as pd
        from saat.panel import PanelAssembler, PRMNLoader

        if Path(args.prmn_csv).suffix.lower() in {".xlsx", ".xls"}:
            raw = pd.read_excel(args.prmn_csv)
        else:
            raw = pd.read_csv(args.prmn_csv)
        prmn = PRMNLoader().load_prmn(raw, material_threshold=args.material_threshold)
        panel = PanelAssembler().assemble(prmn, material_threshold=args.material_threshold)
        panel.to_csv(args.output, index=False)
        print(f"Wrote balanced panel: {args.output} ({len(panel)} district-month rows)")
        return 0
    except Exception as error:
        print(f"Panel build failed: {error}")
        return 1


def cmd_verify(args) -> int:
    """Optimize a threshold against a record."""
    print("SAAT Verify")
    print("=" * 60)
    try:
        import numpy as np
        import pandas as pd
        from saat.verification import CostLossModel, CostLossParameters

        panel = pd.read_csv(args.panel)
        if args.forecast not in panel or args.observation not in panel:
            raise ValueError(
                f"Panel must contain '{args.forecast}' and '{args.observation}' columns"
            )
        params = CostLossParameters(
            cost_action=args.cost_action,
            loss_event=args.loss_event,
            mitigation_effectiveness=args.mitigation_effectiveness,
            climatological_base_rate=args.base_rate,
        )
        model = CostLossModel(params)
        outcome = model.optimize_threshold(
            panel[args.observation].to_numpy(dtype=int),
            panel[args.forecast].to_numpy(dtype=float),
            min_pod=args.min_pod,
            max_far=args.max_far,
        )
        print(json.dumps({
            "threshold": outcome.threshold,
            "expected_expense": outcome.expected_expense,
            "relative_economic_value": outcome.relative_economic_value,
            "pod": outcome.pod,
            "far": outcome.far,
            "pss": outcome.pss,
        }, indent=2, default=lambda value: None if not np.isfinite(value) else float(value)))
        return 0
    except Exception as error:
        print(f"Verification failed: {error}")
        return 1


def cmd_evaluate(args) -> int:
    """Run the engine over current readings."""
    print("SAAT Evaluate")
    print("=" * 60)
    try:
        from datetime import datetime
        import yaml
        from saat.trigger import DataStatus, IndicatorReading, SystemEvaluator, TierEvaluator

        with open(args.readings, encoding="utf-8") as file:
            payload = json.load(file)
        with open(args.config, encoding="utf-8") as file:
            trigger_config = yaml.safe_load(file)
        evaluator = SystemEvaluator()
        tier_readings = {}
        for tier_number in range(4):
            tier = trigger_config[f"tier_{tier_number}"]
            logic = tier.get("combination_logic", {}).get("type", "and")
            evaluator.add_tier(tier_number, TierEvaluator(tier["name"], tier_number, logic))
            readings = []
            for item in payload.get(str(tier_number), payload.get(tier_number, [])):
                readings.append(IndicatorReading(
                    indicator_name=item["indicator_name"], value=item.get("value"),
                    threshold=item["threshold"], operator=item.get("operator", ">="),
                    data_status=DataStatus(item.get("data_status", "OK")),
                    source=item["source"], timestamp=datetime.fromisoformat(item["timestamp"]),
                    last_update=datetime.fromisoformat(item["last_update"]),
                    update_age_hours=float(item.get("update_age_hours", 0)),
                    fallback_used=bool(item.get("fallback_used", False)),
                    fallback_source=item.get("fallback_source"), notes=item.get("notes"),
                ))
            tier_readings[tier_number] = readings
        result = evaluator.evaluate(tier_readings)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "a", encoding="utf-8") as file:
            file.write(result.to_jsonl() + "\n")
        print(result.to_jsonl())
        return 0 if result.system_status.value != "ESCALATION" else 2
    except Exception as error:
        print(f"Evaluation failed: {error}")
        return 1


def main() -> int:
    """Main entry point for the SAAT CLI."""
    parser = argparse.ArgumentParser(
        description="Somalia Anticipatory Action Trigger tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  saat doctor      # Check system configuration
  saat demo        # Run offline self-tests
  saat evaluate    # Run trigger engine
        """,
    )

    parser.add_argument(
        "-v",
        "--verbosity",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Doctor command
    subparsers.add_parser("doctor", help="Check configuration and network")

    # Demo command
    subparsers.add_parser("demo", help="Run offline self-tests")

    # Preflight command
    subparsers.add_parser("preflight", help="Check data source status")

    # Build panel command
    build_panel_parser = subparsers.add_parser("build-panel", help="Assemble data panel")
    build_panel_parser.add_argument("--prmn-csv", help="Path to a PRMN CSV export")
    build_panel_parser.add_argument("--output", default="panel.csv", help="Output panel CSV path")
    build_panel_parser.add_argument(
        "--material-threshold", type=int, default=5000, help="Material displacement threshold"
    )

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Optimize threshold")
    verify_parser.add_argument("--panel", required=True, help="Panel CSV path")
    verify_parser.add_argument("--forecast", required=True, help="Forecast-value column")
    verify_parser.add_argument("--observation", required=True, help="Binary event column")
    verify_parser.add_argument("--cost-action", type=float, required=True)
    verify_parser.add_argument("--loss-event", type=float, required=True)
    verify_parser.add_argument("--mitigation-effectiveness", type=float, required=True)
    verify_parser.add_argument("--base-rate", type=float, required=True)
    verify_parser.add_argument("--min-pod", type=float)
    verify_parser.add_argument("--max-far", type=float)

    # Evaluate command
    evaluate_parser = subparsers.add_parser("evaluate", help="Run trigger engine")
    evaluate_parser.add_argument("--readings", required=True, help="Current readings JSON")
    evaluate_parser.add_argument("--config", default="config/triggers.yml")
    evaluate_parser.add_argument("--output", default="logs/evaluations.jsonl")

    args = parser.parse_args()

    # Set up logging
    setup_logging(args.verbosity)

    # Route to command handler
    if args.command == "doctor":
        return cmd_doctor(args)
    elif args.command == "demo":
        return cmd_demo(args)
    elif args.command == "preflight":
        return cmd_preflight(args)
    elif args.command == "build-panel":
        return cmd_build_panel(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "evaluate":
        return cmd_evaluate(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
