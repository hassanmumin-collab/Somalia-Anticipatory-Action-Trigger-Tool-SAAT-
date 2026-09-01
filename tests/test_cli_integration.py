"""End-to-end tests for CLI decision workflows."""

import json
from pathlib import Path

import pandas as pd

from saat import cli


def test_demo_runs_every_module_offline_and_labels_synthetic_data(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["saat", "demo"])
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out
    # One PASS line per module self-test suite.
    for module in ("verification", "trigger", "hazard", "displacement", "economic", "panel"):
        assert module in out
    assert out.count("PASS") >= 6
    assert "All module self-tests passed" in out


def test_verify_command_runs_cost_loss_optimization(tmp_path, capsys):
    panel_path = tmp_path / "panel.csv"
    pd.DataFrame(
        {
            "forecast": [0.1, 0.2, 0.8, 0.9],
            "event": [0, 0, 1, 1],
        }
    ).to_csv(panel_path, index=False)
    import sys

    sys.argv = [
        "saat", "verify", "--panel", str(panel_path), "--forecast", "forecast",
        "--observation", "event", "--cost-action", "1", "--loss-event", "10",
        "--mitigation-effectiveness", "0.8", "--base-rate", "0.5",
    ]
    assert cli.main() == 0
    assert '"threshold": 0.8' in capsys.readouterr().out


def test_evaluate_command_logs_all_configured_tiers(tmp_path, monkeypatch):
    readings_path = tmp_path / "readings.json"
    output_path = tmp_path / "evaluations.jsonl"
    readings_path.write_text(json.dumps({str(index): [] for index in range(4)}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "saat",
            "evaluate",
            "--readings",
            str(readings_path),
            "--config",
            str(Path("config/triggers.yml")),
            "--output",
            str(output_path),
        ],
    )
    assert cli.main() == 0
    record = json.loads(output_path.read_text(encoding="utf-8").strip())
    assert record["system_status"] == "INACTIVE"
    assert set(record["tier_evaluations"]) == {"0", "1", "2", "3"}
