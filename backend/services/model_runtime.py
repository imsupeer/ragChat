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
from services.llm_provider import LLMProvider, LLMProviderUnsupportedOperationError
from services.embeddings_provider import EmbeddingsProvider
from services.embedding_collection_diagnostics import build_embedding_collection_diagnostics
from services.document_reindex import build_reindex_guidance
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.llama_cpp_runtime_files import get_local_runtime_status


class ModelRuntimeError(Exception):
    def __init__(self, message: str, *, install_command: str | None = None) -> None:
        super().__init__(message)
        self.install_command = install_command


class ModelRuntimeService:
    def __init__(
        self,
        *,
        llm_provider: LLMProvider,
        model_settings: ModelSettingsService,
        keep_alive: str,
        catalog_loader: Callable[[], list[dict[str, Any]]] | None = None,
        llama_cpp_manifest_path: str | None = None,
        llama_cpp_models_dir: str | None = None,
        llama_cpp_binary_dir: str | None = None,
        llama_cpp_server_bin: str | None = None,
        embeddings_provider: EmbeddingsProvider | None = None,
        chroma_service: ChromaService | None = None,
        document_registry: DocumentRegistry | None = None,
    ) -> None:
        self._provider = llm_provider
        self._model_settings = model_settings
        self._keep_alive = keep_alive
        self._catalog_loader = catalog_loader or load_model_catalog
        self._llama_cpp_manifest_path = llama_cpp_manifest_path
        self._llama_cpp_models_dir = llama_cpp_models_dir
        self._llama_cpp_binary_dir = llama_cpp_binary_dir
        self._llama_cpp_server_bin = llama_cpp_server_bin
        self._embeddings_provider = embeddings_provider
        self._chroma_service = chroma_service
        self._document_registry = document_registry

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

        capabilities = self._provider.capabilities
        keep_alive_value = self._keep_alive if capabilities.keep_alive else ""
        return {
            "keep_alive": keep_alive_value,
            "preload_supported": capabilities.preload,
            "unload_supported": capabilities.unload,
            "installed_models_count": installed_count,
            "running_models_count": running_count,
            "loaded_detection": detection,
            "cold_start_likely": cold_start_likely,
        }

    def get_runtime_status(self) -> dict[str, Any]:
        reachable = self._provider.is_reachable()
        installed_details: list[dict[str, Any]] = []
        installed_names: list[str] | None = None
        running_result: dict[str, Any] = {"detection": "unavailable", "models": []}

        if reachable:
            installed_details = self._provider.list_installed_model_details()
            installed_names = [item["name"] for item in installed_details]
            running_result = self._provider.list_running_models_status()

        active_model = self._active_model_state(installed_names, running_result)
        provider_name = self._provider.provider_name
        runtime_reachable = reachable
        runtime_status = "ok" if runtime_reachable else "unavailable"
        runtime_message = None
        if not runtime_reachable:
            if provider_name == "llama_cpp":
                runtime_message = (
                    "llama.cpp server is unreachable on the configured local URL."
                )
            else:
                runtime_message = "Ollama is unreachable on the configured local URL."

        if runtime_reachable and active_model["installed"] is False:
            runtime_status = "degraded"
            if provider_name == "llama_cpp":
                runtime_message = (
                    f"Active chat model `{active_model['name']}` is not reported by the "
                    "llama.cpp server."
                )
            else:
                runtime_message = (
                    f"Active chat model `{active_model['name']}` is not installed locally."
                )

        runtime_block = self._runtime_block(
            installed_count=len(installed_details),
            running_result=running_result,
            active_model=active_model,
        )

        return {
            "status": "ok" if reachable else "degraded",
            "provider": self._provider.provider_info(),
            "ollama": {
                "reachable": runtime_reachable,
                "status": runtime_status,
                "message": runtime_message,
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
            **self._local_runtime_block(),
            **self._embeddings_block(),
        }

    def _embeddings_block(self) -> dict[str, Any]:
        if self._embeddings_provider is None:
            return {}
        info = dict(self._embeddings_provider.provider_info())
        collection_status: dict[str, object] = {}
        if self._chroma_service is not None and hasattr(
            self._chroma_service, "get_collection_status"
        ):
            collection_status = self._chroma_service.get_collection_status()
        if self._chroma_service is not None:
            diagnostics = build_embedding_collection_diagnostics(
                self._chroma_service,
                provider=str(info["provider"]),
                model=str(info["model"]),
                dimension=int(info["dimension"]),
            )
            collection = diagnostics.get("collection", {})
            info["collection"] = {
                "strategy": collection_status.get("strategy"),
                "active_collection": collection_status.get("active_collection"),
                "status": diagnostics.get("status"),
                "reindex_recommended": diagnostics.get("reindex_recommended", False),
                "total_chunks": collection.get("total_chunks", 0),
                "matching_chunks": collection.get("matching_chunks", 0),
                "mismatched_provider_chunks": collection.get("mismatched_provider_chunks", 0),
                "mismatched_model_chunks": collection.get("mismatched_model_chunks", 0),
                "mismatched_dimension_chunks": collection.get("mismatched_dimension_chunks", 0),
                "legacy_chunks": collection.get("legacy_chunks", 0),
                "message": diagnostics.get("message"),
            }
            info["reindex"] = self._reindex_guidance_block(diagnostics)
        return {"embeddings": info}

    def _reindex_guidance_block(self, diagnostics: dict[str, Any]) -> dict[str, Any]:
        registered_count = 0
        if self._document_registry is not None:
            registered_count = len(self._document_registry.list_all())
        return build_reindex_guidance(
            collection_status=str(diagnostics.get("status") or "unknown"),
            reindex_recommended=bool(diagnostics.get("reindex_recommended")),
            registered_document_count=registered_count,
        )

    def get_embeddings_diagnostics(self) -> dict[str, Any]:
        if self._embeddings_provider is None:
            return {"status": "unknown", "message": "Embeddings provider unavailable."}
        info = dict(self._embeddings_provider.provider_info())
        if self._chroma_service is None:
            return {
                "status": "unknown",
                "message": "Chroma diagnostics unavailable.",
                "provider": info,
            }
        diagnostics = build_embedding_collection_diagnostics(
            self._chroma_service,
            provider=str(info["provider"]),
            model=str(info["model"]),
            dimension=int(info["dimension"]),
        )
        chroma_status = (
            self._chroma_service.get_collection_status()
            if hasattr(self._chroma_service, "get_collection_status")
            else {}
        )
        reindex = self._reindex_guidance_block(diagnostics)
        return {
            "provider": info,
            "collection": diagnostics,
            "chroma": chroma_status,
            "reindex": reindex,
            "reindex_guidance": reindex.get("message")
            or (
                "After changing EMBEDDINGS_PROVIDER, re-upload or reindex documents "
                "before evaluating retrieval quality."
            ),
        }

    def _local_runtime_block(self) -> dict[str, Any]:
        if self._provider.provider_name != "llama_cpp":
            return {}
        if not all(
            [
                self._llama_cpp_manifest_path,
                self._llama_cpp_models_dir,
                self._llama_cpp_binary_dir,
            ]
        ):
            return {}
        return {
            "local_runtime": get_local_runtime_status(
                manifest_path=self._llama_cpp_manifest_path,
                models_dir=self._llama_cpp_models_dir,
                binary_dir=self._llama_cpp_binary_dir,
                explicit_binary=self._llama_cpp_server_bin or None,
            )
        }

    def preload_active_model(self) -> dict[str, Any]:
        if not self._provider.is_reachable():
            provider_label = self._provider.display_name
            raise ModelRuntimeError(
                f"{provider_label} is unavailable. Start the local runtime before preloading a model."
            )

        active_model = self._model_settings.get_active_chat_model()
        installed = self._provider.list_installed_model_names()
        if installed and not any(
            model_matches_installed(active_model, name) for name in installed
        ):
            if self._provider.provider_name == "llama_cpp":
                raise ModelRuntimeError(
                    f"Model `{active_model['name']}` is not reported by the llama.cpp server."
                )
            raise ModelRuntimeError(
                f"Model is not installed locally. Install it with `ollama pull {active_model}`.",
                install_command=f"ollama pull {active_model}",
            )

        self._provider.preload_model_sync(active_model)
        refreshed = self.get_runtime_status()
        if self._provider.provider_name == "llama_cpp":
            message = (
                "llama.cpp server is reachable; model is managed by the server process."
            )
        else:
            message = "Model preload request completed."
        return {
            "status": "ok",
            "model": active_model,
            "message": message,
            "keep_alive": self._keep_alive if self._provider.capabilities.keep_alive else None,
            "runtime": refreshed,
        }

    def unload_active_model(self) -> dict[str, Any]:
        if not self._provider.capabilities.unload:
            raise ModelRuntimeError(
                "Unload is not supported for the llama.cpp provider. "
                "The model is managed by the llama-server process."
            )

        if not self._provider.is_reachable():
            provider_label = self._provider.display_name
            raise ModelRuntimeError(
                f"{provider_label} is unavailable. Start the local runtime before unloading a model."
            )

        active_model = self._model_settings.get_active_chat_model()
        try:
            self._provider.unload_model_sync(active_model)
        except LLMProviderUnsupportedOperationError as exc:
            raise ModelRuntimeError(str(exc)) from exc
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
            "provider": status["provider"]["name"],
            "active_chat_model": active["name"],
            "active_model_installed": installed_label,
            "active_model_loaded": loaded_label,
            "loaded_detection": runtime.get("loaded_detection", "unavailable"),
            "keep_alive": self._keep_alive if self._provider.capabilities.keep_alive else "",
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
