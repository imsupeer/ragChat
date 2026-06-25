from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from services.llm_provider import LLMProviderCapabilities, LLMProviderUnsupportedOperationError

logger = logging.getLogger(__name__)


class LlamaCppProviderError(RuntimeError):
    pass


class LlamaCppServerUnavailableError(LlamaCppProviderError):
    pass


class LlamaCppProvider:
    provider_name = "llama_cpp"
    display_name = "llama.cpp"

    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        model_path: str = "",
        model_resolver: Callable[[], str] | None = None,
        timeout_seconds: float = 60.0,
        stream_timeout_seconds: float = 120.0,
        runtime_timeout_seconds: float = 2.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = chat_model.strip()
        self._model_path = model_path.strip()
        self._model_resolver = model_resolver
        self._timeout_seconds = timeout_seconds
        self._stream_timeout_seconds = stream_timeout_seconds
        self._runtime_timeout_seconds = runtime_timeout_seconds

    @property
    def capabilities(self) -> LLMProviderCapabilities:
        return LLMProviderCapabilities(
            chat=True,
            streaming=True,
            list_installed_models=True,
            list_running_models=True,
            preload=True,
            unload=False,
            keep_alive=False,
            openai_compatible=True,
        )

    @property
    def model(self) -> str:
        if self._model_resolver is not None:
            resolved = self._model_resolver().strip()
            if resolved:
                return resolved
        return self._default_model

    @property
    def keep_alive(self) -> str | None:
        return None

    def with_model(self, model: str) -> LlamaCppProvider:
        return LlamaCppProvider(
            base_url=self._base_url,
            chat_model=model,
            model_path=self._model_path,
            timeout_seconds=self._timeout_seconds,
            stream_timeout_seconds=self._stream_timeout_seconds,
            runtime_timeout_seconds=self._runtime_timeout_seconds,
        )

    def _runtime_timeout(self, timeout: float | None) -> float:
        return self._runtime_timeout_seconds if timeout is None else timeout

    def _chat_timeout(self, timeout: float | None) -> float:
        return self._timeout_seconds if timeout is None else timeout

    def _stream_timeout(self, timeout: float | None) -> float:
        return self._stream_timeout_seconds if timeout is None else timeout

    def _request_url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _check_reachable_sync(self, timeout: float | None = None) -> bool:
        request_timeout = self._runtime_timeout(timeout)
        with httpx.Client(timeout=request_timeout) as client:
            for path in ("/health", "/v1/models", ""):
                try:
                    response = client.get(self._request_url(path))
                    if response.status_code < 500:
                        return True
                except (httpx.HTTPError, OSError) as exc:
                    logger.info("llama.cpp reachability check failed for %s: %s", path, exc)
        return False

    def is_reachable(self, timeout: float | None = None) -> bool:
        return self._check_reachable_sync(timeout=timeout)

    def _fetch_models_payload_sync(
        self, timeout: float | None = None
    ) -> dict[str, Any] | None:
        if not self.is_reachable(timeout=timeout):
            return None

        request_timeout = self._runtime_timeout(timeout)
        with httpx.Client(timeout=request_timeout) as client:
            try:
                response = client.get(self._request_url("/v1/models"))
                if response.status_code != 200:
                    return None
                payload = response.json()
                return payload if isinstance(payload, dict) else None
            except (httpx.HTTPError, OSError, json.JSONDecodeError) as exc:
                logger.info("llama.cpp models request unavailable: %s", exc)
                return None

    def _models_from_payload(self, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        if payload is None:
            return []

        raw_models = payload.get("data")
        if not isinstance(raw_models, list):
            return []

        models: list[dict[str, Any]] = []
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or item.get("name") or "").strip()
            if not model_id:
                continue
            models.append(
                {
                    "name": model_id,
                    "family": item.get("owned_by"),
                    "size": item.get("size"),
                    "modified_at": item.get("created"),
                    "status": "server",
                }
            )
        return models

    def _configured_model_entry(self) -> dict[str, Any]:
        return {
            "name": self.model,
            "family": None,
            "size": None,
            "modified_at": None,
            "status": "configured",
        }

    def list_installed_model_details(
        self, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        models = self._models_from_payload(self._fetch_models_payload_sync(timeout=timeout))
        if models:
            return models
        if self.is_reachable(timeout=timeout):
            return [self._configured_model_entry()]
        return []

    def list_installed_model_names(self, timeout: float | None = None) -> list[str]:
        return [item["name"] for item in self.list_installed_model_details(timeout=timeout)]

    def list_running_models_status(
        self, timeout: float | None = None
    ) -> dict[str, Any]:
        if not self.is_reachable(timeout=timeout):
            return {
                "detection": "unavailable",
                "detection_method": "server_reachable",
                "models": [],
            }

        models_payload = self._fetch_models_payload_sync(timeout=timeout)
        server_models = self._models_from_payload(models_payload)
        active_name = self.model

        if server_models:
            names = [item["name"] for item in server_models]
            running_name = active_name if active_name in names else names[0]
            return {
                "detection": "available",
                "detection_method": "single_model_server",
                "models": [{"name": running_name, "status": "loaded"}],
            }

        return {
            "detection": "available",
            "detection_method": "provider_runtime",
            "models": [{"name": active_name, "status": "loaded"}],
        }

    def preload_model_sync(self, model: str) -> None:
        del model
        if not self.is_reachable():
            raise LlamaCppServerUnavailableError(
                "llama.cpp server is unavailable. Start llama-server before preloading."
            )

    def unload_model_sync(self, model: str) -> None:
        del model
        raise LLMProviderUnsupportedOperationError(
            "Unload is not supported for the llama.cpp provider. "
            "The model is managed by the llama-server process."
        )

    def _build_chat_payload(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None,
        stream: bool,
    ) -> dict[str, Any]:
        temperature = 0.2
        if options and options.get("temperature") is not None:
            temperature = options["temperature"]

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
        }
        if options:
            for key in ("top_p", "max_tokens", "stop"):
                if key in options:
                    payload[key] = options[key]
        return payload

    def _extract_chat_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlamaCppProviderError("llama.cpp chat response did not include choices.")

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content

        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if isinstance(text, str):
            return text

        raise LlamaCppProviderError("llama.cpp chat response did not include message content.")

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        del keep_alive
        payload = self._build_chat_payload(
            model=model,
            messages=messages,
            options=options,
            stream=False,
        )

        try:
            async with httpx.AsyncClient(timeout=self._chat_timeout(None)) as client:
                response = await client.post(
                    self._request_url("/v1/chat/completions"),
                    json=payload,
                )
        except (httpx.HTTPError, OSError) as exc:
            raise LlamaCppServerUnavailableError(
                "llama.cpp server is unavailable."
            ) from exc

        if response.status_code != 200:
            raise LlamaCppProviderError(
                f"llama.cpp chat request failed with status {response.status_code}."
            )

        body = response.json()
        if not isinstance(body, dict):
            raise LlamaCppProviderError("Unexpected llama.cpp chat response.")

        content = self._extract_chat_content(body)
        return {"message": {"role": "assistant", "content": content}}

    def _parse_stream_line(self, line: str) -> str | None:
        stripped = line.strip()
        if not stripped.startswith("data:"):
            return None

        data = stripped[5:].strip()
        if data == "[DONE]":
            return None

        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            logger.info("Skipping malformed llama.cpp stream chunk.")
            return ""

        if not isinstance(chunk, dict):
            return ""

        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""

        choice = choices[0]
        if not isinstance(choice, dict):
            return ""

        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                return content

        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content

        text = choice.get("text")
        if isinstance(text, str):
            return text

        return ""

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del keep_alive
        if not self.capabilities.streaming:
            raise LLMProviderUnsupportedOperationError(
                "Streaming is not supported by the llama.cpp provider."
            )

        payload = self._build_chat_payload(
            model=model,
            messages=messages,
            options=options,
            stream=True,
        )

        try:
            async with httpx.AsyncClient(timeout=self._stream_timeout(None)) as client:
                async with client.stream(
                    "POST",
                    self._request_url("/v1/chat/completions"),
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        raise LlamaCppProviderError(
                            f"llama.cpp streaming request failed with status {response.status_code}."
                        )

                    async for line in response.aiter_lines():
                        token = self._parse_stream_line(line)
                        if token is None:
                            break
                        if token:
                            yield {"message": {"content": token}}
        except LlamaCppProviderError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise LlamaCppServerUnavailableError(
                "llama.cpp server is unavailable."
            ) from exc

    async def generate(self, prompt: str, model: str | None = None) -> str:
        active_model = model or self.model
        result = await self.chat(
            model=active_model,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(result["message"]["content"])

    async def stream(
        self, prompt: str, model: str | None = None
    ) -> AsyncIterator[str]:
        active_model = model or self.model
        async for event in self.stream_chat(
            model=active_model,
            messages=[{"role": "user", "content": prompt}],
        ):
            yield str(event["message"]["content"])

    async def list_installed_models(self) -> list[dict[str, Any]]:
        return self.list_installed_model_details()

    async def list_running_models(self) -> list[dict[str, Any]]:
        result = self.list_running_models_status()
        models = result.get("models")
        return models if isinstance(models, list) else []

    async def preload_model(
        self,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        del keep_alive
        self.preload_model_sync(model)
        return {
            "status": "ok",
            "model": model,
            "message": (
                "llama.cpp server is reachable; model is managed by the server process."
            ),
        }

    async def unload_model(self, *, model: str) -> dict[str, Any]:
        del model
        raise LLMProviderUnsupportedOperationError(
            "Unload is not supported for the llama.cpp provider."
        )

    async def runtime_status(self) -> dict[str, Any]:
        reachable = self.is_reachable()
        installed = self.list_installed_model_details() if reachable else []
        running = await self.list_running_models() if reachable else []
        return {
            "reachable": reachable,
            "provider": self.provider_name,
            "active_model": self.model,
            "installed_models_count": len(installed),
            "running_models_count": len(running),
            "detection_method": (
                self.list_running_models_status().get("detection_method")
                if reachable
                else "server_reachable"
            ),
        }

    def provider_info(self) -> dict[str, Any]:
        return {
            "name": self.provider_name,
            "display_name": self.display_name,
            "capabilities": self.capabilities.to_dict(),
        }
