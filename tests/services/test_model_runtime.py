import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.model_catalog import load_model_catalog
from services.model_names import model_matches_installed
from services.model_runtime import ModelRuntimeError, ModelRuntimeService
from services.model_settings import ModelSettingsService
from services.ollama_service import OllamaService
from services.providers.ollama_provider import OllamaProvider


class FakeOllamaRuntime(OllamaService):
    def __init__(
        self,
        *,
        reachable: bool = True,
        installed: list[str] | None = None,
        running: list[str] | None = None,
        ps_detection: str = "available",
        generate_calls: list[dict] | None = None,
    ) -> None:
        super().__init__(
            base_url="http://127.0.0.1:11434",
            model="llama3.1:8b",
            keep_alive="5m",
        )
        self._reachable = reachable
        self._installed = installed or ["llama3.1:8b", "qwen3:8b"]
        self._running = list(running or [])
        self._ps_detection = ps_detection
        self.generate_calls = generate_calls or []

    def is_reachable(self, timeout: float | None = None) -> bool:
        return self._reachable

    def list_installed_models(self, timeout: float | None = None) -> list[str]:
        return list(self._installed) if self._reachable else []

    def list_installed_model_details(self, timeout: float | None = None) -> list[dict]:
        return [
            {"name": name, "family": "test", "size": 1, "modified_at": "now"}
            for name in self._installed
        ]

    def list_running_models(self, timeout: float | None = None) -> dict:
        if not self._reachable:
            return {"detection": "unavailable", "models": []}
        if self._ps_detection == "unsupported":
            return {"detection": "unsupported", "models": []}
        if self._ps_detection == "unavailable":
            return {"detection": "unavailable", "models": []}
        return {
            "detection": "available",
            "models": [
                {
                    "name": name,
                    "expires_at": "2026-06-24T12:00:00Z",
                    "size": 1,
                    "size_vram": 1,
                }
                for name in self._running
            ],
        }

    def _post_generate(self, *, model: str, prompt: str, keep_alive, timeout: float) -> dict:
        self.generate_calls.append(
            {
                "model": model,
                "prompt": prompt,
                "keep_alive": keep_alive,
                "timeout": timeout,
            }
        )
        if keep_alive == 0:
            self._running = [
                name for name in self._running if not model_matches_installed(model, name)
            ]
        elif not any(model_matches_installed(model, name) for name in self._running):
            self._running.append(model)
        return {"done": True}


@pytest.fixture
def runtime_stack(tmp_path: Path):
    settings = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: ["llama3.1:8b", "qwen3:8b"],
        catalog_loader=load_model_catalog,
    )
    ollama = FakeOllamaRuntime(running=["llama3.1:8b"])
    runtime = ModelRuntimeService(
        llm_provider=OllamaProvider(ollama),
        model_settings=settings,
        keep_alive="5m",
    )
    return settings, ollama, runtime


def test_runtime_status_with_ollama_reachable(runtime_stack):
    _, _, runtime = runtime_stack
    status = runtime.get_runtime_status()

    assert status["ollama"]["reachable"] is True
    assert status["installed_models_count"] == 2
    assert status["active_model"]["name"] == "llama3.1:8b"
    assert status["active_model"]["installed"] is True
    assert status["active_model"]["loaded"] is True
    assert status["runtime"]["keep_alive"] == "5m"
    assert status["runtime"]["running_models_count"] == 1
    assert status["runtime"]["loaded_detection"] == "available"
    assert status["provider"]["name"] == "ollama"
    assert status["provider"]["capabilities"]["preload"] is True


def test_runtime_status_with_ollama_unavailable(tmp_path: Path):
    settings = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: [],
        catalog_loader=load_model_catalog,
    )
    ollama = FakeOllamaRuntime(reachable=False)
    runtime = ModelRuntimeService(
        llm_provider=OllamaProvider(ollama),
        model_settings=settings,
        keep_alive="5m",
    )

    status = runtime.get_runtime_status()

    assert status["status"] == "degraded"
    assert status["ollama"]["reachable"] is False
    assert status["active_model"]["installed"] is None
    assert status["active_model"]["loaded"] is None
    assert status["installed_models_count"] == 0


