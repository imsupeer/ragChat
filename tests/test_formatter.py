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
            metadata={"source": "file.txt", "page": 1, "chunk_index": 0},
        )
    ]

    sources = serialize_sources(docs)
    assert len(sources) == 1
    assert sources[0]["source"] == "file.txt"
