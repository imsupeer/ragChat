import queue
import threading
import uuid
from ingestion.processor import process_document, build_registry_entry
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.sqlite_store import SQLiteStore


class UploadQueueService:
    def __init__(
        self,
        chroma_service: ChromaService,
        registry: DocumentRegistry,
        sqlite_store: SQLiteStore,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self.chroma_service = chroma_service
        self.registry = registry
        self.sqlite_store = sqlite_store
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._queue: "queue.Queue[dict]" = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def enqueue(self, job: dict) -> None:
        self._queue.put(job)

    def _worker(self) -> None:
        while True:
            job = self._queue.get()
            job_id = job["job_id"]

            try:
                self.sqlite_store.update_upload_job(
                    job_id,
                    status="processing",
                    index_progress=5,
                )

                chunks = process_document(
                    file_path=job["stored_path"],
                    original_filename=job["filename"],
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                )

                self.sqlite_store.update_upload_job(job_id, index_progress=45)

                document_id = str(uuid.uuid4())
                self.chroma_service.add_documents(document_id=document_id, docs=chunks)

                self.sqlite_store.update_upload_job(job_id, index_progress=80)

                entry = build_registry_entry(
                    document_id=document_id,
                    original_filename=job["filename"],
                    stored_path=job["stored_path"],
                    total_chunks=len(chunks),
                )
                self.registry.add(entry)

                self.sqlite_store.update_upload_job(
                    job_id,
                    status="completed",
                    index_progress=100,
                    document_id=document_id,
                )

            except Exception as exc:
                self.sqlite_store.update_upload_job(
                    job_id,
                    status="failed",
                    error=str(exc),
                )
            finally:
                self._queue.task_done()
