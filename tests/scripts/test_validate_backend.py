import subprocess
import sys
from pathlib import Path

from scripts import validate_backend


def test_validate_backend_fast_runs_pytest_only(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, check=False, env=None):
        calls.append(list(cmd))
        result = subprocess.CompletedProcess(cmd, 0)
        return result

    monkeypatch.setattr(validate_backend.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_backend.py", "--fast", "--skip-eval", "--skip-benchmark"],
    )

    validate_backend.main()

    assert len(calls) == 1
    assert calls[0][0] == sys.executable
    assert "-m" in calls[0]
    assert "pytest" in calls[0]
    assert "not live" in calls[0]


def test_validate_backend_returns_nonzero_on_failure(monkeypatch):
    def fake_run(cmd, cwd=None, check=False, env=None):
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(validate_backend.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_backend.py", "--fast", "--skip-eval", "--skip-benchmark"],
    )

    try:
        validate_backend.main()
        raised = False
    except SystemExit as exc:
        raised = True
        assert exc.code != 0

    assert raised


def test_validate_backend_script_exists():
    script = Path(__file__).resolve().parents[2] / "scripts" / "validate_backend.py"
    assert script.exists()
