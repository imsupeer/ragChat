from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

IMPLEMENTED_EMBEDDINGS_PROVIDERS = frozenset({"ollama", "local_hash", "sentence_transformers"})


class EmbeddingsProviderConfigError(ValueError):
    pass


class EmbeddingsProviderUnavailableError(RuntimeError):
    def __init__(self, message: str, *, status: str) -> None:
        super().__init__(message)
        self.status = status


@runtime_checkable
class EmbeddingsProvider(Protocol):
    provider_name: str
    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...

    def provider_info(self) -> dict[str, Any]:
        ...
