from collections.abc import AsyncIterator
from typing import Any

from services.llm_provider import LLMProviderCapabilities
from services.providers.ollama_provider import OllamaProvider


class FakeLLMProvider:
    def __init__(self, tokens=None, fail: bool = False) -> None:
        self.model = "test-model"
        self.keep_alive = "5m"
        self.provider_name = "ollama"
        self.display_name = "Ollama"
        self.tokens = tokens or ["Hello", " world"]
        self.fail = fail

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
        )

    async def generate(self, prompt: str, model: str | None = None) -> str:
        del prompt, model
        if self.fail:
            raise RuntimeError("LLM unavailable")
        return "".join(self.tokens)

    async def stream(self, prompt: str, model: str | None = None) -> AsyncIterator[str]:
        del prompt, model
        if self.fail:
            raise RuntimeError("LLM unavailable")
        for token in self.tokens:
            yield token

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        del model, messages, options, keep_alive
        content = await self.generate("")
        return {"message": {"role": "assistant", "content": content}}

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del model, messages, options, keep_alive
        async for token in self.stream(""):
            yield {"message": {"content": token}}

    async def list_installed_models(self) -> list[dict[str, Any]]:
        return [{"name": self.model}]

    async def list_running_models(self) -> list[dict[str, Any]]:
        return []

    async def preload_model(
        self,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        del keep_alive
        return {"status": "ok", "model": model}

    async def unload_model(self, *, model: str) -> dict[str, Any]:
        return {"status": "ok", "model": model}

    async def runtime_status(self) -> dict[str, Any]:
        return {
            "reachable": not self.fail,
            "provider": self.provider_name,
            "active_model": self.model,
            "installed_models_count": 1,
            "running_models_count": 0,
        }

    def is_reachable(self, timeout: float | None = None) -> bool:
        del timeout
        return not self.fail

    def list_installed_model_names(self, timeout: float | None = None) -> list[str]:
        del timeout
        return [self.model]

    def list_installed_model_details(
        self, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        del timeout
        return [{"name": self.model, "family": "test", "size": 1, "modified_at": "now"}]

    def list_running_models_status(
        self, timeout: float | None = None
    ) -> dict[str, Any]:
        del timeout
        return {"detection": "available", "models": []}

    def preload_model_sync(self, model: str) -> None:
        del model

    def unload_model_sync(self, model: str) -> None:
        del model

    def provider_info(self) -> dict[str, Any]:
        return {
            "name": self.provider_name,
            "display_name": self.display_name,
            "capabilities": self.capabilities.to_dict(),
        }


FakeOllamaService = FakeLLMProvider


def wrap_ollama_runtime(runtime) -> OllamaProvider:
    return OllamaProvider(runtime)
