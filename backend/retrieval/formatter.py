from typing import List
from langchain_core.documents import Document
from core.observability import build_chunk_debug


def format_retrieved_chunks(docs: List[Document]) -> str:
    sections = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page", "n/a")
        chunk_index = doc.metadata.get("chunk_index", "n/a")

        header = f"[SOURCE: {source} | page={page} | chunk={chunk_index}]"
        sections.append(f"{header}\n{doc.page_content}")

    return "\n\n".join(sections)


def serialize_sources(docs: List[Document]) -> list[dict]:
    sources = []
    for doc in docs:
        chunk_debug = build_chunk_debug(doc)
        sources.append(
            {
                "source": doc.metadata.get("source", "unknown"),
                "page": doc.metadata.get("page"),
                "chunk_index": doc.metadata.get("chunk_index"),
                "section_title": chunk_debug["section_title"],
                "section_path": chunk_debug["section_path"],
                "preview": doc.page_content[:280],
                "chunk_id": chunk_debug["chunk_id"],
                "document_id": chunk_debug["document_id"],
                "score": chunk_debug["score"],
                "score_type": chunk_debug["score_type"],
                "rank": chunk_debug["rank"],
                "retrieval_method": chunk_debug["retrieval_method"],
                "retrieval_methods": chunk_debug["retrieval_methods"],
                "retrieval_rank": chunk_debug["retrieval_rank"],
                "retrieval_score": chunk_debug["retrieval_score"],
                "retrieval_score_type": chunk_debug["retrieval_score_type"],
                "rerank_rank": chunk_debug["rerank_rank"],
                "rerank_score": chunk_debug["rerank_score"],
                "dense_rank": chunk_debug["dense_rank"],
                "dense_score": chunk_debug["dense_score"],
                "lexical_rank": chunk_debug["lexical_rank"],
                "lexical_score": chunk_debug["lexical_score"],
                "fused_score": chunk_debug["fused_score"],
                "metadata": chunk_debug["metadata"],
            }
        )
    return sources
