from __future__ import annotations



import json

import os

import threading

from datetime import datetime, timezone

from typing import Any, Callable, Literal



from services.model_catalog import load_model_catalog

from services.model_names import (

    build_install_command,

    build_run_command,

    catalog_name_set,

    is_catalog_known,

    model_matches_installed,

    resolve_installed_match,

)



InstalledStatus = Literal["installed", "not_installed", "unknown"]

SettingsSource = Literal["default", "user"]





def _utc_now_iso() -> str:

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()





class ModelSettingsService:

    def __init__(

        self,

        *,

        settings_path: str,

        default_chat_model: str,

        query_rewrite_model: str | None = None,

        use_chat_model_for_query_rewrite: bool = False,

        installed_models_provider: Callable[[], list[str]] | None = None,

        catalog_loader: Callable[[], list[dict[str, Any]]] | None = None,

    ) -> None:

        self.settings_path = settings_path

        self.default_chat_model = default_chat_model.strip()

        self.configured_query_rewrite_model = (

            query_rewrite_model.strip() if query_rewrite_model else None

        )

        self.use_chat_model_for_query_rewrite = use_chat_model_for_query_rewrite

        self._installed_models_provider = installed_models_provider

        self._catalog_loader = catalog_loader or load_model_catalog

        self._lock = threading.Lock()

        self._ensure_file()



    def _ensure_file(self) -> None:

        directory = os.path.dirname(self.settings_path)

        if directory:

            os.makedirs(directory, exist_ok=True)

        if not os.path.exists(self.settings_path):

            self._write_unlocked(self._default_payload())



    def _default_payload(self) -> dict[str, Any]:

        return {

            "chat_model": self.default_chat_model,

            "default_chat_model": self.default_chat_model,

            "query_rewrite_model": self.configured_query_rewrite_model,

            "use_chat_model_for_query_rewrite": self.use_chat_model_for_query_rewrite,

            "source": "default",

            "updated_at": _utc_now_iso(),

        }



    def _read_unlocked(self) -> dict[str, Any]:

        with open(self.settings_path, encoding="utf-8") as handle:

            payload = json.load(handle)

        if not isinstance(payload, dict):

            raise ValueError("Model settings file must contain a JSON object.")

        return payload



    def _write_unlocked(self, payload: dict[str, Any]) -> None:

        directory = os.path.dirname(self.settings_path) or "."

        os.makedirs(directory, exist_ok=True)

        temp_path = f"{self.settings_path}.tmp"

        with open(temp_path, "w", encoding="utf-8") as handle:

            json.dump(payload, handle, ensure_ascii=False, indent=2)

            handle.flush()

            os.fsync(handle.fileno())

        os.replace(temp_path, self.settings_path)



    def get_active_chat_model(self) -> str:

        with self._lock:

            payload = self._read_unlocked()

        chat_model = str(payload.get("chat_model") or self.default_chat_model).strip()

        return chat_model or self.default_chat_model



    def get_rewrite_model(self) -> str:

        if self.use_chat_model_for_query_rewrite:

            return self.get_active_chat_model()

        if self.configured_query_rewrite_model:

            return self.configured_query_rewrite_model

        return self.default_chat_model



    def query_rewrite_policy(self, chat_model: str | None = None) -> dict[str, Any]:

        active_chat_model = chat_model or self.get_active_chat_model()

        configured_model = self.configured_query_rewrite_model or self.default_chat_model

        if chat_model is None:

            effective_model = self.get_rewrite_model()

        elif self.use_chat_model_for_query_rewrite:

            effective_model = active_chat_model

        else:

            effective_model = self.configured_query_rewrite_model or self.default_chat_model

        return {

            "use_chat_model": self.use_chat_model_for_query_rewrite,

            "configured_model": configured_model,

            "effective_model": effective_model,

        }



    def list_catalog_ollama_names(self) -> set[str]:

        return catalog_name_set(self._catalog_loader())



    def validate_chat_model_name(self, chat_model: str, *, allow_custom: bool = False) -> str:

        normalized = chat_model.strip()

        if not normalized:

            raise ValueError("chat_model must not be empty.")



        allowed = self.list_catalog_ollama_names()

        if allowed and is_catalog_known(normalized, allowed):

            return normalized



        if allow_custom:

            return normalized



        if allowed:

            raise ValueError(

                "chat_model is not in the curated local catalog. "

                "Choose a catalog model from /models/catalog or an installed custom model."

            )

        return normalized



    def _installed_models(self) -> list[str] | None:

        if self._installed_models_provider is None:

            return None

        try:

            models = self._installed_models_provider()

            return models if models is not None else []

        except Exception:

            return None



    def _model_metadata(self, chat_model: str, installed: list[str] | None) -> dict[str, Any]:

        catalog_names = self.list_catalog_ollama_names()

        catalog_known = is_catalog_known(chat_model, catalog_names)



        if installed is None:

            return {

                "catalog_known": catalog_known,

                "installed": None,

                "installed_match": None,

                "match_type": "none",

                "install_command": build_install_command(chat_model),

                "run_command": build_run_command(chat_model),

            }



        match = resolve_installed_match(chat_model, installed, catalog_names)

        return {

            "catalog_known": match["catalog_known"],

            "installed": match["installed"],

            "installed_match": match["installed_match"],

            "match_type": match["match_type"],

            "install_command": build_install_command(chat_model),

            "run_command": build_run_command(chat_model),

        }



    def installed_status_for(self, chat_model: str) -> InstalledStatus:

        installed = self._installed_models()

        if installed is None:

            return "unknown"

        metadata = self._model_metadata(chat_model, installed)

        if metadata["installed"]:

            return "installed"

        return "not_installed"



    def get_state(self) -> dict[str, Any]:

        with self._lock:

            payload = self._read_unlocked()



        chat_model = str(payload.get("chat_model") or self.default_chat_model).strip()

        source = str(payload.get("source") or "default")

        if source not in {"default", "user"}:

            source = "default"



        installed = self._installed_models()

        metadata = self._model_metadata(chat_model, installed)



        return {

            "status": "ok",

            "chat_model": chat_model,

            "default_chat_model": self.default_chat_model,

            "query_rewrite_model": self.configured_query_rewrite_model,

            "use_chat_model_for_query_rewrite": self.use_chat_model_for_query_rewrite,

            "source": source,

            "updated_at": payload.get("updated_at"),

            "installed_status": self.installed_status_for(chat_model),

            "installed_models": installed or [],

            "catalog_known": metadata["catalog_known"],

            "installed": metadata["installed"],

            "installed_match": metadata["installed_match"],

            "match_type": metadata["match_type"],

            "install_command": metadata["install_command"],

            "run_command": metadata["run_command"],

            "query_rewrite": self.query_rewrite_policy(chat_model),

        }



    def update_chat_model(

        self,

        chat_model: str,

        *,

        require_installed: bool = True,

    ) -> dict[str, Any]:

        installed = self._installed_models()

        catalog_names = self.list_catalog_ollama_names()

        catalog_known = is_catalog_known(chat_model, catalog_names)

        custom_installed = False

        if installed is not None:

            match = resolve_installed_match(chat_model, installed, catalog_names)

            custom_installed = match["installed"] and match["match_type"] == "custom"



        validated = self.validate_chat_model_name(

            chat_model,

            allow_custom=custom_installed,

        )



        if require_installed:

            if installed is None:

                raise ModelSettingsConflictError(

                    "Ollama is unavailable, so installed models cannot be verified. "

                    "Retry when Ollama is running or set require_installed to false.",

                    install_command=build_install_command(validated),

                )

            match = resolve_installed_match(validated, installed, catalog_names)

            if not match["installed"]:

                raise ModelSettingsConflictError(

                    f"Model is not installed locally. Install it with "

                    f"`{build_install_command(validated)}` or choose another installed model.",

                    install_command=build_install_command(validated),

                )

            warning = None

        elif installed is None:

            warning = "Installed status is unknown because local Ollama is unavailable."

        else:

            match = resolve_installed_match(validated, installed, catalog_names)

            if not match["installed"]:

                warning = (

                    f"Model `{validated}` is not currently reported as installed by local Ollama."

                )

            else:

                warning = None



        payload = {

            "chat_model": validated,

            "default_chat_model": self.default_chat_model,

            "query_rewrite_model": self.configured_query_rewrite_model,

            "use_chat_model_for_query_rewrite": self.use_chat_model_for_query_rewrite,

            "source": "user",

            "updated_at": _utc_now_iso(),

        }



        with self._lock:

            self._write_unlocked(payload)



        state = self.get_state()

        if warning:

            state["warning"] = warning

        if not catalog_known and custom_installed:

            state["warning"] = (

                state.get("warning", "")

                + (" " if state.get("warning") else "")

                + f"Using custom installed model `{validated}` (not in curated catalog)."

            ).strip()

        return state



    def reset(self) -> dict[str, Any]:

        payload = self._default_payload()

        with self._lock:

            self._write_unlocked(payload)

        return self.get_state()





class ModelSettingsConflictError(Exception):

    def __init__(self, message: str, *, install_command: str | None = None) -> None:

        super().__init__(message)

        self.install_command = install_command


