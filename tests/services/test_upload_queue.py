from pathlib import Path

import pytest

from ingestion.processor import save_uploaded_file
from services.sqlite_store import SQLiteStore
from services.upload_queue import (
    UploadJobNotFoundError,
    UploadJobNotRetryableError,
    UploadQueueService,
)


class FakeChromaService:
    def __init__(self) -> None:
        self.added: list[tuple[str, int]] = []
        self.deleted: list[str] = []

    def add_documents(self, document_id: str, docs) -> None:
        self.added.append((document_id, len(docs)))

    def delete_document(self, document_id: str) -> None:
        self.deleted.append(document_id)


class FakeRegistry:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.entries: list[dict] = []
        self.should_fail = should_fail

    def add(self, entry: dict) -> None:
        if self.should_fail:
            raise RuntimeError("registry write failed")
        self.entries.append(entry)


def build_queue(
    tmp_path: Path,
    *,
    chroma: FakeChromaService | None = None,
    registry: FakeRegistry | None = None,
) -> tuple[UploadQueueService, SQLiteStore, FakeChromaService, FakeRegistry]:
    sqlite_store = SQLiteStore(str(tmp_path / "app.db"))
    chroma_service = chroma or FakeChromaService()
    document_registry = registry or FakeRegistry()
    queue = UploadQueueService(
        chroma_service=chroma_service,
        registry=document_registry,
        sqlite_store=sqlite_store,
        chunk_size=800,
        chunk_overlap=200,
        autostart=False,
    )
    return queue, sqlite_store, chroma_service, document_registry


def create_job(
    sqlite_store: SQLiteStore,
    *,
    filename: str,
    stored_path: str,
    status: str = "queued",
) -> dict:
    return sqlite_store.create_upload_job(
        filename=filename,
        file_size=Path(stored_path).stat().st_size,
        stored_path=stored_path,
    )


