from __future__ import annotations

from typing import Any

from langchain_core.documents import Document


def embedding_metadata_from_provider(provider_info: dict[str, Any]) -> dict[str, str | int]:
    return {
        "embedding_provider": str(provider_info["provider"]),
        "embedding_model": str(provider_info["model"]),
        "embedding_dimension": int(provider_info["dimension"]),
    }


def chunk_embedding_identity(metadata: dict[str, Any]) -> tuple[str, str, int] | None:
    provider = metadata.get("embedding_provider")
    model = metadata.get("embedding_model")
    dimension = metadata.get("embedding_dimension")
    if not provider or not model or dimension is None:
        return None
    try:
        return str(provider), str(model), int(dimension)
    except (TypeError, ValueError):
        return None


def matches_current_embedding(
    metadata: dict[str, Any],
    *,
    provider: str,
    model: str,
    dimension: int,
) -> bool:
    identity = chunk_embedding_identity(metadata)
    if identity is None:
        return True
    chunk_provider, chunk_model, chunk_dimension = identity
    return (
        chunk_provider == provider
        and chunk_model == model
        and chunk_dimension == dimension
    )


def filter_dense_results(
    docs: list[Document],
    *,
    provider: str,
    model: str,
    dimension: int,
) -> tuple[list[Document], dict[str, Any]]:
    kept: list[Document] = []
    filtered_mismatch = 0
    legacy_without_metadata = 0

    for doc in docs:
        identity = chunk_embedding_identity(doc.metadata)
        if identity is None:
            legacy_without_metadata += 1
            kept.append(doc)
            continue
        if matches_current_embedding(
            doc.metadata,
            provider=provider,
            model=model,
            dimension=dimension,
        ):
            kept.append(doc)
        else:
            filtered_mismatch += 1

    stats = {
        "filtered_mismatch_count": filtered_mismatch,
        "legacy_without_metadata_count": legacy_without_metadata,
        "embedding_provider": provider,
        "embedding_model": model,
        "embedding_dimension": dimension,
    }
    if filtered_mismatch > 0:
        stats["warning"] = (
            "Some dense retrieval candidates were filtered because they were indexed "
            "with a different embeddings provider or model."
        )
    if legacy_without_metadata > 0:
        stats["legacy_warning"] = (
            "Some chunks lack embeddings provider metadata and may have been indexed "
            "before provider tracking was added."
        )
    return kept, stats
