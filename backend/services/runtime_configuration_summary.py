from __future__ import annotations

from typing import Any

from core.config import Settings
from retrieval.collection_identity import resolve_active_collection_name
from services.embeddings_provider_resolver import resolve_embeddings_provider
from services.sentence_transformers_runtime import inspect_sentence_transformers_setup


def build_embeddings_runtime_section(
    embeddings_provider: str,
    settings: Settings,
) -> dict[str, Any]:
    normalized = (embeddings_provider or "ollama").strip().lower()
    if normalized == "local_hash":
        return {
            "provider": "local_hash",
            "quality": "demo",
            "status": "ok",
            "message": "Dependency-free demo embeddings.",
            "zero_ollama_compatible": True,
            "ollama_required": False,
        }

    if normalized == "sentence_transformers":
        report = inspect_sentence_transformers_setup(
            model_name=settings.sentence_transformers_model,
            dimension=settings.sentence_transformers_dimension,
            device=settings.sentence_transformers_device,
            cache_dir=settings.sentence_transformers_cache_dir,
            local_files_only=settings.sentence_transformers_local_files_only,
        )
        return {
            "provider": "sentence_transformers",
            "model": settings.sentence_transformers_model,
            "quality": "semantic",
            "zero_ollama_compatible": True,
            "ollama_required": False,
            "status": report.get("status"),
            "message": report.get("message"),
            "dependency_installed": report.get("dependency_installed"),
            "model_available": report.get("model_available"),
            "check_command": report.get("check_command"),
        }

    if normalized == "ollama":
        return {
            "provider": "ollama",
            "model": settings.ollama_embed_model,
            "quality": "semantic",
            "status": "requires_ollama",
            "message": "Ollama is required for embeddings in this mode.",
            "zero_ollama_compatible": False,
            "ollama_required": True,
        }

    return {
        "provider": normalized,
        "status": "unknown",
        "message": f"Unknown embeddings provider: {normalized}",
    }


def runtime_configuration_lines(
    *,
    chat_provider: str,
    embeddings_provider: str,
    settings: Settings,
    chat_model: str = "",
) -> list[str]:
    lines = [f"- Chat provider: {chat_provider}"]
    if chat_model:
        lines.append(f"- Chat model: {chat_model}")

    section = build_embeddings_runtime_section(embeddings_provider, settings)
    lines.append(f"- Embeddings provider: {section.get('provider', embeddings_provider)}")
    quality = section.get("quality")
    if quality:
        lines.append(f"- Embeddings quality: {quality}")
    if section.get("model"):
        lines.append(f"- Embeddings model: {section['model']}")
    if embeddings_provider == "sentence_transformers":
        lines.append(f"- Sentence-transformers ready: {section.get('status')}")
    if section.get("ollama_required") is True:
        lines.append("- Ollama required: yes")
    elif section.get("ollama_required") is False:
        lines.append("- Ollama required: no")

    lines.append(f"- Chroma collection strategy: {settings.chroma_collection_strategy}")
    try:
        provider = resolve_embeddings_provider(settings)
        info = provider.provider_info()
        active_collection = resolve_active_collection_name(
            strategy=settings.chroma_collection_strategy,
            default_collection=settings.chroma_default_collection,
            collection_prefix=settings.chroma_collection_prefix,
            provider=str(info["provider"]),
            model=str(info["model"]),
            dimension=int(info["dimension"]),
        )
        lines.append(f"- Active Chroma collection: {active_collection}")
        if settings.chroma_collection_strategy == "per_embedding_provider":
            lines.append(
                "- Vector isolation: embeddings are stored in provider-specific collections"
            )
    except Exception:
        lines.append(f"- Default Chroma collection: {settings.chroma_default_collection}")

    lines.append("- Reindex helper: python scripts/reindex_documents.py --dry-run")

    return lines
