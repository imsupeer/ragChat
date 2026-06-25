import pytest

from core.config import Settings
from core.dependencies import clear_dependency_caches, get_embeddings_provider
from services.embeddings_provider import EmbeddingsProviderConfigError
from services.embeddings_provider_resolver import resolve_embeddings_provider
from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider
from services.providers.ollama_embeddings_provider import OllamaEmbeddingsProvider
from services.providers.sentence_transformers_embeddings_provider import (
    SentenceTransformersEmbeddingsProvider,
)


def test_default_resolver_returns_ollama_provider():
    provider = resolve_embeddings_provider(Settings())
    assert isinstance(provider, OllamaEmbeddingsProvider)
    assert provider.provider_name == "ollama"


def test_local_hash_resolver_returns_local_hash_provider():
    provider = resolve_embeddings_provider(
        Settings(embeddings_provider="local_hash", local_hash_embeddings_dimension=256)
    )
    assert isinstance(provider, LocalHashEmbeddingsProvider)
    assert provider.dimension == 256


def test_sentence_transformers_resolver_returns_provider():
    provider = resolve_embeddings_provider(
        Settings(embeddings_provider="sentence_transformers")
    )
    assert isinstance(provider, SentenceTransformersEmbeddingsProvider)


def test_invalid_embeddings_provider_raises():
    with pytest.raises(EmbeddingsProviderConfigError):
        resolve_embeddings_provider(Settings.model_construct(embeddings_provider="openai"))


def test_dependency_cache_reset_clears_embeddings_provider(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "local_hash")
    clear_dependency_caches()
    first = get_embeddings_provider()
    clear_dependency_caches()
    second = get_embeddings_provider()
    assert isinstance(first, LocalHashEmbeddingsProvider)
    assert isinstance(second, LocalHashEmbeddingsProvider)
