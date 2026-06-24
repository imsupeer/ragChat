from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_models import router as models_router
from core.dependencies import get_local_metrics_service, get_model_settings_service
from services.metrics import LocalMetrics
from services.model_catalog import load_model_catalog
from services.model_settings import ModelSettingsService


def build_client(service: ModelSettingsService):
    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_model_settings_service] = lambda: service
    app.dependency_overrides[get_local_metrics_service] = lambda: LocalMetrics()
    return TestClient(app)


@pytest.fixture
def settings_service(tmp_path: Path) -> ModelSettingsService:
    return ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: ["llama3.1:8b", "qwen3:8b"],
        catalog_loader=load_model_catalog,
    )


def test_get_model_settings_returns_default_state(settings_service: ModelSettingsService):
    with build_client(settings_service) as client:
        response = client.get("/models/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["chat_model"] == "llama3.1:8b"
    assert payload["default_chat_model"] == "llama3.1:8b"
    assert payload["use_chat_model_for_query_rewrite"] is False


def test_put_model_settings_updates_chat_model(settings_service: ModelSettingsService):
    with build_client(settings_service) as client:
        response = client.put(
            "/models/settings",
            json={"chat_model": "qwen3:8b", "require_installed": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_model"] == "qwen3:8b"
    assert payload["source"] == "user"
    assert payload["installed_status"] == "installed"


def test_put_model_settings_rejects_not_installed_model(settings_service: ModelSettingsService):
    with build_client(settings_service) as client:
        response = client.put(
            "/models/settings",
            json={"chat_model": "mistral:7b", "require_installed": True},
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    message = detail["message"] if isinstance(detail, dict) else detail
    assert "ollama pull" in message.lower()
    if isinstance(detail, dict):
        assert detail["install_command"] == "ollama pull mistral:7b"


def test_get_model_settings_includes_query_rewrite_policy(settings_service: ModelSettingsService):
    with build_client(settings_service) as client:
        response = client.get("/models/settings")

    payload = response.json()
    assert "query_rewrite" in payload
    assert payload["query_rewrite"]["use_chat_model"] is False
    assert payload["query_rewrite"]["configured_model"] == "llama3.1:8b"
    assert payload["query_rewrite"]["effective_model"] == "llama3.1:8b"


def test_get_model_settings_includes_install_metadata(settings_service: ModelSettingsService):
    with build_client(settings_service) as client:
        response = client.get("/models/settings")

    payload = response.json()
    assert payload["catalog_known"] is True
    assert payload["installed"] is True
    assert payload["match_type"] == "exact"
    assert payload["install_command"] == "ollama pull llama3.1:8b"
    assert payload["run_command"] == "ollama run llama3.1:8b"


def test_put_model_settings_accepts_alias_when_installed(tmp_path: Path):
    service = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: ["llama3.1:8b"],
        catalog_loader=load_model_catalog,
    )
    with build_client(service) as client:
        response = client.put(
            "/models/settings",
            json={"chat_model": "llama3.1", "require_installed": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_model"] == "llama3.1"
    assert payload["installed"] is True
    assert payload["match_type"] == "alias"


def test_post_model_settings_reset(settings_service: ModelSettingsService):
    with build_client(settings_service) as client:
        client.put(
            "/models/settings",
            json={"chat_model": "qwen3:8b", "require_installed": True},
        )
        response = client.post("/models/settings/reset")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_model"] == "llama3.1:8b"
    assert payload["source"] == "default"


def test_model_settings_errors_do_not_leak_paths(settings_service: ModelSettingsService):
    with build_client(settings_service) as client:
        response = client.put(
            "/models/settings",
            json={"chat_model": "mistral:7b", "require_installed": True},
        )

    assert "C:\\" not in response.text
    assert "/Users/" not in response.text


def test_put_model_settings_increments_metrics(settings_service: ModelSettingsService):
    metrics = LocalMetrics()
    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_model_settings_service] = lambda: settings_service
    app.dependency_overrides[get_local_metrics_service] = lambda: metrics

    with TestClient(app) as client:
        response = client.put(
            "/models/settings",
            json={"chat_model": "qwen3:8b", "require_installed": True},
        )

    assert response.status_code == 200
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["models.settings.update"] == 1
