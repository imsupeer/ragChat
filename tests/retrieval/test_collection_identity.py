import pytest

from retrieval.collection_identity import (
    CHROMA_COLLECTION_STRATEGIES,
    build_embedding_collection_name,
    resolve_active_collection_name,
)


def test_build_embedding_collection_name_local_hash():
    name = build_embedding_collection_name(
        provider="local_hash",
        model="local-hash-v1",
        dimension=384,
        prefix="rag",
    )
    assert name == "rag_local_hash_local_hash_v1_384"


def test_build_embedding_collection_name_sentence_transformers():
    name = build_embedding_collection_name(
        provider="sentence_transformers",
        model="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
        prefix="rag",
    )
    assert len(name) <= 63
    assert name.startswith("rag_sentence_transformers_")


def test_build_embedding_collection_name_truncates_long_values():
    long_model = "x" * 200
    name = build_embedding_collection_name(
        provider="sentence_transformers",
        model=long_model,
        dimension=384,
        prefix="rag",
    )
    assert len(name) <= 63
    assert name.startswith("rag_sentence_transformers_")


def test_resolve_active_collection_legacy_single():
    name = resolve_active_collection_name(
        strategy="legacy_single",
        default_collection="rag_chat",
        collection_prefix="rag",
        provider="local_hash",
        model="local-hash-v1",
        dimension=384,
    )
    assert name == "rag_chat"


def test_resolve_active_collection_per_provider():
    name = resolve_active_collection_name(
        strategy="per_embedding_provider",
        default_collection="rag_chat",
        collection_prefix="rag",
        provider="ollama",
        model="mxbai-embed-large",
        dimension=1024,
    )
    assert name == "rag_ollama_mxbai_embed_large_1024"


def test_resolve_active_collection_falls_back_without_provider_info():
    name = resolve_active_collection_name(
        strategy="per_embedding_provider",
        default_collection="rag_chat",
        collection_prefix="rag",
    )
    assert name == "rag_chat"


@pytest.mark.parametrize("strategy", sorted(CHROMA_COLLECTION_STRATEGIES))
def test_known_collection_strategies(strategy: str):
    assert strategy in {"legacy_single", "per_embedding_provider"}
