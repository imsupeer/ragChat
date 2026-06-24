from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, AsyncGenerator

from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)


class OllamaService:
    def __init__(
        self,
        base_url: str,
        model: str,
        model_resolver: Callable[[], str] | None = None,
        keep_alive: str = "5m",
        tags_timeout_seconds: float = 2.0,
        ps_timeout_seconds: float = 2.0,
        preload_timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = model
        self._model_resolver = model_resolver
        self.keep_alive = keep_alive
        self.tags_timeout_seconds = tags_timeout_seconds
        self.ps_timeout_seconds = ps_timeout_seconds
        self.preload_timeout_seconds = preload_timeout_seconds
        self._clients: dict[str, ChatOllama] = {}

    @property
    def model(self) -> str:
        if self._model_resolver is not None:
            resolved = self._model_resolver().strip()
            if resolved:
                return resolved
        return self.default_model

    def _get_client(self, model_name: str | None = None) -> ChatOllama:
        active_model = model_name or self.model
        if active_model not in self._clients:
            self._clients[active_model] = ChatOllama(
                model=active_model,
                base_url=self.base_url,
                temperature=0,
                keep_alive=self.keep_alive,
            )
        return self._clients[active_model]

    def _fetch_tags_payload(self, timeout: float | None = None) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/tags"
        request = urllib.request.Request(url, method="GET")
        request_timeout = self.tags_timeout_seconds if timeout is None else timeout

        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                if response.status != 200:
                    return None
                payload = json.loads(response.read().decode("utf-8"))
                return payload if isinstance(payload, dict) else None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            logger.info("Ollama tags request unavailable: %s", exc)
            return None

    def is_reachable(self, timeout: float | None = None) -> bool:
        return self._fetch_tags_payload(timeout=timeout) is not None

    def list_installed_models(
        self,
        timeout: float | None = None,
    ) -> list[str]:
        payload = self._fetch_tags_payload(timeout=timeout)
        if payload is None:
            return []

        models = payload.get("models")
        if not isinstance(models, list):
            return []

        names: list[str] = []
        for item in models:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
        return names

    def list_installed_model_details(
        self,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._fetch_tags_payload(timeout=timeout)
        if payload is None:
            return []

        models = payload.get("models")
        if not isinstance(models, list):
            return []

        details: list[dict[str, Any]] = []
        for item in models:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            details.append(
                {
                    "name": str(item["name"]),
                    "family": item.get("details", {}).get("family")
                    if isinstance(item.get("details"), dict)
                    else item.get("family"),
                    "size": item.get("size"),
                    "modified_at": item.get("modified_at"),
                }
            )
        return details

    def _fetch_ps_payload(self, timeout: float | None = None) -> tuple[str, dict[str, Any] | None]:
        url = f"{self.base_url}/api/ps"
        request = urllib.request.Request(url, method="GET")
        request_timeout = self.ps_timeout_seconds if timeout is None else timeout

        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                if response.status != 200:
                    return "unavailable", None
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    return "unavailable", None
                return "available", payload
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return "unsupported", None
            logger.info("Ollama ps request failed: %s", exc)
            return "unavailable", None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            logger.info("Ollama ps request unavailable: %s", exc)
            return "unavailable", None

    def list_running_models(
        self,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not self.is_reachable(timeout=timeout):
            return {"detection": "unavailable", "models": []}

        detection, payload = self._fetch_ps_payload(timeout=timeout)
        if detection != "available" or payload is None:
            return {"detection": detection, "models": []}

        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            return {"detection": "available", "models": []}

        models: list[dict[str, Any]] = []
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("model") or "").strip()
            if not name:
                continue
            models.append(
                {
                    "name": name,
                    "expires_at": item.get("expires_at"),
                    "size": item.get("size"),
                    "size_vram": item.get("size_vram"),
                }
            )
        return {"detection": "available", "models": models}

    def _post_generate(
        self,
        *,
        model: str,
        prompt: str,
        keep_alive: str | int,
        timeout: float,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/api/generate"
        body = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": keep_alive,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError("Unexpected Ollama generate response.")
            return payload

    def preload_model(self, model: str) -> None:
        self._post_generate(
            model=model,
            prompt=" ",
            keep_alive=self.keep_alive,
            timeout=self.preload_timeout_seconds,
        )

    def unload_model(self, model: str) -> None:
        self._post_generate(
            model=model,
            prompt=" ",
            keep_alive=0,
            timeout=self.preload_timeout_seconds,
        )

    async def generate(self, prompt: str, model: str | None = None) -> str:
        client = self._get_client(model)
        response = await client.ainvoke(prompt)
        return response.content

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        client = self._get_client(model)
        async for chunk in client.astream(prompt):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content
