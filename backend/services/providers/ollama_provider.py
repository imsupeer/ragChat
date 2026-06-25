from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from services.llm_provider import LLMProviderCapabilities
from services.ollama_service import OllamaService


class OllamaProvider:
    provider_name = "ollama"
    display_name = "Ollama"

    def __init__(self, ollama_service: OllamaService) -> None:
        self._ollama = ollama_service

    @property
    def ollama_service(self) -> OllamaService:
        return self._ollama

    @property
    def capabilities(self) -> LLMProviderCapabilities:
        return LLMProviderCapabilities(
            chat=True,
            streaming=True,
            list_installed_models=True,
            list_running_models=True,
            preload=True,
            unload=True,
            keep_alive=True,
            openai_compatible=False,
        )

    @property
    def model(self) -> str:
        return self._ollama.model

    @property
    def keep_alive(self) -> str | None:
        return self._ollama.keep_alive

    def with_model(self, model: str) -> OllamaProvider:
        return OllamaProvider(
            OllamaService(
                base_url=self._ollama.base_url,
                model=model,
                keep_alive=self._ollama.keep_alive,
                tags_timeout_seconds=self._ollama.tags_timeout_seconds,
                ps_timeout_seconds=self._ollama.ps_timeout_seconds,
                preload_timeout_seconds=self._ollama.preload_timeout_seconds,
            )
        )

    async def generate(self, prompt: str, model: str | None = None) -> str:
        return await self._ollama.generate(prompt, model)

    async def stream(
        self, prompt: str, model: str | None = None
    ) -> AsyncIterator[str]:
        async for chunk in self._ollama.stream(prompt, model):
            yield chunk

    def _prompt_from_messages(self, messages: list[dict[str, str]]) -> str:
        if not messages:
            return ""
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content") or "")
        return str(messages[-1].get("content") or "")

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        del options, keep_alive
        prompt = self._prompt_from_messages(messages)
        content = await self.generate(prompt, model=model)
        return {"message": {"role": "assistant", "content": content}}

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del options, keep_alive
        prompt = self._prompt_from_messages(messages)
        async for token in self.stream(prompt, model=model):
            yield {"message": {"content": token}}

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
        return {"status": "ok", "model": model}

    async def unload_model(self, *, model: str) -> dict[str, Any]:
        self.unload_model_sync(model)
        return {"status": "ok", "model": model}

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
        }

    def is_reachable(self, timeout: float | None = None) -> bool:
        return self._ollama.is_reachable(timeout=timeout)

    def list_installed_model_names(self, timeout: float | None = None) -> list[str]:
        return self._ollama.list_installed_models(timeout=timeout)

    def list_installed_model_details(
        self, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        return self._ollama.list_installed_model_details(timeout=timeout)

    def list_running_models_status(
        self, timeout: float | None = None
    ) -> dict[str, Any]:
        return self._ollama.list_running_models(timeout=timeout)

    def preload_model_sync(self, model: str) -> None:
        self._ollama.preload_model(model)

    def unload_model_sync(self, model: str) -> None:
        self._ollama.unload_model(model)

    def provider_info(self) -> dict[str, Any]:
        return {
            "name": self.provider_name,
            "display_name": self.display_name,
            "capabilities": self.capabilities.to_dict(),
        }
