from langchain_core.documents import Document

from backend.retrieval.retriever import Retriever


class FakeChromaService:
    def __init__(self, dense_docs: list[Document], lexical_docs: list[Document]) -> None:
        self.dense_docs = dense_docs
        self.lexical_docs = lexical_docs
        self.lexical_called = False

    def similarity_search(self, query: str, k: int = 5, document_ids=None):
        return self.dense_docs[:k]

    def lexical_search(self, query: str, k: int = 5, document_ids=None):
        self.lexical_called = True
        return self.lexical_docs[:k]


def build_doc(
    chunk_id: str,
    *,
    dense_rank: int | None = None,
    dense_score: float | None = None,
    lexical_rank: int | None = None,
    lexical_score: float | None = None,
) -> Document:
    metadata = {
        "chunk_id": chunk_id,
        "document_id": f"doc-{chunk_id}",
        "chunk_index": 0,
        "source": f"{chunk_id}.md",
    }

    if dense_rank is not None:
        metadata["_dense_rank"] = dense_rank
        metadata["_dense_score"] = dense_score
        metadata["_retrieval_rank"] = dense_rank
        metadata["_retrieval_score"] = dense_score
        metadata["_retrieval_score_type"] = "distance"
        metadata["_retrieval_method"] = "dense"
        metadata["_retrieval_methods"] = ["dense"]

    if lexical_rank is not None:
        metadata["_lexical_rank"] = lexical_rank
        metadata["_lexical_score"] = lexical_score
        metadata["_retrieval_rank"] = lexical_rank
        metadata["_retrieval_score"] = lexical_score
        metadata["_retrieval_score_type"] = "bm25"
        metadata["_retrieval_method"] = "lexical"
        metadata["_retrieval_methods"] = ["lexical"]

    return Document(page_content=f"content for {chunk_id}", metadata=metadata)


def test_retriever_uses_dense_only_when_hybrid_is_disabled():
    dense_docs = [build_doc("chunk-a", dense_rank=1, dense_score=0.12)]
    lexical_docs = [build_doc("chunk-b", lexical_rank=1, lexical_score=5.0)]
    chroma_service = FakeChromaService(dense_docs=dense_docs, lexical_docs=lexical_docs)

    retriever = Retriever(
        chroma_service=chroma_service,
        top_k=5,
        enable_hybrid=False,
    )
    results = retriever.search("registry.json")

    assert results == dense_docs
    assert chroma_service.lexical_called is False


def test_retriever_fuses_dense_and_lexical_results_with_rrf():
    dense_docs = [
        build_doc("chunk-a", dense_rank=1, dense_score=0.12),
        build_doc("chunk-b", dense_rank=2, dense_score=0.18),
    ]
    lexical_docs = [
        build_doc("chunk-b", lexical_rank=1, lexical_score=4.2),
        build_doc("chunk-c", lexical_rank=2, lexical_score=3.8),
    ]
    chroma_service = FakeChromaService(dense_docs=dense_docs, lexical_docs=lexical_docs)

    retriever = Retriever(
        chroma_service=chroma_service,
        top_k=3,
        enable_hybrid=True,
        rrf_k=60,
    )
    results = retriever.search("registry.json")

    assert [doc.metadata["chunk_id"] for doc in results] == [
        "chunk-b",
        "chunk-a",
        "chunk-c",
    ]
    assert results[0].metadata["_retrieval_method"] == "hybrid"
    assert results[0].metadata["_retrieval_methods"] == ["dense", "lexical"]
    assert results[0].metadata["_dense_rank"] == 2
    assert results[0].metadata["_lexical_rank"] == 1
    assert results[0].metadata["_retrieval_score_type"] == "rrf"
    assert chroma_service.lexical_called is True
