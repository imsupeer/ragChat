import os

from core.config import Settings, get_settings
from core.dependencies import clear_dependency_caches
from services.metrics import get_local_metrics, reset_local_metrics


def test_clear_dependency_caches_is_idempotent():
    clear_dependency_caches()
    clear_dependency_caches()


def test_clear_dependency_caches_refreshes_settings(monkeypatch):
    monkeypatch.setenv("APP_NAME", "DX Test Workspace")
    clear_dependency_caches()

    assert get_settings().app_name == "DX Test Workspace"

    monkeypatch.delenv("APP_NAME", raising=False)
    clear_dependency_caches()


def test_reset_local_metrics_clears_counters():
    metrics = get_local_metrics()
    metrics.increment("chat.stream.completed", 3)
    metrics.set_last("reconciliation.status", "drift_detected")

    reset_local_metrics()
    refreshed = get_local_metrics()

    assert refreshed is not metrics
    assert refreshed.snapshot()["counters"] == {}
    assert refreshed.snapshot()["last_values"] == {}


def test_settings_fixture_pattern_uses_explicit_paths(test_settings: Settings):
    assert test_settings.sqlite_path.endswith("app.db")
    assert test_settings.documents_directory.endswith("docs")
    assert test_settings.max_upload_bytes == 1024 * 1024


def test_env_override_requires_cache_clear(monkeypatch):
    monkeypatch.setenv("TOP_K", "7")
    clear_dependency_caches()
    assert get_settings().top_k == 7

    monkeypatch.setenv("TOP_K", "9")
    assert get_settings().top_k == 7

    clear_dependency_caches()
    assert get_settings().top_k == 9

    monkeypatch.delenv("TOP_K", raising=False)
    clear_dependency_caches()
