from __future__ import annotations

import hashlib
import math
import re
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
LOCAL_HASH_MODEL_NAME = "local-hash-v1"


class LocalHashEmbeddingsProvider:
    provider_name = "local_hash"
    model_name = LOCAL_HASH_MODEL_NAME

    def __init__(self, *, dimension: int = 384, normalize: bool = True) -> None:
        if dimension <= 0:
            raise ValueError("local_hash embeddings dimension must be positive.")
        self.dimension = dimension
        self._normalize = normalize

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = TOKEN_RE.findall((text or "").lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(0, len(digest), 4):
                bucket = int.from_bytes(digest[index : index + 4], "big") % self.dimension
                sign = 1.0 if digest[index] % 2 == 0 else -1.0
                vector[bucket] += sign

        if self._normalize:
            norm = math.sqrt(sum(value * value for value in vector))
            if norm > 0:
                vector = [value / norm for value in vector]
        return vector

    def provider_info(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "dimension": self.dimension,
            "quality": "demo",
            "zero_ollama_compatible": True,
        }
