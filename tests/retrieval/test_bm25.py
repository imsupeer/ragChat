from langchain_core.documents import Document

from backend.retrieval.bm25 import BM25Index


def test_bm25_prefers_exact_keyword_match():
    docs = [
        Document(
            page_content="registry.json stores document registry entries for the app",
            metadata={"chunk_id": "chunk-1"},
        ),
        Document(
            page_content="ChromaDB stores vectors for semantic retrieval",
            metadata={"chunk_id": "chunk-2"},
        ),
    ]

    results = BM25Index(docs).search("registry.json", k=2)

    assert len(results) == 1
    top_doc, score = results[0]
    assert top_doc.metadata["chunk_id"] == "chunk-1"
    assert score > 0
