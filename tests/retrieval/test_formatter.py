from langchain_core.documents import Document

from backend.retrieval.formatter import format_retrieved_chunks, serialize_sources


def test_format_retrieved_chunks():
    docs = [
        Document(
            page_content="Example content",
            metadata={"source": "file.txt", "page": 1, "chunk_index": 0},
        )
    ]

    output = format_retrieved_chunks(docs)
    assert "file.txt" in output
    assert "Example content" in output


def test_serialize_sources():
    docs = [
        Document(
            page_content="Example content",
            metadata={
                "source": "file.txt",
                "page": 1,
                "chunk_index": 0,
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "section_title": "Retrieval",
                "section_path": "Architecture > Retrieval",
                "_retrieval_score": 0.123,
                "_retrieval_rank": 1,
                "_retrieval_score_type": "rrf",
                "_retrieval_method": "hybrid",
                "_retrieval_methods": ["dense", "lexical"],
                "_dense_score": 0.42,
                "_dense_rank": 2,
                "_lexical_score": 4.5,
                "_lexical_rank": 1,
                "_hybrid_fused_score": 0.0325,
                "_rerank_score": 6.75,
                "_rerank_rank": 1,
            },
        )
    ]

    sources = serialize_sources(docs)

    assert len(sources) == 1
    assert sources[0]["source"] == "file.txt"
    assert sources[0]["document_id"] == "doc-1"
    assert sources[0]["chunk_id"] == "chunk-1"
    assert sources[0]["section_title"] == "Retrieval"
    assert sources[0]["section_path"] == "Architecture > Retrieval"
    assert sources[0]["score"] == 6.75
    assert sources[0]["rank"] == 1
    assert sources[0]["score_type"] == "rerank"
    assert sources[0]["retrieval_method"] == "hybrid"
    assert sources[0]["retrieval_methods"] == ["dense", "lexical"]
    assert sources[0]["retrieval_rank"] == 1
    assert sources[0]["retrieval_score"] == 0.123
    assert sources[0]["retrieval_score_type"] == "rrf"
    assert sources[0]["rerank_rank"] == 1
    assert sources[0]["rerank_score"] == 6.75
    assert sources[0]["dense_rank"] == 2
    assert sources[0]["lexical_rank"] == 1
    assert sources[0]["fused_score"] == 0.0325
    assert sources[0]["metadata"]["document_id"] == "doc-1"
    assert "_retrieval_score" not in sources[0]["metadata"]
