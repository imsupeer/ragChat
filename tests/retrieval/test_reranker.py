from langchain_core.documents import Document

from backend.retrieval.reranker import HeuristicReranker


def build_doc(chunk_id: str, content: str, retrieval_rank: int) -> Document:
    return Document(
        page_content=content,
        metadata={
            "chunk_id": chunk_id,
            "source": f"{chunk_id}.md",
            "document_id": f"doc-{chunk_id}",
            "chunk_index": 0,
            "_retrieval_rank": retrieval_rank,
            "_retrieval_score": 0.1 * retrieval_rank,
            "_retrieval_score_type": "distance",
            "_retrieval_method": "dense",
            "_retrieval_methods": ["dense"],
        },
    )


def test_reranker_promotes_exact_term_matches():
    docs = [
        build_doc(
            "chunk-a",
            "The system uses a background worker and queue for indexing.",
            retrieval_rank=1,
        ),
        build_doc(
            "chunk-b",
            "registry.json stores the document registry entries for the app.",
            retrieval_rank=2,
        ),
        build_doc(
            "chunk-c",
            "ChromaDB stores vectors for semantic search.",
            retrieval_rank=3,
        ),
    ]

    reranker = HeuristicReranker()
    reranked = reranker.rerank(
        "Which file stores document registry entries?",
        docs,
        top_m=3,
        top_k=2,
    )

    assert [doc.metadata["chunk_id"] for doc in reranked] == ["chunk-b", "chunk-a"]
    assert reranked[0].metadata["_rerank_rank"] == 1
    assert reranked[0].metadata["_rerank_score"] > reranked[1].metadata["_rerank_score"]
