from __future__ import annotations

from typing import Any, Protocol

from retrieval.embedding_metadata import chunk_embedding_identity


class ChunkMetadataSource(Protocol):
    def list_chunk_metadatas(self) -> list[dict[str, Any]]:
        ...


def summarize_chunk_metadata(
    metadatas: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
    dimension: int,
) -> dict[str, int]:
    total_chunks = len(metadatas)
    matching_chunks = 0
    legacy_chunks = 0
    mismatched_provider_chunks = 0
    mismatched_model_chunks = 0
    mismatched_dimension_chunks = 0

    for metadata in metadatas:
        identity = chunk_embedding_identity(metadata)
        if identity is None:
            legacy_chunks += 1
            continue

        chunk_provider, chunk_model, chunk_dimension = identity
        if (
            chunk_provider == provider
            and chunk_model == model
            and chunk_dimension == dimension
        ):
            matching_chunks += 1
            continue

        if chunk_provider != provider:
            mismatched_provider_chunks += 1
        if chunk_model != model:
            mismatched_model_chunks += 1
        if chunk_dimension != dimension:
            mismatched_dimension_chunks += 1

    return {
        "total_chunks": total_chunks,
        "matching_chunks": matching_chunks,
        "mismatched_provider_chunks": mismatched_provider_chunks,
        "mismatched_model_chunks": mismatched_model_chunks,
        "mismatched_dimension_chunks": mismatched_dimension_chunks,
        "legacy_chunks": legacy_chunks,
    }


def evaluate_embedding_collection_status(
    *,
    provider: str,
    model: str,
    dimension: int,
    collection: dict[str, int],
) -> dict[str, Any]:
    active = {
        "provider": provider,
        "model": model,
        "dimension": dimension,
    }
    total = collection.get("total_chunks", 0)
    matching = collection.get("matching_chunks", 0)
    legacy = collection.get("legacy_chunks", 0)
    mismatch_provider = collection.get("mismatched_provider_chunks", 0)
    mismatch_model = collection.get("mismatched_model_chunks", 0)
    mismatch_dimension = collection.get("mismatched_dimension_chunks", 0)
    has_mismatch = any(
        value > 0
        for value in (mismatch_provider, mismatch_model, mismatch_dimension)
    )

    if total == 0:
        return {
            "active": active,
            "collection": collection,
            "status": "empty",
            "reindex_recommended": False,
            "message": "No indexed chunks found for embeddings diagnostics.",
        }

    if matching == total:
        return {
            "active": active,
            "collection": collection,
            "status": "ok",
            "reindex_recommended": False,
            "message": "Collection matches the active embeddings provider.",
        }

    if has_mismatch:
        return {
            "active": active,
            "collection": collection,
            "status": "mixed",
            "reindex_recommended": True,
            "message": (
                "Existing chunks were indexed with another embeddings provider or model. "
                "Reindex documents before evaluating retrieval quality."
            ),
        }

    if legacy == total:
        return {
            "active": active,
            "collection": collection,
            "status": "legacy",
            "reindex_recommended": True,
            "message": (
                "Indexed chunks lack embeddings provider metadata. "
                "Reindex documents before evaluating retrieval quality."
            ),
        }

    if legacy > 0:
        return {
            "active": active,
            "collection": collection,
            "status": "legacy",
            "reindex_recommended": True,
            "message": (
                "Some indexed chunks use legacy embeddings metadata. "
                "Reindex documents before evaluating retrieval quality."
            ),
        }

    return {
        "active": active,
        "collection": collection,
        "status": "unknown",
        "reindex_recommended": False,
        "message": "Embeddings collection status could not be determined.",
    }


def build_embedding_collection_diagnostics(
    metadata_source: ChunkMetadataSource,
    *,
    provider: str,
    model: str,
    dimension: int,
) -> dict[str, Any]:
    try:
        metadatas = metadata_source.list_chunk_metadatas()
    except Exception as exc:
        return {
            "active": {
                "provider": provider,
                "model": model,
                "dimension": dimension,
            },
            "collection": {
                "total_chunks": 0,
                "matching_chunks": 0,
                "mismatched_provider_chunks": 0,
                "mismatched_model_chunks": 0,
                "mismatched_dimension_chunks": 0,
                "legacy_chunks": 0,
            },
            "status": "error",
            "reindex_recommended": False,
            "message": "Embeddings collection diagnostics are unavailable.",
            "detail": str(exc),
        }

    summary = summarize_chunk_metadata(
        metadatas,
        provider=provider,
        model=model,
        dimension=dimension,
    )
    return evaluate_embedding_collection_status(
        provider=provider,
        model=model,
        dimension=dimension,
        collection=summary,
    )