def test_recover_pending_jobs_requeues_queued_job(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(
        b"Registry entries live in registry.json",
        "sample.txt",
        str(docs_dir),
    )

    queue, sqlite_store, _, _ = build_queue(tmp_path)
    job = create_job(sqlite_store, filename="sample.txt", stored_path=stored_path)

    recovered = queue.recover_pending_jobs()

    assert recovered == 1
    queue._process_job(
        {
            "job_id": job["id"],
            "filename": job["filename"],
            "stored_path": job["stored_path"],
        }
    )

    updated = sqlite_store.get_upload_job(job["id"])
    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["document_id"] is not None


def test_recover_pending_jobs_resets_processing_job(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(
        b"Registry entries live in registry.json",
        "sample.txt",
        str(docs_dir),
    )

    queue, sqlite_store, _, _ = build_queue(tmp_path)
    job = create_job(sqlite_store, filename="sample.txt", stored_path=stored_path)
    sqlite_store.update_upload_job(job["id"], status="processing", index_progress=45)

    recovered = queue.recover_pending_jobs()

    assert recovered == 1
    updated = sqlite_store.get_upload_job(job["id"])
    assert updated is not None
    assert updated["status"] == "queued"
    assert updated["index_progress"] == 0


def test_recover_pending_jobs_marks_missing_file_as_failed(tmp_path: Path):
    queue, sqlite_store, _, _ = build_queue(tmp_path)
    job = sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=10,
        stored_path=str(tmp_path / "missing.txt"),
    )

    recovered = queue.recover_pending_jobs()

    assert recovered == 0
    updated = sqlite_store.get_upload_job(job["id"])
    assert updated is not None
    assert updated["status"] == "failed"
    assert "no longer exists" in (updated["error"] or "")


def test_registry_failure_triggers_chroma_cleanup(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(
        b"Registry entries live in registry.json",
        "sample.txt",
        str(docs_dir),
    )

    queue, sqlite_store, chroma_service, _ = build_queue(
        tmp_path,
        registry=FakeRegistry(should_fail=True),
    )
    job = create_job(sqlite_store, filename="sample.txt", stored_path=stored_path)

    queue._process_job(
        {
            "job_id": job["id"],
            "filename": job["filename"],
            "stored_path": job["stored_path"],
        }
    )

    updated = sqlite_store.get_upload_job(job["id"])
    assert updated is not None
    assert updated["status"] == "failed"
    assert "registry write failed" in (updated["error"] or "")
    assert len(chroma_service.added) == 1
    assert chroma_service.deleted == [chroma_service.added[0][0]]


def test_retry_job_reuses_existing_file_without_duplicating(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(
        b"Registry entries live in registry.json",
        "sample.txt",
        str(docs_dir),
    )

    queue, sqlite_store, _, registry = build_queue(tmp_path)
    job = create_job(sqlite_store, filename="sample.txt", stored_path=stored_path)
    sqlite_store.update_upload_job(
        job["id"],
        status="failed",
        error="registry write failed",
    )

    retried = queue.retry_job(job["id"])

    assert retried["status"] == "queued"
    queue._process_job(
        {
            "job_id": job["id"],
            "filename": job["filename"],
            "stored_path": job["stored_path"],
        }
    )

    updated = sqlite_store.get_upload_job(job["id"])
    assert updated is not None
    assert updated["status"] == "completed"
    assert len(registry.entries) == 1
    assert registry.entries[0]["stored_path"] == stored_path
    assert len(list(docs_dir.glob("*"))) == 1


def test_shutdown_stops_worker_thread(tmp_path: Path):
    queue, sqlite_store, _, _ = build_queue(tmp_path)
    queue._worker_thread.start()

    assert queue._worker_thread.is_alive()

    queue.shutdown(timeout_seconds=1.0)

    assert not queue._worker_thread.is_alive()
    assert queue._stop_event.is_set()


def test_shutdown_resets_processing_job_to_queued(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(
        b"Registry entries live in registry.json",
        "sample.txt",
        str(docs_dir),
    )

    queue, sqlite_store, _, _ = build_queue(tmp_path)
    job = create_job(sqlite_store, filename="sample.txt", stored_path=stored_path)
    sqlite_store.update_upload_job(job["id"], status="processing", index_progress=45)
    queue._current_job_id = job["id"]
    queue._active_job_ids.add(job["id"])
    queue._worker_thread.start()

    queue.shutdown(timeout_seconds=1.0)

    updated = sqlite_store.get_upload_job(job["id"])
    assert updated is not None
    assert updated["status"] == "queued"
    assert updated["index_progress"] == 0
    assert queue._active_job_ids == set()


def test_retry_job_rejects_completed_job(tmp_path: Path):
    queue, sqlite_store, _, _ = build_queue(tmp_path)
    job = sqlite_store.create_upload_job(
        filename="done.txt",
        file_size=4,
        stored_path=str(tmp_path / "done.txt"),
    )
    sqlite_store.update_upload_job(job["id"], status="completed", index_progress=100)

    with pytest.raises(UploadJobNotRetryableError):
        queue.retry_job(job["id"])


def test_retry_job_raises_not_found(tmp_path: Path):
    queue, _, _, _ = build_queue(tmp_path)

    with pytest.raises(UploadJobNotFoundError):
        queue.retry_job("missing-job")


def test_retry_job_returns_processing_job_when_still_active(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(
        b"Registry entries live in registry.json",
        "sample.txt",
        str(docs_dir),
    )

    queue, sqlite_store, _, _ = build_queue(tmp_path)
    job = create_job(sqlite_store, filename="sample.txt", stored_path=stored_path)
    sqlite_store.update_upload_job(job["id"], status="processing", index_progress=45)
    queue._active_job_ids.add(job["id"])

    retried = queue.retry_job(job["id"])

    assert retried["status"] == "processing"
    assert retried["index_progress"] == 45


def test_enqueue_skips_duplicate_active_job(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(
        b"Registry entries live in registry.json",
        "sample.txt",
        str(docs_dir),
    )

    queue, sqlite_store, chroma_service, _ = build_queue(tmp_path)
    job = create_job(sqlite_store, filename="sample.txt", stored_path=stored_path)
    payload = {
        "job_id": job["id"],
        "filename": job["filename"],
        "stored_path": job["stored_path"],
    }

    queue.enqueue(payload)
    queue.enqueue(payload)

    assert queue._queue.qsize() == 1

    queue._process_job(queue._queue.get())
    assert len(chroma_service.added) == 1


def test_permanent_failure_removes_raw_file(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(b"", "empty.txt", str(docs_dir))

    queue, sqlite_store, _, _ = build_queue(tmp_path)
    job = create_job(sqlite_store, filename="empty.txt", stored_path=stored_path)

    queue._process_job(
        {
            "job_id": job["id"],
            "filename": job["filename"],
            "stored_path": job["stored_path"],
        }
    )

    updated = sqlite_store.get_upload_job(job["id"])
    assert updated is not None
    assert updated["status"] == "failed"
    assert not Path(stored_path).exists()
    assert list(docs_dir.glob("*")) == []


def test_recoverable_failure_keeps_raw_file_for_retry(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stored_path = save_uploaded_file(
        b"Registry entries live in registry.json",
        "sample.txt",
        str(docs_dir),
    )

    queue, sqlite_store, _, _ = build_queue(
        tmp_path,
        registry=FakeRegistry(should_fail=True),
    )
    job = create_job(sqlite_store, filename="sample.txt", stored_path=stored_path)

    queue._process_job(
        {
            "job_id": job["id"],
            "filename": job["filename"],
            "stored_path": job["stored_path"],
        }
    )

    assert Path(stored_path).exists()
    updated = sqlite_store.get_upload_job(job["id"])
    assert updated is not None
    assert updated["status"] == "failed"

    retried = queue.retry_job(job["id"])
    assert retried["status"] == "queued"
