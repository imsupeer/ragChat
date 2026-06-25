from pathlib import Path

import pytest
from langchain_core.documents import Document

from services.document_reindex import DocumentReindexService
from services.document_registry import DocumentRegistry
from services.chroma_service import ChromaService
from services.langchain_embeddings_adapter import LangChainEmbeddingsAdapter
from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider
from services.metrics import get_local_metrics, reset_local_metrics


@pytest.fixture(autouse=True)
def reset_metrics():
    reset_local_metrics()
    yield
    reset_local_metrics()


def build_service(tmp_path: Path) -> tuple[DocumentReindexService, DocumentRegistry, ChromaService]:
    provider = LocalHashEmbeddingsProvider()
    adapter = LangChainEmbeddingsAdapter(provider)
    chroma = ChromaService(
        persist_directory=str(tmp_path / "vector_db"),
        embedding_function=adapter,
        embeddings_provider=provider,
        collection_strategy="per_embedding_provider",
    )
    registry = DocumentRegistry(str(tmp_path / "registry.json"))
    service = DocumentReindexService(
        chroma_service=chroma,
        registry=registry,
        embeddings_provider=provider,
        chunk_size=200,
        chunk_overlap=20,
    )
    return service, registry, chroma


def register_text_document(
    tmp_path: Path,
    registry: DocumentRegistry,
    *,
    document_id: str = "doc-1",
    filename: str = "sample.txt",
    content: str = "registry json metadata alpha",
) -> str:
    stored_path = tmp_path / filename
    stored_path.write_text(content, encoding="utf-8")
    registry.add(
        {
            "id": document_id,
            "filename": filename,
            "stored_path": str(stored_path),
            "total_chunks": 0,
        }
    )
    return str(stored_path)


def test_build_reindex_plan_lists_registered_documents(tmp_path):
    service, registry, _chroma = build_service(tmp_path)
    register_text_document(tmp_path, registry)

    plan = service.build_reindex_plan()

    assert plan["dry_run"] is True
    assert plan["active_provider"] == "local_hash"
    assert plan["summary"]["total"] == 1
    assert plan["summary"]["would_reindex"] == 1
    assert plan["documents"][0]["status"] == "would_reindex"


def test_build_reindex_plan_reports_missing_file(tmp_path):
    service, registry, _chroma = build_service(tmp_path)
    registry.add(
        {
            "id": "doc-missing",
            "filename": "missing.txt",
            "stored_path": str(tmp_path / "missing.txt"),
            "total_chunks": 1,
        }
    )

    plan = service.build_reindex_plan()

    assert plan["summary"]["missing_file"] == 1
    assert plan["documents"][0]["status"] == "missing_file"
    assert "missing" in plan["documents"][0]["reason"].lower()


def test_build_reindex_plan_skips_already_indexed(tmp_path):
    service, registry, chroma = build_service(tmp_path)
    register_text_document(tmp_path, registry)
    chroma.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="existing", metadata={"source": "sample.txt"})],
    )

    plan = service.build_reindex_plan()

    assert plan["summary"]["already_indexed"] == 1
    assert plan["documents"][0]["status"] == "already_indexed"


def test_run_reindex_indexes_document(tmp_path):
    service, registry, chroma = build_service(tmp_path)
    register_text_document(tmp_path, registry)

    result = service.run_reindex_plan()

    assert result["dry_run"] is False
    assert result["summary"]["reindexed"] == 1
    assert chroma.list_document_ids_with_vector_counts()["doc-1"] > 0
    stored = chroma.list_documents(document_ids=["doc-1"])
    assert stored[0].metadata["embedding_provider"] == "local_hash"
    assert stored[0].metadata["collection_name"] == chroma.collection_name
    updated = registry.get("doc-1")
    assert updated["total_chunks"] > 0


def test_force_reindex_replaces_active_collection_vectors(tmp_path):
    service, registry, chroma = build_service(tmp_path)
    stored_path = register_text_document(tmp_path, registry, content="first version content")
    chroma.add_documents(
        document_id="doc-1",
        docs=[Document(page_content="stale chunk", metadata={"source": "sample.txt"})],
    )

    Path(stored_path).write_text(
        "second version with registry json metadata",
        encoding="utf-8",
    )

    result = service.run_reindex_plan(force=True)

    assert result["summary"]["reindexed"] == 1
    docs = chroma.list_documents(document_ids=["doc-1"])
    assert any("registry json" in doc.page_content for doc in docs)


def test_reindex_does_not_delete_other_provider_collections(tmp_path):
    service, registry, chroma = build_service(tmp_path)
    register_text_document(tmp_path, registry)
    legacy_store = chroma._vector_store_for("rag_chat")
    legacy_store.add_documents(
        documents=[
            Document(
                page_content="legacy only",
                metadata={"document_id": "doc-1", "chunk_id": "legacy-1", "source": "sample.txt"},
            )
        ],
        ids=["legacy-1"],
    )

    service.run_reindex_plan()

    assert chroma._document_counts_for_collection("rag_chat")["doc-1"] == 1
    assert chroma.list_document_ids_with_vector_counts()["doc-1"] > 0


def test_run_reindex_increments_metrics(tmp_path):
    service, registry, _chroma = build_service(tmp_path)
    register_text_document(tmp_path, registry)

    service.run_reindex_plan()
    metrics = get_local_metrics().snapshot()["counters"]

    assert metrics.get("documents.reindex.run", 0) >= 1
    assert metrics.get("documents.reindex.completed", 0) >= 1


def test_build_reindex_plan_reports_unsupported_extension(tmp_path):
    service, registry, _chroma = build_service(tmp_path)
    stored_path = tmp_path / "sample.csv"
    stored_path.write_text("a,b,c", encoding="utf-8")
    registry.add(
        {
            "id": "doc-csv",
            "filename": "sample.csv",
            "stored_path": str(stored_path),
            "total_chunks": 0,
        }
    )

    plan = service.build_reindex_plan()

    assert plan["summary"]["unsupported"] == 1
    assert plan["documents"][0]["status"] == "unsupported"
