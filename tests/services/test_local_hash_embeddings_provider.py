import math

import pytest

from services.providers.local_hash_embeddings_provider import (
    LOCAL_HASH_MODEL_NAME,
    LocalHashEmbeddingsProvider,
)


@pytest.fixture
def provider() -> LocalHashEmbeddingsProvider:
    return LocalHashEmbeddingsProvider(dimension=384, normalize=True)


def test_local_hash_is_deterministic(provider: LocalHashEmbeddingsProvider):
    text = "registry json queue chroma"
    first = provider.embed_query(text)
    second = provider.embed_query(text)
    assert first == second


def test_local_hash_dimension(provider: LocalHashEmbeddingsProvider):
    vector = provider.embed_query("hello world")
    assert len(vector) == 384


def test_local_hash_normalization(provider: LocalHashEmbeddingsProvider):
    vector = provider.embed_query("hello world retrieval")
    norm = math.sqrt(sum(value * value for value in vector))
    assert norm == pytest.approx(1.0, rel=1e-6)


def test_local_hash_empty_text_returns_zero_vector(provider: LocalHashEmbeddingsProvider):
    vector = provider.embed_query("")
    assert vector == [0.0] * 384


def test_local_hash_non_empty_text_is_non_zero(provider: LocalHashEmbeddingsProvider):
    vector = provider.embed_query("document chunk")
    assert any(value != 0.0 for value in vector)


def test_local_hash_similar_text_shares_signal(provider: LocalHashEmbeddingsProvider):
    left = provider.embed_query("retrieval dense hybrid")
    right = provider.embed_query("hybrid dense retrieval")
    overlap = sum(1 for a, b in zip(left, right) if a != 0.0 and b != 0.0)
    assert overlap > 0


def test_local_hash_provider_info(provider: LocalHashEmbeddingsProvider):
    info = provider.provider_info()
    assert info["provider"] == "local_hash"
    assert info["model"] == LOCAL_HASH_MODEL_NAME
    assert info["dimension"] == 384
    assert info["quality"] == "demo"
    assert info["zero_ollama_compatible"] is True


def test_local_hash_batch_embed_documents(provider: LocalHashEmbeddingsProvider):
    vectors = provider.embed_documents(["one", "two"])
    assert len(vectors) == 2
    assert all(len(vector) == 384 for vector in vectors)
