from __future__ import annotations

from core.config import Settings
from services.embeddings_provider import (
    IMPLEMENTED_EMBEDDINGS_PROVIDERS,
    EmbeddingsProvider,
    EmbeddingsProviderConfigError,
)
from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider
from services.providers.ollama_embeddings_provider import OllamaEmbeddingsProvider
from services.providers.sentence_transformers_embeddings_provider import (
    SentenceTransformersEmbeddingsProvider,
)


def resolve_embeddings_provider(settings: Settings) -> EmbeddingsProvider:
    provider_key = (settings.embeddings_provider or "ollama").strip().lower()

    if provider_key not in IMPLEMENTED_EMBEDDINGS_PROVIDERS:
        allowed = ", ".join(sorted(IMPLEMENTED_EMBEDDINGS_PROVIDERS))
        raise EmbeddingsProviderConfigError(
            f"Invalid EMBEDDINGS_PROVIDER value: '{provider_key}'. "
            f"Implemented providers: {allowed}"
        )

    if provider_key == "ollama":
        return OllamaEmbeddingsProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embed_model,
            dimension=settings.ollama_embed_dimension,
        )

    if provider_key == "local_hash":
        return LocalHashEmbeddingsProvider(
            dimension=settings.local_hash_embeddings_dimension,
            normalize=settings.local_hash_embeddings_normalize,
        )

    if provider_key == "sentence_transformers":
        return SentenceTransformersEmbeddingsProvider(
            model_name=settings.sentence_transformers_model,
            dimension=settings.sentence_transformers_dimension,
            device=settings.sentence_transformers_device,
            cache_dir=settings.sentence_transformers_cache_dir,
            local_files_only=settings.sentence_transformers_local_files_only,
        )

    raise EmbeddingsProviderConfigError(f"Unsupported embeddings provider: {provider_key}")
