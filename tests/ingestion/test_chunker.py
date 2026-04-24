import pytest
from langchain_core.documents import Document

from backend.ingestion.chunker import build_text_splitter, chunk_documents


@pytest.mark.parametrize(
    ("text", "chunk_size", "chunk_overlap", "expected_min_chunks"),
    [
        ("Short text.", 50, 10, 1),
        ("".join(f"{index:03d}" for index in range(80)), 50, 10, 2),
    ],
)
def test_text_splitter_handles_small_and_large_documents(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    expected_min_chunks: int,
):
    splitter = build_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_text(text)

    assert len(chunks) >= expected_min_chunks
    assert all(len(chunk) <= chunk_size for chunk in chunks)


def test_text_splitter_respects_overlap_for_large_documents():
    text = "".join(f"{index:03d}" for index in range(80))
    splitter = build_text_splitter(chunk_size=50, chunk_overlap=10)

    chunks = splitter.split_text(text)

    assert len(chunks) > 1
    assert chunks[0][-10:] == chunks[1][:10]


def test_markdown_chunking_preserves_heading_path_metadata():
    docs = [
        Document(
            page_content=(
                "# Architecture\n\n"
                "The system is organized into backend and frontend layers.\n\n"
                "## Retrieval\n\n"
                "Hybrid retrieval combines dense search with lexical search."
            ),
            metadata={},
        )
    ]

    chunks = chunk_documents(
        docs=docs,
        source_path="notes.md",
        chunk_size=500,
        chunk_overlap=50,
    )

    assert len(chunks) == 2
    assert chunks[0].metadata["section_title"] == "Architecture"
    assert chunks[0].metadata["section_path"] == "Architecture"
    assert chunks[1].metadata["section_title"] == "Retrieval"
    assert chunks[1].metadata["section_path"] == "Architecture > Retrieval"
    assert chunks[1].page_content.startswith("Section: Architecture > Retrieval")


def test_pdf_chunking_preserves_page_and_detected_section_metadata():
    docs = [
        Document(
            page_content="SYSTEM OVERVIEW\nThe application stores vectors in ChromaDB.",
            metadata={"page": 0},
        )
    ]

    chunks = chunk_documents(
        docs=docs,
        source_path="report.pdf",
        chunk_size=500,
        chunk_overlap=50,
    )

    assert len(chunks) == 1
    assert chunks[0].metadata["page"] == 1
    assert chunks[0].metadata["section_title"] == "SYSTEM OVERVIEW"
    assert chunks[0].metadata["section_path"] == "Page 1 > SYSTEM OVERVIEW"
    assert chunks[0].page_content.startswith("Section: Page 1 > SYSTEM OVERVIEW")
