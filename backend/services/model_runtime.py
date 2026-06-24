from __future__ import annotations

from typing import Any, Callable

from services.model_catalog import load_model_catalog
from services.model_names import (
    build_install_command,
    catalog_name_set,
    is_catalog_known,
    model_matches_installed,
    resolve_installed_match,
)
from services.model_settings import ModelSettingsService
from services.ollama_service import OllamaService


class ModelRuntimeError(Exception):
    def __init__(self, message: str, *, install_command: str | None = None) -> None:
        super().__init__(message)
        self.install_command = install_command


class ModelRuntimeService:
    def __init__(
        self,
        *,
        ollama_service: OllamaService,
        model_settings: ModelSettingsService,
        keep_alive: str,
        catalog_loader: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._ollama = ollama_service
        self._model_settings = model_settings
        self._keep_alive = keep_alive
        self._catalog_loader = catalog_loader or load_model_catalog

    def _catalog_entry_for(self, active_name: str) -> dict[str, Any] | None:
        for entry in self._catalog_loader():
            ollama_name = str(entry.get("ollama_name", "")).strip()
            if is_catalog_known(active_name, {ollama_name}):
                return entry
        return None

    def _loaded_state(
        self,
        active_name: str,
        running_result: dict[str, Any],
        catalog_names: set[str],
    ) -> dict[str, Any]:
        detection = str(running_result.get("detection", "unavailable"))
        running_models = running_result.get("models") or []
        running_names = [str(item["name"]) for item in running_models if item.get("name")]

        if detection != "available":
            return {
                "loaded": None,
                "loaded_match": None,
                "loaded_match_type": "unknown",
            }

        match = resolve_installed_match(active_name, running_names, catalog_names)
        if match["installed"]:
            return {
                "loaded": True,
                "loaded_match": match["installed_match"],
                "loaded_match_type": match["match_type"],
            }

        return {
            "loaded": False,
            "loaded_match": None,
            "loaded_match_type": "none",
        }

    def _active_model_state(
        self,
        installed_names: list[str] | None,
        running_result: dict[str, Any],
    ) -> dict[str, Any]:
        settings = self._model_settings.get_state()
        active_name = str(settings["chat_model"])
        catalog_names = catalog_name_set(self._catalog_loader())
        catalog_entry = self._catalog_entry_for(active_name)

        install_match = (
            resolve_installed_match(active_name, installed_names or [], catalog_names)
            if installed_names is not None
            else {
                "installed": None,
                "installed_match": None,
                "match_type": "none",
                "catalog_known": is_catalog_known(active_name, catalog_names),
            }
        )

        loaded_state = self._loaded_state(active_name, running_result, catalog_names)

        return {
            "name": active_name,
            "installed": install_match["installed"],
            "installed_match": install_match.get("installed_match"),
            "match_type": install_match.get("match_type", "none"),
            "loaded": loaded_state["loaded"],
            "loaded_match": loaded_state["loaded_match"],
            "loaded_match_type": loaded_state["loaded_match_type"],
            "source": settings.get("source", "default"),
            "catalog_known": install_match.get(
                "catalog_known",
                is_catalog_known(active_name, catalog_names),
            ),
            "family": catalog_entry.get("family") if catalog_entry else None,
        }

    def _runtime_block(
        self,
        *,
        installed_count: int,
        running_result: dict[str, Any],
        active_model: dict[str, Any],
    ) -> dict[str, Any]:
        detection = str(running_result.get("detection", "unavailable"))
        running_models = running_result.get("models") or []
        running_count = len(running_models)

        cold_start_likely: bool | None = None
        if detection == "available" and active_model.get("installed") is True:
            cold_start_likely = active_model.get("loaded") is False

        return {
            "keep_alive": self._keep_alive,
            "preload_supported": True,
            "unload_supported": True,
            "installed_models_count": installed_count,
            "running_models_count": running_count,
            "loaded_detection": detection,
            "cold_start_likely": cold_start_likely,
        }

    def get_runtime_status(self) -> dict[str, Any]:
        reachable = self._ollama.is_reachable()
        installed_details: list[dict[str, Any]] = []
        installed_names: list[str] | None = None
        running_result: dict[str, Any] = {"detection": "unavailable", "models": []}

        if reachable:
            installed_details = self._ollama.list_installed_model_details()
            installed_names = [item["name"] for item in installed_details]
            running_result = self._ollama.list_running_models()

        active_model = self._active_model_state(installed_names, running_result)
        ollama_status = "ok" if reachable else "unavailable"
        ollama_message = None if reachable else "Ollama is unreachable on the configured local URL."

        if reachable and active_model["installed"] is False:
            ollama_status = "degraded"
            ollama_message = (
                f"Active chat model `{active_model['name']}` is not installed locally."
            )

        runtime_block = self._runtime_block(
            installed_count=len(installed_details),
            running_result=running_result,
            active_model=active_model,
        )

        return {
            "status": "ok" if reachable else "degraded",
            "ollama": {
                "reachable": reachable,
                "status": ollama_status,
                "message": ollama_message,
            },
            "active_model": active_model,
            "installed_models": installed_details,
            "installed_models_count": len(installed_details),
            "running_models": running_result.get("models") or [],
            "settings": {
                "chat_model": active_model["name"],
                "default_chat_model": self._model_settings.default_chat_model,
                "source": active_model["source"],
                "query_rewrite": self._model_settings.query_rewrite_policy(active_model["name"]),
            },
            "runtime": runtime_block,
        }

    def preload_active_model(self) -> dict[str, Any]:
        if not self._ollama.is_reachable():
            raise ModelRuntimeError("Ollama is unavailable. Start Ollama before preloading a model.")

        active_model = self._model_settings.get_active_chat_model()
        installed = self._ollama.list_installed_models()
        if not any(model_matches_installed(active_model, name) for name in installed):
            raise ModelRuntimeError(
                f"Model is not installed locally. Install it with `ollama pull {active_model}`.",
                install_command=f"ollama pull {active_model}",
            )

        self._ollama.preload_model(active_model)
        refreshed = self.get_runtime_status()
        return {
            "status": "ok",
            "model": active_model,
            "message": "Model preload request completed.",
            "keep_alive": self._keep_alive,
            "runtime": refreshed,
        }

    def unload_active_model(self) -> dict[str, Any]:
        if not self._ollama.is_reachable():
            raise ModelRuntimeError("Ollama is unavailable. Start Ollama before unloading a model.")

        active_model = self._model_settings.get_active_chat_model()
        self._ollama.unload_model(active_model)
        refreshed = self.get_runtime_status()
        return {
            "status": "ok",
            "model": active_model,
            "message": (
                "Unload request completed. The selected chat model remains unchanged."
            ),
            "runtime": refreshed,
        }

    def readiness_summary(self) -> dict[str, Any]:
        status = self.get_runtime_status()
        active = status["active_model"]
        runtime = status["runtime"]
        installed_value = active.get("installed")
        if installed_value is True:
            installed_label = "installed"
        elif installed_value is False:
            installed_label = "not_installed"
        else:
            installed_label = "unknown"

        loaded_value = active.get("loaded")
        if loaded_value is True:
            loaded_label = "loaded"
        elif loaded_value is False:
            loaded_label = "not_loaded"
        else:
            loaded_label = "unknown"

        check: dict[str, Any] = {
            "status": status["ollama"]["status"],
            "reachable": status["ollama"]["reachable"],
            "active_chat_model": active["name"],
            "active_model_installed": installed_label,
            "active_model_loaded": loaded_label,
            "loaded_detection": runtime.get("loaded_detection", "unavailable"),
            "keep_alive": self._keep_alive,
            "installed_models_count": status["installed_models_count"],
            "running_models_count": runtime.get("running_models_count", 0),
        }
        cold_start = runtime.get("cold_start_likely")
        if cold_start is not None:
            check["cold_start_likely"] = cold_start

        if check["status"] == "unavailable":
            check["status"] = "degraded"
        if status["ollama"]["message"]:
            check["message"] = status["ollama"]["message"]
        return check
