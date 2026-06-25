from unittest.mock import MagicMock

import numpy as np
import pytest

from services.embeddings_provider import EmbeddingsProviderUnavailableError
from services.providers.sentence_transformers_embeddings_provider import (
    SentenceTransformersEmbeddingsProvider,
)


class FakeSentenceTransformer:
    def __init__(self, model_name: str, **kwargs) -> None:
        self.model_name = model_name
        self.kwargs = kwargs

    def encode(self, texts, convert_to_numpy=True):
        if isinstance(texts, str):
            return np.array([0.1, 0.2, 0.3] + [0.0] * 381, dtype=float)
        return np.array([[0.1, 0.2, 0.3] + [0.0] * 381] * len(texts), dtype=float)


def test_provider_info_reports_ok_with_fake_model(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: FakeSentenceTransformer,
    )
    provider = SentenceTransformersEmbeddingsProvider(
        model_loader=FakeSentenceTransformer,
    )
    info = provider.provider_info()
    assert info["provider"] == "sentence_transformers"
    assert info["model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert info["dimension"] == 384
    assert info["quality"] == "semantic"
    assert info["zero_ollama_compatible"] is True
    assert info["local_files_only"] is True
    assert info["status"] == "ok"


def test_missing_dependency_reports_status(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: None,
    )
    provider = SentenceTransformersEmbeddingsProvider()
    info = provider.provider_info()
    assert info["status"] == "missing_dependency"


def test_model_missing_with_local_files_only(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: FakeSentenceTransformer,
    )

    def failing_loader(*args, **kwargs):
        raise OSError("model not cached")

    provider = SentenceTransformersEmbeddingsProvider(model_loader=failing_loader)
    info = provider.provider_info()
    assert info["status"] == "model_missing"


def test_embed_query_returns_expected_dimension(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: FakeSentenceTransformer,
    )
    provider = SentenceTransformersEmbeddingsProvider(model_loader=FakeSentenceTransformer)
    vector = provider.embed_query("hello retrieval")
    assert len(vector) == 384
    assert vector == provider.embed_query("hello retrieval")


def test_empty_text_handled_safely(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: FakeSentenceTransformer,
    )
    provider = SentenceTransformersEmbeddingsProvider(model_loader=FakeSentenceTransformer)
    vector = provider.embed_query("")
    assert len(vector) == 384


def test_embed_documents_batch(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: FakeSentenceTransformer,
    )
    provider = SentenceTransformersEmbeddingsProvider(model_loader=FakeSentenceTransformer)
    vectors = provider.embed_documents(["one", "two"])
    assert len(vectors) == 2
    assert all(len(vector) == 384 for vector in vectors)


def test_dimension_mismatch_raises(monkeypatch):
    class WrongDimModel(FakeSentenceTransformer):
        def encode(self, texts, convert_to_numpy=True):
            if isinstance(texts, str):
                texts = [texts]
            return np.array([[0.1, 0.2]] * len(texts), dtype=float)

    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: WrongDimModel,
    )
    provider = SentenceTransformersEmbeddingsProvider(model_loader=WrongDimModel)
    with pytest.raises(EmbeddingsProviderUnavailableError):
        provider.embed_query("test")


def test_unavailable_provider_raises_on_embed(monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: None,
    )
    provider = SentenceTransformersEmbeddingsProvider()
    with pytest.raises(EmbeddingsProviderUnavailableError) as exc:
        provider.embed_query("test")
    assert exc.value.status == "missing_dependency"
