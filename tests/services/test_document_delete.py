import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from services.document_delete import (
    DELETE_INCOMPLETE_MESSAGE,
    DocumentDeleteError,
    DocumentDeleteService,
    DocumentNotFoundError,
)
from services.document_registry import DocumentRegistry
from services.sqlite_store import SQLiteStore, SQLITE_BUSY_TIMEOUT_MS


class TrackingChromaService:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.fail = False

    def delete_document(self, document_id: str) -> None:
        if self.fail:
            raise RuntimeError("vector delete failed")
        self.deleted.append(document_id)


class FailingRegistry(DocumentRegistry):
    def __init__(self, registry_path: str) -> None:
        super().__init__(registry_path)
        self.fail_remove = False

    def remove(self, document_id: str):
        if self.fail_remove:
            raise RuntimeError("registry write failed")
        return super().remove(document_id)


def test_document_delete_success_removes_all_stores(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    stored_path = tmp_path / "docs" / "sample.txt"
    stored_path.parent.mkdir()
    stored_path.write_text("content", encoding="utf-8")

    registry = DocumentRegistry(str(registry_path))
    registry.add(
        {
            "id": "doc-1",
            "filename": "sample.txt",
            "stored_path": str(stored_path),
            "total_chunks": 1,
        }
    )

    sqlite_store = SQLiteStore(str(tmp_path / "app.db"))
    job = sqlite_store.create_upload_job(
        filename="sample.txt",
        file_size=7,
        stored_path=str(stored_path),
    )
    sqlite_store.update_upload_job(job["id"], status="completed", document_id="doc-1")

    chroma = TrackingChromaService()
    service = DocumentDeleteService(
        chroma_service=chroma,
        registry=registry,
        sqlite_store=sqlite_store,
    )

    result = service.delete_document("doc-1")

    assert result["document_id"] == "doc-1"
    assert chroma.deleted == ["doc-1"]
    assert not stored_path.exists()
    assert registry.get("doc-1") is None
    updated_job = sqlite_store.get_upload_job(job["id"])
    assert updated_job["document_id"] is None


def test_document_delete_chroma_failure_keeps_registry(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    registry = DocumentRegistry(str(registry_path))
    registry.add(
        {
            "id": "doc-1",
            "filename": "sample.txt",
            "stored_path": str(tmp_path / "sample.txt"),
            "total_chunks": 1,
        }
    )

    chroma = TrackingChromaService()
    chroma.fail = True
    sqlite_store = SQLiteStore(str(tmp_path / "app.db"))
    service = DocumentDeleteService(
        chroma_service=chroma,
        registry=registry,
        sqlite_store=sqlite_store,
    )

    with pytest.raises(DocumentDeleteError):
        service.delete_document("doc-1")

    assert registry.get("doc-1") is not None
    assert sqlite_store.list_upload_jobs() == []


def test_document_delete_filesystem_failure_keeps_registry(tmp_path: Path, monkeypatch):
    registry_path = tmp_path / "registry.json"
    stored_path = tmp_path / "sample.txt"
    stored_path.write_text("content", encoding="utf-8")

    registry = DocumentRegistry(str(registry_path))
    registry.add(
        {
            "id": "doc-1",
            "filename": "sample.txt",
            "stored_path": str(stored_path),
            "total_chunks": 1,
        }
    )

    chroma = TrackingChromaService()
    sqlite_store = SQLiteStore(str(tmp_path / "app.db"))
    service = DocumentDeleteService(
        chroma_service=chroma,
        registry=registry,
        sqlite_store=sqlite_store,
    )

    def failing_remove(path: str) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr("services.document_delete.os.remove", failing_remove)

    with pytest.raises(DocumentDeleteError) as exc_info:
        service.delete_document("doc-1")

    assert exc_info.value.safe_detail == DELETE_INCOMPLETE_MESSAGE
    assert registry.get("doc-1") is not None
    assert chroma.deleted == ["doc-1"]


def test_document_delete_registry_failure_after_chroma(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    stored_path = tmp_path / "sample.txt"
    stored_path.write_text("content", encoding="utf-8")

    registry = FailingRegistry(str(registry_path))
    registry.add(
        {
            "id": "doc-1",
            "filename": "sample.txt",
            "stored_path": str(stored_path),
            "total_chunks": 1,
        }
    )
    registry.fail_remove = True

    chroma = TrackingChromaService()
    sqlite_store = SQLiteStore(str(tmp_path / "app.db"))
    sqlite_store.update_upload_job(
        sqlite_store.create_upload_job("sample.txt", 7, str(stored_path))["id"],
        status="completed",
        document_id="doc-1",
    )

    service = DocumentDeleteService(
        chroma_service=chroma,
        registry=registry,
        sqlite_store=sqlite_store,
    )

    with pytest.raises(DocumentDeleteError):
        service.delete_document("doc-1")

    assert registry.get("doc-1") is not None
    job = sqlite_store.list_upload_jobs()[0]
    assert job["document_id"] == "doc-1"


def test_document_delete_missing_document_raises_not_found(tmp_path: Path):
    service = DocumentDeleteService(
        chroma_service=TrackingChromaService(),
        registry=DocumentRegistry(str(tmp_path / "registry.json")),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
    )

    with pytest.raises(DocumentNotFoundError):
        service.delete_document("missing-doc")
