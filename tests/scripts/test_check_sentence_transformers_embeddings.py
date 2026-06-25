import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT = ROOT_DIR / "scripts" / "check_sentence_transformers_embeddings.py"
BACKEND_DIR = ROOT_DIR / "backend"
SCRIPTS_DIR = ROOT_DIR / "scripts"
for path in (str(BACKEND_DIR), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import check_sentence_transformers_embeddings as st_check
from services.sentence_transformers_runtime import inspect_sentence_transformers_setup


def run_check_script(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), *args]
    return subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


class FakeModel:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def encode(self, texts, convert_to_numpy=True):
        if isinstance(texts, str):
            return np.array([0.1] * 384, dtype=float)
        return np.array([[0.1] * 384 for _ in texts], dtype=float)


def test_check_script_help_works():
    result = run_check_script("--help")
    assert result.returncode == 0
    assert "strict" in result.stdout.lower()


def test_inspect_reports_missing_dependency(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: None,
    )
    report = inspect_sentence_transformers_setup(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
        device="cpu",
        cache_dir="",
        local_files_only=True,
    )
    assert report["status"] == "missing_dependency"


def test_build_report_json_mode(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: FakeModel,
    )
    report = st_check.build_report(st_check.Settings())
    assert report["status"] == "ok"


def test_main_strict_fails_when_not_ready(monkeypatch):
    monkeypatch.setattr(
        st_check,
        "build_report",
        lambda settings: {"status": "missing_dependency"},
    )
    monkeypatch.setattr(
        "sys.argv",
        ["check_sentence_transformers_embeddings.py", "--strict"],
    )
    with pytest.raises(SystemExit) as excinfo:
        st_check.main()
    assert excinfo.value.code == 1


def test_main_strict_passes_when_ready(monkeypatch, capsys):
    monkeypatch.setattr(
        st_check,
        "build_report",
        lambda settings: {"status": "ok"},
    )
    monkeypatch.setattr(
        "sys.argv",
        ["check_sentence_transformers_embeddings.py", "--strict"],
    )
    st_check.main()
    assert "Status: ok" in capsys.readouterr().out
