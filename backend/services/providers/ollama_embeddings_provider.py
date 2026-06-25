from __future__ import annotations

from typing import Any

from langchain_ollama import OllamaEmbeddings


class OllamaEmbeddingsProvider:
    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimension: int,
    ) -> None:
        self._base_url = base_url
        self.model_name = model
        self.dimension = dimension
        self._embeddings = OllamaEmbeddings(
            model=model,
            base_url=base_url,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)

    def get_langchain_embeddings(self) -> OllamaEmbeddings:
        return self._embeddings

    def provider_info(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "dimension": self.dimension,
            "quality": "semantic",
            "zero_ollama_compatible": False,
        }
