import pytest

from services.embedding_collection_diagnostics import (
    evaluate_embedding_collection_status,
    summarize_chunk_metadata,
)


def test_empty_collection_status():
    result = evaluate_embedding_collection_status(
        provider="local_hash",
        model="local-hash-v1",
        dimension=384,
        collection={
            "total_chunks": 0,
            "matching_chunks": 0,
            "mismatched_provider_chunks": 0,
            "mismatched_model_chunks": 0,
            "mismatched_dimension_chunks": 0,
            "legacy_chunks": 0,
        },
    )
    assert result["status"] == "empty"
    assert result["reindex_recommended"] is False


def test_all_matching_collection_status():
    result = evaluate_embedding_collection_status(
        provider="sentence_transformers",
        model="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
        collection={
            "total_chunks": 5,
            "matching_chunks": 5,
            "mismatched_provider_chunks": 0,
            "mismatched_model_chunks": 0,
            "mismatched_dimension_chunks": 0,
            "legacy_chunks": 0,
        },
    )
    assert result["status"] == "ok"
    assert result["reindex_recommended"] is False


def test_provider_mismatch_collection_status():
    result = evaluate_embedding_collection_status(
        provider="local_hash",
        model="local-hash-v1",
        dimension=384,
        collection={
            "total_chunks": 3,
            "matching_chunks": 1,
            "mismatched_provider_chunks": 2,
            "mismatched_model_chunks": 0,
            "mismatched_dimension_chunks": 0,
            "legacy_chunks": 0,
        },
    )
    assert result["status"] == "mixed"
    assert result["reindex_recommended"] is True


def test_legacy_only_collection_status():
    result = evaluate_embedding_collection_status(
        provider="ollama",
        model="mxbai-embed-large",
        dimension=1024,
        collection={
            "total_chunks": 4,
            "matching_chunks": 0,
            "mismatched_provider_chunks": 0,
            "mismatched_model_chunks": 0,
            "mismatched_dimension_chunks": 0,
            "legacy_chunks": 4,
        },
    )
    assert result["status"] == "legacy"
    assert result["reindex_recommended"] is True


def test_summarize_chunk_metadata_counts():
    metadatas = [
        {
            "embedding_provider": "local_hash",
            "embedding_model": "local-hash-v1",
            "embedding_dimension": 384,
        },
        {
            "embedding_provider": "ollama",
            "embedding_model": "mxbai-embed-large",
            "embedding_dimension": 1024,
        },
        {},
    ]
    summary = summarize_chunk_metadata(
        metadatas,
        provider="local_hash",
        model="local-hash-v1",
        dimension=384,
    )
    assert summary["total_chunks"] == 3
    assert summary["matching_chunks"] == 1
    assert summary["mismatched_provider_chunks"] == 1
    assert summary["legacy_chunks"] == 1


class FakeMetadataSource:
    def __init__(self, metadatas: list[dict]) -> None:
        self._metadatas = metadatas

    def list_chunk_metadatas(self) -> list[dict]:
        return self._metadatas


def test_build_diagnostics_does_not_expose_document_text():
    from services.embedding_collection_diagnostics import build_embedding_collection_diagnostics

    source = FakeMetadataSource(
        [
            {
                "embedding_provider": "ollama",
                "embedding_model": "mxbai-embed-large",
                "embedding_dimension": 1024,
            }
        ]
    )
    diagnostics = build_embedding_collection_diagnostics(
        source,
        provider="local_hash",
        model="local-hash-v1",
        dimension=384,
    )
    payload = str(diagnostics)
    assert "page_content" not in payload
    assert diagnostics["status"] == "mixed"
    assert diagnostics["reindex_recommended"] is True
