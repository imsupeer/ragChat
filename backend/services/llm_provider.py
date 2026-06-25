from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from typing import Any, Protocol, runtime_checkable


IMPLEMENTED_LLM_PROVIDERS = frozenset({"ollama", "llama_cpp"})

PLANNED_LLM_PROVIDERS = frozenset(
    {
        "embedded_llamacpp",
        "openai_compatible",
        "lmstudio",
        "localai",
    }
)


class LLMProviderConfigError(ValueError):
    pass


class LLMProviderUnsupportedOperationError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMProviderCapabilities:
    chat: bool = True
    streaming: bool = True
    list_installed_models: bool = True
    list_running_models: bool = False
    preload: bool = False
    unload: bool = False
    keep_alive: bool = False
    openai_compatible: bool = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@runtime_checkable
class LLMProvider(Protocol):
    provider_name: str
    display_name: str

    @property
    def capabilities(self) -> LLMProviderCapabilities: ...

    @property
    def model(self) -> str: ...

    @property
    def keep_alive(self) -> str | None: ...

    async def generate(self, prompt: str, model: str | None = None) -> str: ...

    async def stream(
        self, prompt: str, model: str | None = None
    ) -> AsyncIterator[str]: ...

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]: ...

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...

    async def list_installed_models(self) -> list[dict[str, Any]]: ...

    async def list_running_models(self) -> list[dict[str, Any]]: ...

    async def preload_model(
        self,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> dict[str, Any]: ...

    async def unload_model(self, *, model: str) -> dict[str, Any]: ...

    async def runtime_status(self) -> dict[str, Any]: ...

    def is_reachable(self, timeout: float | None = None) -> bool: ...

    def list_installed_model_names(self, timeout: float | None = None) -> list[str]: ...

    def list_installed_model_details(
        self, timeout: float | None = None
    ) -> list[dict[str, Any]]: ...

    def list_running_models_status(
        self, timeout: float | None = None
    ) -> dict[str, Any]: ...

    def preload_model_sync(self, model: str) -> None: ...

    def unload_model_sync(self, model: str) -> None: ...

    def provider_info(self) -> dict[str, Any]: ...
