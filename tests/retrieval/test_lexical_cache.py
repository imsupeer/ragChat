from unittest.mock import patch

import pytest
from langchain_core.documents import Document

from backend.retrieval.lexical_cache import LexicalSearchCache
from backend.services.chroma_service import ChromaService


def test_lexical_cache_key_for_scoped_documents():
    assert LexicalSearchCache.cache_key(None) == "all"
    assert LexicalSearchCache.cache_key(["b", "a"]) == "a,b"


def test_lexical_cache_filters_documents_by_document_id():
    docs = [
        Document(page_content="a", metadata={"document_id": "doc-1"}),
        Document(page_content="b", metadata={"document_id": "doc-2"}),
    ]

    filtered = LexicalSearchCache.filter_documents(docs, ["doc-2"])
    assert len(filtered) == 1
    assert filtered[0].metadata["document_id"] == "doc-2"


def test_lexical_cache_reuses_corpus_and_index_on_repeat_search():
    cache = LexicalSearchCache()
    load_calls = {"count": 0}

    def load_corpus():
        load_calls["count"] += 1
        return [
            Document(
                page_content="registry json metadata",
                metadata={"document_id": "doc-1", "chunk_id": "c1"},
            )
        ]

    cache.search(
        query="registry json",
        k=1,
        document_ids=None,
        load_corpus=load_corpus,
    )
    first_stats = dict(cache.last_stats)

    cache.search(
        query="registry json",
        k=1,
        document_ids=None,
        load_corpus=load_corpus,
    )
    second_stats = dict(cache.last_stats)

    assert load_calls["count"] == 1
    assert first_stats["corpus_cache_hit"] is False
    assert first_stats["index_cache_hit"] is False
    assert second_stats["corpus_cache_hit"] is True
    assert second_stats["index_cache_hit"] is True
    assert second_stats["cache_hit"] is True


def test_lexical_cache_invalidates_corpus_and_indexes():
    cache = LexicalSearchCache()
    load_calls = {"count": 0}

    def load_corpus():
        load_calls["count"] += 1
        return [
            Document(
                page_content="registry json metadata",
                metadata={"document_id": "doc-1", "chunk_id": "c1"},
            )
        ]

    cache.search(query="registry", k=1, document_ids=None, load_corpus=load_corpus)
    cache.invalidate()
    cache.search(query="registry", k=1, document_ids=None, load_corpus=load_corpus)

    assert load_calls["count"] == 2


def test_lexical_search_returns_ranked_metadata(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[
            Document(page_content="alpha queue worker", metadata={"source": "a.txt"}),
            Document(page_content="registry json metadata", metadata={"source": "b.txt"}),
        ],
    )

    results = chroma_service.lexical_search("registry json", k=1)

    assert len(results) == 1
    assert results[0].metadata["source"] == "b.txt"
    assert results[0].metadata["_retrieval_method"] == "lexical"
    assert results[0].metadata["_retrieval_score_type"] == "bm25"
    assert results[0].metadata["_lexical_rank"] == 1


def test_lexical_search_respects_document_ids_filter(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="registry json alpha", metadata={"source": "a.txt"})],
    )
    chroma_service.add_documents(
        document_id="doc-2",
        docs=[Document(page_content="registry json beta", metadata={"source": "b.txt"})],
    )

    results = chroma_service.lexical_search(
        "registry json",
        k=5,
        document_ids=["doc-2"],
    )

    assert len(results) == 1
    assert results[0].metadata["document_id"] == "doc-2"


def test_lexical_search_empty_corpus_returns_empty_list(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )

    assert chroma_service.lexical_search("anything", k=5) == []


def test_lexical_cache_invalidates_after_add_documents(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="registry json", metadata={"source": "a.txt"})],
    )

    with patch.object(
        ChromaService,
        "list_documents",
        wraps=chroma_service.list_documents,
    ) as list_documents:
        chroma_service.lexical_search("registry", k=1)
        chroma_service.lexical_search("registry", k=1)
        chroma_service.add_documents(
            document_id="doc-2",
            docs=[Document(page_content="queue worker", metadata={"source": "b.txt"})],
        )
        chroma_service.lexical_search("queue", k=1)

    assert list_documents.call_count == 2


def test_lexical_cache_invalidates_after_delete_document(tmp_path, fake_embeddings):
    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )
    chroma_service.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="registry json", metadata={"source": "a.txt"})],
    )
    chroma_service.add_documents(
        document_id="doc-2",
        docs=[Document(page_content="queue worker", metadata={"source": "b.txt"})],
    )

    with patch.object(
        ChromaService,
        "list_documents",
        wraps=chroma_service.list_documents,
    ) as list_documents:
        chroma_service.lexical_search("registry", k=1)
        chroma_service.lexical_search("registry", k=1)
        chroma_service.delete_document("doc-1")
        chroma_service.lexical_search("queue", k=1)

    assert list_documents.call_count == 2


def test_hybrid_retriever_uses_cached_lexical_path(tmp_path, fake_embeddings):
    from backend.retrieval.retriever import Retriever

    chroma_service = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=fake_embeddings,
    )
    chroma_service.add_documents(
        document_id="doc-dense",
        docs=[Document(page_content="semantic only content", metadata={"source": "d.txt"})],
    )
    chroma_service.add_documents(
        document_id="doc-lexical",
        docs=[Document(page_content="registry json metadata", metadata={"source": "r.txt"})],
    )

    retriever = Retriever(chroma_service=chroma_service, top_k=3, enable_hybrid=True)

    with patch.object(
        ChromaService,
        "list_documents",
        wraps=chroma_service.list_documents,
    ) as list_documents:
        first = retriever.search("registry json")
        second = retriever.search("registry json")

    assert list_documents.call_count == 1
    assert any(doc.metadata.get("_retrieval_method") == "hybrid" for doc in first)
    assert len(second) >= 1
