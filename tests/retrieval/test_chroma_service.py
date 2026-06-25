from langchain_core.documents import Document

from backend.services.chroma_service import ChromaService
from services.langchain_embeddings_adapter import LangChainEmbeddingsAdapter
from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider


def test_similarity_search_returns_top_k_results(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )
    docs = [
        Document(page_content="alpha queue worker", metadata={"source": "a.txt"}),
        Document(page_content="registry json metadata", metadata={"source": "b.txt"}),
        Document(page_content="gamma delta", metadata={"source": "c.txt"}),
    ]

    chroma_service.add_documents(document_id="doc-1", docs=docs)
    results = chroma_service.similarity_search("registry json", k=2)

    assert len(results) == 2
    assert results[0].metadata["source"] == "b.txt"


def test_similarity_search_handles_empty_results_with_non_matching_filter(
    tmp_path,
    fake_embeddings,
):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="alpha queue worker", metadata={"source": "a.txt"})],
    )

    results = chroma_service.similarity_search(
        "alpha",
        k=3,
        document_ids=["missing-doc"],
    )

    assert results == []


def test_delete_document_removes_only_matching_document(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[
            Document(
                page_content="alpha queue worker",
                metadata={"source": "a.txt"},
            )
        ],
    )
    chroma_service.add_documents(
        document_id="doc-2",
        docs=[
            Document(
                page_content="registry json metadata",
                metadata={"source": "b.txt"},
            )
        ],
    )

    chroma_service.delete_document("doc-1")

    remaining = chroma_service.list_documents()
    assert [(doc.metadata["document_id"], doc.metadata["source"]) for doc in remaining] == [
        ("doc-2", "b.txt")
    ]


def test_add_documents_stores_embedding_provider_metadata(tmp_path):
    provider = LocalHashEmbeddingsProvider()
    adapter = LangChainEmbeddingsAdapter(provider)
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=adapter,
        embeddings_provider=provider,
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="registry json", metadata={"source": "a.txt"})],
    )
    stored = chroma_service.list_documents(document_ids=["doc-1"])
    assert stored[0].metadata["embedding_provider"] == "local_hash"
    assert stored[0].metadata["embedding_model"] == "local-hash-v1"
    assert stored[0].metadata["embedding_dimension"] == 384


def test_per_provider_collection_routes_vectors(tmp_path):
    provider = LocalHashEmbeddingsProvider()
    adapter = LangChainEmbeddingsAdapter(provider)
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=adapter,
        embeddings_provider=provider,
        collection_strategy="per_embedding_provider",
    )
    assert chroma_service.collection_name == "rag_local_hash_local_hash_v1_384"
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="alpha", metadata={"source": "a.txt"})],
    )
    assert chroma_service.list_documents()
    legacy_counts = chroma_service._document_counts_for_collection("rag_chat")
    assert legacy_counts == {}


def test_legacy_single_uses_default_collection(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
        collection_strategy="legacy_single",
        default_collection="rag_chat",
    )
    assert chroma_service.collection_name == "rag_chat"


def test_delete_document_removes_from_all_known_collections(tmp_path):
    provider = LocalHashEmbeddingsProvider()
    adapter = LangChainEmbeddingsAdapter(provider)
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=adapter,
        embeddings_provider=provider,
        collection_strategy="per_embedding_provider",
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="active collection", metadata={"source": "a.txt"})],
    )
    legacy_store = chroma_service._vector_store_for("rag_chat")
    legacy_store.add_documents(
        documents=[
            Document(
                page_content="legacy collection",
                metadata={"document_id": "doc-1", "chunk_id": "legacy-1", "source": "b.txt"},
            )
        ],
        ids=["legacy-1"],
    )

    chroma_service.delete_document("doc-1")

    assert chroma_service.list_documents() == []
    assert chroma_service._document_counts_for_collection("rag_chat") == {}


def test_lexical_cache_scoped_to_collection(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
        collection_strategy="legacy_single",
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="registry json metadata", metadata={"source": "a.txt"})],
    )
    chroma_service.lexical_search("registry", k=1)
    first_stats = chroma_service.get_last_lexical_cache_stats()
    assert first_stats.get("cache_hit") is False

    chroma_service.lexical_search("registry", k=1)
    second_stats = chroma_service.get_last_lexical_cache_stats()
    assert second_stats.get("cache_hit") is True
