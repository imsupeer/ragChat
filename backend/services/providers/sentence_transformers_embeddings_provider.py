from __future__ import annotations

from typing import Any, Callable

from services.embeddings_provider import EmbeddingsProviderUnavailableError
from services.sentence_transformers_runtime import (
    DEFAULT_SENTENCE_TRANSFORMERS_MODEL,
    inspect_sentence_transformers_setup,
)


class SentenceTransformersEmbeddingsProvider:
    provider_name = "sentence_transformers"

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_SENTENCE_TRANSFORMERS_MODEL,
        dimension: int = 384,
        device: str = "cpu",
        cache_dir: str = "",
        local_files_only: bool = True,
        model_loader: Callable[..., Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self._device = device
        self._cache_dir = cache_dir
        self._local_files_only = local_files_only
        self._model_loader = model_loader
        self._model: Any | None = None
        self._availability_cache: dict[str, Any] | None = None

    def inspect_setup(self, *, force_refresh: bool = False) -> dict[str, Any]:
        if self._availability_cache is not None and not force_refresh:
            return dict(self._availability_cache)

        report = inspect_sentence_transformers_setup(
            model_name=self.model_name,
            dimension=self.dimension,
            device=self._device,
            cache_dir=self._cache_dir,
            local_files_only=self._local_files_only,
            model_loader=self._model_loader,
        )
        self._availability_cache = dict(report)
        return dict(report)

    def provider_info(self) -> dict[str, Any]:
        report = self.inspect_setup()
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "dimension": self.dimension,
            "quality": "semantic",
            "zero_ollama_compatible": True,
            "local_files_only": self._local_files_only,
            "device": self._device,
            "status": report["status"],
            "message": report.get("message"),
            "setup_command": report.get("setup_command"),
            "check_command": report.get("check_command"),
        }

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        report = self.inspect_setup()
        status = str(report.get("status", "error"))
        if status != "ok":
            message = str(report.get("message") or "Sentence-transformers embeddings are unavailable.")
            raise EmbeddingsProviderUnavailableError(message, status=status)

        from services.sentence_transformers_runtime import import_sentence_transformer_class

        sentence_transformer_cls = import_sentence_transformer_class()
        if sentence_transformer_cls is None:
            raise EmbeddingsProviderUnavailableError(
                "sentence-transformers is not installed.",
                status="missing_dependency",
            )

        loader = self._model_loader or sentence_transformer_cls
        load_kwargs: dict[str, Any] = {
            "device": self._device,
            "local_files_only": self._local_files_only,
        }
        if self._cache_dir:
            load_kwargs["cache_folder"] = self._cache_dir
        self._model = loader(self.model_name, **load_kwargs)
        return self._model

    def _encode(self, text: str) -> list[float]:
        model = self._ensure_model()
        vector = model.encode(text or "", convert_to_numpy=True)
        values_raw = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        if values_raw and isinstance(values_raw[0], list):
            values_raw = values_raw[0]
        values = [float(value) for value in values_raw]
        if len(values) != self.dimension:
            raise EmbeddingsProviderUnavailableError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {len(values)}.",
                status="error",
            )
        return values

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        vectors = model.encode(list(texts), convert_to_numpy=True)
        encoded: list[list[float]] = []
        for vector in vectors:
            values = [float(value) for value in vector.tolist()]
            if len(values) != self.dimension:
                raise EmbeddingsProviderUnavailableError(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(values)}.",
                    status="error",
                )
            encoded.append(values)
        return encoded

    def embed_query(self, text: str) -> list[float]:
        return self._encode(text)
