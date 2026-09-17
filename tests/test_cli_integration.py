"""End-to-end tests for CLI workflows."""

from saat import cli


def test_demo_runs_every_module_offline_and_labels_synthetic_data(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["saat", "demo"])
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out
    # One PASS line per module self-test suite.
    for module in ("hazard", "displacement", "casualties", "economic", "urban_flood", "panel"):
        assert module in out
    assert out.count("PASS") >= 6
    assert "All module self-tests passed" in out
