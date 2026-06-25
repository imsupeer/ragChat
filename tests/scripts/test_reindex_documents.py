import json
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import reindex_documents as reindex_script


def test_reindex_script_defaults_to_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(
        reindex_script,
        "run_direct",
        lambda **kwargs: {
            "dry_run": kwargs["dry_run"],
            "active_provider": "local_hash",
            "active_model": "local-hash-v1",
            "active_collection": "rag_local_hash_local_hash_v1_384",
            "summary": {"total": 0, "would_reindex": 0},
            "documents": [],
        },
    )
    monkeypatch.setattr(reindex_script, "backend_reachable", lambda *args, **kwargs: False)

    code = reindex_script.main([])

    assert code == 0
    assert "dry-run" in capsys.readouterr().out


def test_reindex_script_run_requires_confirmation(monkeypatch, capsys):
    code = reindex_script.main(["--run"])

    assert code == 2
    assert "confirm" in capsys.readouterr().err.lower()


def test_reindex_script_run_with_yes(monkeypatch, capsys):
    captured = {}

    def fake_run_direct(**kwargs):
        captured.update(kwargs)
        return {
            "dry_run": kwargs["dry_run"],
            "active_provider": "local_hash",
            "active_model": "local-hash-v1",
            "active_collection": "rag_local_hash_local_hash_v1_384",
            "summary": {"reindexed": 1},
            "documents": [],
        }

    monkeypatch.setattr(reindex_script, "run_direct", fake_run_direct)
    monkeypatch.setattr(reindex_script, "backend_reachable", lambda *args, **kwargs: False)

    code = reindex_script.main(["--run", "--yes", "--direct"])

    assert code == 0
    assert captured["dry_run"] is False


def test_reindex_script_json_output(monkeypatch, capsys):
    monkeypatch.setattr(
        reindex_script,
        "run_direct",
        lambda **kwargs: {
            "dry_run": True,
            "active_provider": "local_hash",
            "active_model": "local-hash-v1",
            "active_collection": "rag_local_hash_local_hash_v1_384",
            "summary": {"total": 0},
            "documents": [],
        },
    )
    monkeypatch.setattr(reindex_script, "backend_reachable", lambda *args, **kwargs: False)

    code = reindex_script.main(["--json", "--direct"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True


def test_reindex_script_backend_unavailable_falls_back(monkeypatch):
    calls = {"direct": 0}

    def fake_run_direct(**kwargs):
        calls["direct"] += 1
        return {
            "dry_run": True,
            "active_provider": "local_hash",
            "active_model": "local-hash-v1",
            "active_collection": "rag_local_hash_local_hash_v1_384",
            "summary": {"total": 0},
            "documents": [],
        }

    monkeypatch.setattr(reindex_script, "run_direct", fake_run_direct)
    monkeypatch.setattr(reindex_script, "backend_reachable", lambda *args, **kwargs: False)

    code = reindex_script.main(["--yes", "--direct"])

    assert code == 0
    assert calls["direct"] == 1
