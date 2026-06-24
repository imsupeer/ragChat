import logging
import os
import queue
import threading
import uuid

from ingestion.processor import build_registry_entry, process_document, remove_stored_file
from core.observability import log_api_exception, safe_ingestion_error_message
from services.metrics import get_local_metrics
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.sqlite_store import SQLiteStore

logger = logging.getLogger("uvicorn.error")

RETRYABLE_STATUSES = frozenset({"failed", "queued", "processing"})
PERMANENT_FAILURE_MARKERS = (
    "Document produced no indexable chunks",
    "Unsupported file type",
    "Text file could not be decoded",
    "Uploaded file is empty",
)
CHROMA_INDEX_BATCH_SIZE = 32
WORKER_POLL_TIMEOUT_SECONDS = 0.5


class UploadJobNotFoundError(Exception):
    pass


class UploadJobNotRetryableError(Exception):
    pass


class UploadQueueService:
    def __init__(
        self,
        chroma_service: ChromaService,
        registry: DocumentRegistry,
        sqlite_store: SQLiteStore,
        chunk_size: int,
        chunk_overlap: int,
        *,
        cleanup_failed_upload_files: bool = True,
        autostart: bool = True,
    ) -> None:
        self.chroma_service = chroma_service
        self.registry = registry
        self.sqlite_store = sqlite_store
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.cleanup_failed_upload_files = cleanup_failed_upload_files

        self._queue: "queue.Queue[dict]" = queue.Queue()
        self._lock = threading.Lock()
        self._active_job_ids: set[str] = set()
        self._stop_event = threading.Event()
        self._current_job_id: str | None = None
        self._worker_thread = threading.Thread(
            target=self._worker,
            name="upload-queue-worker",
            daemon=True,
        )

        if autostart:
            self._worker_thread.start()
            self.recover_pending_jobs()

    @property
    def is_worker_alive(self) -> bool:
        return self._worker_thread.is_alive()

    def recover_pending_jobs(self) -> int:
        recovered = 0

        for job in self.sqlite_store.list_pending_upload_jobs():
            if not self._prepare_job_for_recovery(job):
                continue

            payload = self._job_payload_from_record(job)
            if self._register_active_job(payload["job_id"]):
                self._queue.put(payload)
                recovered += 1

        if recovered:
            logger.info("Recovered %s pending upload job(s) on startup.", recovered)

        return recovered

    def enqueue(self, job: dict) -> None:
        if self._register_active_job(job["job_id"]):
            self._queue.put(job)

    def shutdown(self, timeout_seconds: float = 5.0) -> None:
        if not self._worker_thread.is_alive():
            return

        logger.info("Upload queue shutdown started.")
        self._stop_event.set()
        self._worker_thread.join(timeout=timeout_seconds)
        self._release_interrupted_jobs()

        if self._worker_thread.is_alive():
            logger.warning(
                "Upload queue worker did not stop within %s seconds.",
                timeout_seconds,
            )
        else:
            logger.info("Upload queue shutdown finished.")

    def retry_job(self, job_id: str) -> dict:
        job = self.sqlite_store.get_upload_job(job_id)
        if not job:
            raise UploadJobNotFoundError(job_id)

        if job["status"] == "completed":
            raise UploadJobNotRetryableError("Completed upload jobs cannot be retried.")

        if job["status"] not in RETRYABLE_STATUSES:
            raise UploadJobNotRetryableError(
                f"Upload job in status '{job['status']}' cannot be retried."
            )

        with self._lock:
            if job_id in self._active_job_ids:
                if job["status"] == "processing":
                    refreshed = self.sqlite_store.get_upload_job(job_id)
                    if refreshed is not None:
                        return refreshed
                raise UploadJobNotRetryableError(
                    "Upload job is already queued or processing."
                )

        if not self._prepare_job_for_recovery(job):
            updated = self.sqlite_store.get_upload_job(job_id)
            message = (updated or {}).get("error") or "Upload job cannot be recovered."
            raise UploadJobNotRetryableError(message)

        self.sqlite_store.update_upload_job(
            job_id,
            status="queued",
            index_progress=0,
            error="",
        )

        refreshed = self.sqlite_store.get_upload_job(job_id)
        if refreshed is None:
            raise UploadJobNotFoundError(job_id)

        payload = self._job_payload_from_record(refreshed)
        if not self._register_active_job(payload["job_id"]):
            raise UploadJobNotRetryableError(
                "Upload job is already queued or processing."
            )

        self._queue.put(payload)
        get_local_metrics().increment("upload.retry.attempted")
        updated_job = self.sqlite_store.get_upload_job(job_id)
        if updated_job is None:
            raise UploadJobNotFoundError(job_id)
        return updated_job

    def _register_active_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._active_job_ids:
                return False
            self._active_job_ids.add(job_id)
        return True

    def _prepare_job_for_recovery(self, job: dict) -> bool:
        job_id = job["id"]
        stored_path = job.get("stored_path")
        filename = job.get("filename")

        if not stored_path or not filename:
            self.sqlite_store.update_upload_job(
                job_id,
                status="failed",
                error="Upload job is missing file metadata and cannot be recovered.",
            )
            return False

        if not os.path.exists(stored_path):
            self.sqlite_store.update_upload_job(
                job_id,
                status="failed",
                error=(
                    "Upload file no longer exists on disk; "
                    "re-upload the document to retry indexing."
                ),
            )
            return False

        if job["status"] == "processing":
            self.sqlite_store.update_upload_job(
                job_id,
                status="queued",
                index_progress=0,
                error="",
            )

        return True

    def _job_payload_from_record(self, job: dict) -> dict:
        return {
            "job_id": job["id"],
            "filename": job["filename"],
            "stored_path": job["stored_path"],
        }

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._queue.get(timeout=WORKER_POLL_TIMEOUT_SECONDS)
            except queue.Empty:
                continue

            try:
                self._process_job(job)
            finally:
                self._queue.task_done()

        logger.info("Upload queue worker stopped.")

    def _release_interrupted_jobs(self) -> None:
        current_job_id = self._current_job_id
        if current_job_id:
            self.sqlite_store.update_upload_job(
                current_job_id,
                status="queued",
                index_progress=0,
                error="",
            )

        for job in self.sqlite_store.list_pending_upload_jobs():
            if job["status"] == "processing":
                self.sqlite_store.update_upload_job(
                    job["id"],
                    status="queued",
                    index_progress=0,
                    error="",
                )

        with self._lock:
            self._active_job_ids.clear()

    def _process_job(self, job: dict) -> None:
        job_id = job["job_id"]
        document_id = None
        stored_path = job.get("stored_path")
        self._current_job_id = job_id

        try:
            filename = job.get("filename")

            if not stored_path or not filename:
                self.sqlite_store.update_upload_job(
                    job_id,
                    status="failed",
                    error="Upload job is missing file metadata and cannot be indexed.",
                )
                return

            if not os.path.exists(stored_path):
                self.sqlite_store.update_upload_job(
                    job_id,
                    status="failed",
                    error=(
                        "Upload file no longer exists on disk; "
                        "re-upload the document to retry indexing."
                    ),
                )
                return

            self.sqlite_store.update_upload_job(
                job_id,
                status="processing",
                index_progress=5,
            )

            chunks = process_document(
                file_path=stored_path,
                original_filename=filename,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )

            self.sqlite_store.update_upload_job(job_id, index_progress=45)

            document_id = str(uuid.uuid4())
            total_chunks = len(chunks)
            if total_chunks == 0:
                raise ValueError("Document produced no indexable chunks.")

            for start in range(0, total_chunks, CHROMA_INDEX_BATCH_SIZE):
                if self._stop_event.is_set():
                    raise RuntimeError("Upload queue shutdown interrupted indexing.")

                batch = chunks[start : start + CHROMA_INDEX_BATCH_SIZE]
                self.chroma_service.add_documents(document_id=document_id, docs=batch)
                indexed = min(start + len(batch), total_chunks)
                progress = 45 + int((indexed / total_chunks) * 35)
                self.sqlite_store.update_upload_job(job_id, index_progress=progress)

            self.sqlite_store.update_upload_job(job_id, index_progress=80)

            entry = build_registry_entry(
                document_id=document_id,
                original_filename=filename,
                stored_path=stored_path,
                total_chunks=len(chunks),
            )
            self.registry.add(entry)

            self.sqlite_store.update_upload_job(
                job_id,
                status="completed",
                index_progress=100,
                document_id=document_id,
            )
            get_local_metrics().increment("indexing.completed")
        except Exception as exc:
            if document_id:
                self._rollback_vectors(document_id=document_id, job_id=job_id)
            log_api_exception(f"upload_queue.job.{job_id}", exc)
            safe_error = safe_ingestion_error_message(exc)
            self.sqlite_store.update_upload_job(
                job_id,
                status="failed",
                error=safe_error,
            )
            metrics = get_local_metrics()
            if self._is_permanent_indexing_failure(exc):
                metrics.increment("indexing.failed.permanent")
            else:
                metrics.increment("indexing.failed.recoverable")
            if (
                self.cleanup_failed_upload_files
                and stored_path
                and self._is_permanent_indexing_failure(exc)
            ):
                self._cleanup_failed_upload_file(stored_path, job_id)
        finally:
            self._current_job_id = None
            with self._lock:
                self._active_job_ids.discard(job_id)

    def _is_permanent_indexing_failure(self, exc: Exception) -> bool:
        if isinstance(exc, RuntimeError):
            return False

        message = str(exc)
        return any(marker in message for marker in PERMANENT_FAILURE_MARKERS)

    def _cleanup_failed_upload_file(self, stored_path: str, job_id: str) -> None:
        if remove_stored_file(stored_path):
            logger.info(
                "Removed raw upload file for permanently failed job %s.",
                job_id,
            )
        else:
            logger.warning(
                "Failed to remove raw upload file for permanently failed job %s.",
                job_id,
            )

    def _rollback_vectors(self, *, document_id: str, job_id: str) -> None:
        try:
            self.chroma_service.delete_document(document_id)
            logger.warning(
                "Rolled back Chroma vectors for failed upload job %s document_id=%s",
                job_id,
                document_id,
            )
        except Exception as cleanup_exc:
            logger.error(
                "Failed to roll back Chroma vectors for upload job %s document_id=%s: %s",
                job_id,
                document_id,
                cleanup_exc,
            )
