from __future__ import annotations

import hashlib
import re

CHROMA_COLLECTION_STRATEGIES = frozenset({"legacy_single", "per_embedding_provider"})
MAX_COLLECTION_NAME_LENGTH = 63


def _sanitize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


def build_embedding_collection_name(
    *,
    provider: str,
    model: str,
    dimension: int,
    prefix: str = "rag",
) -> str:
    provider_part = _sanitize_token(provider) or "provider"
    model_part = _sanitize_token(model.replace("/", "_").replace(":", "_")) or "model"
    base = f"{prefix}_{provider_part}_{model_part}_{dimension}"
    if len(base) <= MAX_COLLECTION_NAME_LENGTH:
        return base

    digest = hashlib.sha256(f"{provider}:{model}:{dimension}".encode("utf-8")).hexdigest()[:8]
    trimmed = base[: MAX_COLLECTION_NAME_LENGTH - 9].rstrip("_")
    return f"{trimmed}_{digest}"


def resolve_active_collection_name(
    *,
    strategy: str,
    default_collection: str,
    collection_prefix: str,
    provider: str | None = None,
    model: str | None = None,
    dimension: int | None = None,
) -> str:
    if strategy == "legacy_single":
        return default_collection
    if not provider or not model or dimension is None:
        return default_collection
    return build_embedding_collection_name(
        provider=provider,
        model=model,
        dimension=dimension,
        prefix=collection_prefix,
    )


def build_collection_identity(
    *,
    provider: str,
    model: str,
    dimension: int,
    prefix: str = "rag",
) -> dict[str, object]:
    collection_name = build_embedding_collection_name(
        provider=provider,
        model=model,
        dimension=dimension,
        prefix=prefix,
    )
    return {
        "collection_name": collection_name,
        "provider": provider,
        "model": model,
        "dimension": dimension,
        "display_name": f"{provider} / {dimension}d",
    }
