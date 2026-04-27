from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_documents import router as documents_router
from core.config import Settings
from core.dependencies import (
    get_chroma_service,
    get_document_registry,
    get_settings,
    get_sqlite_store,
    get_upload_queue_service,
)


class FakeSQLiteStore:
    def __init__(self) -> None:
        self.jobs = []

    def create_upload_job(self, filename: str, file_size: int, stored_path: str):
        job = {
            "id": "job-1",
            "filename": filename,
            "file_size": file_size,
            "stored_path": stored_path,
            "status": "queued",
            "upload_progress": 100,
            "index_progress": 0,
            "error": None,
            "document_id": None,
        }
        self.jobs.append(job)
        return job


class FakeUploadQueueService:
    def __init__(self) -> None:
        self.enqueued = []

    def enqueue(self, job: dict) -> None:
        self.enqueued.append(job)


class FakeRegistry:
    def __init__(self) -> None:
        self.removed = []

    def get(self, document_id: str):
        return {
            "id": document_id,
            "filename": "sample.txt",
            "stored_path": None,
            "total_chunks": 1,
        }

    def remove(self, document_id: str):
        self.removed.append(document_id)


class FailingChromaService:
    def delete_document(self, document_id: str) -> None:
        raise RuntimeError("vector delete failed")


def test_documents_upload_works_with_sample_file(tmp_path: Path):
    app = FastAPI()
    app.include_router(documents_router)

    fake_sqlite_store = FakeSQLiteStore()
    fake_upload_queue = FakeUploadQueueService()
    settings = Settings(
        documents_directory=str(tmp_path / "docs"),
        sqlite_path=str(tmp_path / "app.db"),
        registry_path=str(tmp_path / "registry.json"),
    )

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store
    app.dependency_overrides[get_upload_queue_service] = lambda: fake_upload_queue

    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            files={"file": ("sample.txt", b"Registry entries live in registry.json", "text/plain")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["id"] == "job-1"
    assert fake_upload_queue.enqueued[0]["job_id"] == "job-1"

    stored_path = Path(fake_sqlite_store.jobs[0]["stored_path"])
    assert stored_path.exists()
    assert stored_path.parent == tmp_path / "docs"


def test_documents_upload_rejects_unsupported_files_before_saving(tmp_path: Path):
    app = FastAPI()
    app.include_router(documents_router)

    fake_sqlite_store = FakeSQLiteStore()
    fake_upload_queue = FakeUploadQueueService()
    settings = Settings(
        documents_directory=str(tmp_path / "docs"),
        sqlite_path=str(tmp_path / "app.db"),
        registry_path=str(tmp_path / "registry.json"),
    )

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store
    app.dependency_overrides[get_upload_queue_service] = lambda: fake_upload_queue

    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            files={"file": ("sample.exe", b"not a supported document", "application/octet-stream")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type: .exe."
    assert fake_sqlite_store.jobs == []
    assert fake_upload_queue.enqueued == []
    assert not (tmp_path / "docs").exists()


def test_document_delete_keeps_registry_entry_when_vector_delete_fails():
    app = FastAPI()
    app.include_router(documents_router)

    fake_registry = FakeRegistry()
    app.dependency_overrides[get_document_registry] = lambda: fake_registry
    app.dependency_overrides[get_chroma_service] = lambda: FailingChromaService()

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.delete("/documents/doc-1")

    assert response.status_code == 500
    assert fake_registry.removed == []
