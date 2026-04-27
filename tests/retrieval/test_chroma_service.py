from langchain_core.documents import Document

from backend.services.chroma_service import ChromaService


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
