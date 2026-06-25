from langchain_core.documents import Document

from retrieval.embedding_metadata import (
    embedding_metadata_from_provider,
    filter_dense_results,
    matches_current_embedding,
)
from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider


def test_embedding_metadata_from_provider():
    provider = LocalHashEmbeddingsProvider()
    metadata = embedding_metadata_from_provider(provider.provider_info())
    assert metadata == {
        "embedding_provider": "local_hash",
        "embedding_model": "local-hash-v1",
        "embedding_dimension": 384,
    }


def test_filter_dense_results_removes_mismatched_chunks():
    docs = [
        Document(
            page_content="match",
            metadata={
                "embedding_provider": "local_hash",
                "embedding_model": "local-hash-v1",
                "embedding_dimension": 384,
            },
        ),
        Document(
            page_content="mismatch",
            metadata={
                "embedding_provider": "ollama",
                "embedding_model": "mxbai-embed-large",
                "embedding_dimension": 1024,
            },
        ),
        Document(page_content="legacy", metadata={}),
    ]
    kept, stats = filter_dense_results(
        docs,
        provider="local_hash",
        model="local-hash-v1",
        dimension=384,
    )
    assert [doc.page_content for doc in kept] == ["match", "legacy"]
    assert stats["filtered_mismatch_count"] == 1
    assert stats["legacy_without_metadata_count"] == 1
    assert "warning" in stats


def test_matches_current_embedding():
    metadata = {
        "embedding_provider": "ollama",
        "embedding_model": "mxbai-embed-large",
        "embedding_dimension": 1024,
    }
    assert matches_current_embedding(
        metadata,
        provider="ollama",
        model="mxbai-embed-large",
        dimension=1024,
    )
    assert not matches_current_embedding(
        metadata,
        provider="local_hash",
        model="local-hash-v1",
        dimension=384,
    )


def test_sentence_transformers_metadata_filtering():
    docs = [
        Document(
            page_content="st",
            metadata={
                "embedding_provider": "sentence_transformers",
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                "embedding_dimension": 384,
            },
        ),
        Document(
            page_content="ollama",
            metadata={
                "embedding_provider": "ollama",
                "embedding_model": "mxbai-embed-large",
                "embedding_dimension": 1024,
            },
        ),
    ]
    kept, stats = filter_dense_results(
        docs,
        provider="sentence_transformers",
        model="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
    )
    assert [doc.page_content for doc in kept] == ["st"]
    assert stats["filtered_mismatch_count"] == 1