def test_runtime_status_marks_active_model_not_installed(runtime_stack):
    settings, ollama, runtime = runtime_stack
    settings.update_chat_model("mistral:7b", require_installed=False)
    ollama._installed = ["llama3.1:8b"]
    ollama._running = ["llama3.1:8b"]

    status = runtime.get_runtime_status()

    assert status["active_model"]["installed"] is False
    assert status["ollama"]["status"] == "degraded"


def test_runtime_status_installed_not_loaded_sets_cold_start(runtime_stack):
    settings, ollama, runtime = runtime_stack
    ollama._running = []

    status = runtime.get_runtime_status()

    assert status["active_model"]["installed"] is True
    assert status["active_model"]["loaded"] is False
    assert status["runtime"]["cold_start_likely"] is True


def test_runtime_status_loaded_alias_match(runtime_stack):
    settings, ollama, runtime = runtime_stack
    settings.update_chat_model("llama3.1", require_installed=True)
    ollama._running = ["llama3.1:8b"]

    status = runtime.get_runtime_status()

    assert status["active_model"]["loaded"] is True
    assert status["active_model"]["loaded_match_type"] == "alias"


def test_runtime_status_ps_unsupported_marks_loaded_unknown(runtime_stack):
    _, ollama, runtime = runtime_stack
    ollama._ps_detection = "unsupported"

    status = runtime.get_runtime_status()

    assert status["runtime"]["loaded_detection"] == "unsupported"
    assert status["active_model"]["loaded"] is None
    assert status["runtime"]["cold_start_likely"] is None


def test_preload_active_installed_model(runtime_stack):
    settings, ollama, runtime = runtime_stack
    settings.update_chat_model("qwen3:8b", require_installed=True)
    ollama._running = []

    result = runtime.preload_active_model()

    assert result["status"] == "ok"
    assert result["model"] == "qwen3:8b"
    assert result["runtime"]["active_model"]["loaded"] is True
    assert ollama.generate_calls
    assert ollama.generate_calls[0]["model"] == "qwen3:8b"
    assert ollama.generate_calls[0]["keep_alive"] == "5m"


def test_preload_not_installed_returns_install_command(runtime_stack):
    settings, ollama, runtime = runtime_stack
    settings.update_chat_model("mistral:7b", require_installed=False)
    ollama._installed = ["llama3.1:8b"]

    with pytest.raises(ModelRuntimeError, match="ollama pull"):
        runtime.preload_active_model()

    assert ollama.generate_calls == []


def test_preload_ollama_unavailable(tmp_path: Path):
    settings = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: [],
        catalog_loader=load_model_catalog,
    )
    runtime = ModelRuntimeService(
        llm_provider=OllamaProvider(FakeOllamaRuntime(reachable=False)),
        model_settings=settings,
        keep_alive="5m",
    )

    with pytest.raises(ModelRuntimeError, match="unavailable"):
        runtime.preload_active_model()


def test_unload_uses_keep_alive_zero(runtime_stack):
    settings, ollama, runtime = runtime_stack
    settings.update_chat_model("qwen3:8b", require_installed=True)
    ollama._running = ["qwen3:8b"]

    result = runtime.unload_active_model()

    assert result["status"] == "ok"
    assert result["model"] == "qwen3:8b"
    assert result["runtime"]["active_model"]["loaded"] is False
    assert settings.get_active_chat_model() == "qwen3:8b"
    assert ollama.generate_calls[-1]["keep_alive"] == 0


def test_readiness_summary_includes_loaded_detection(runtime_stack):
    _, ollama, runtime = runtime_stack
    ollama._running = []

    summary = runtime.readiness_summary()

    assert summary["active_chat_model"] == "llama3.1:8b"
    assert summary["keep_alive"] == "5m"
    assert summary["reachable"] is True
    assert summary["active_model_loaded"] == "not_loaded"
    assert summary["loaded_detection"] == "available"
    assert summary["cold_start_likely"] is True
    assert summary["running_models_count"] == 0


def test_readiness_ps_unsupported_stays_ok(runtime_stack):
    _, ollama, runtime = runtime_stack
    ollama._ps_detection = "unsupported"

    summary = runtime.readiness_summary()

    assert summary["status"] in {"ok", "degraded"}
    assert summary["loaded_detection"] == "unsupported"
    assert "cold_start_likely" not in summary or summary.get("cold_start_likely") is None
