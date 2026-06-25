from __future__ import annotations

from services.embeddings_provider import EmbeddingsProvider


class LangChainEmbeddingsAdapter:
    def __init__(self, provider: EmbeddingsProvider) -> None:
        self._provider = provider

    @property
    def embeddings_provider(self) -> EmbeddingsProvider:
        return self._provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._provider.embed_query(text)
