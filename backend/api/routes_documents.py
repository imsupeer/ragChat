from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from core.config import Settings, get_settings
from core.dependencies import (
    get_document_delete_service,
    get_document_registry,
    get_settings,
    get_sqlite_store,
    get_upload_queue_service,
)
from core.observability import log_api_exception, safe_ingestion_error_message
from ingestion.loaders import SUPPORTED_EXTENSIONS
from ingestion.processor import UploadTooLargeError, stream_upload_to_disk
from services.metrics import get_local_metrics
from services.document_delete import (
    DocumentDeleteError,
    DocumentDeleteService,
    DocumentNotFoundError,
)
from services.document_registry import DocumentRegistry
from services.sqlite_store import SQLiteStore
from services.upload_queue import (
    UploadJobNotFoundError,
    UploadJobNotRetryableError,
    UploadQueueService,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
    upload_queue: UploadQueueService = Depends(get_upload_queue_service),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix or 'unknown'}.",
        )

    get_local_metrics().increment("upload.attempt")

    try:
        stored_path, file_size = await stream_upload_to_disk(
            file,
            filename=file.filename,
            target_dir=settings.documents_directory,
            max_bytes=settings.max_upload_bytes,
            chunk_bytes=settings.upload_read_chunk_bytes,
        )
    except UploadTooLargeError as exc:
        get_local_metrics().increment("upload.rejected_oversized")
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds maximum size of {exc.max_bytes} bytes.",
        ) from exc
    except ValueError as exc:
        get_local_metrics().increment("upload.failed")
        raise HTTPException(
            status_code=400,
            detail=safe_ingestion_error_message(exc),
        ) from exc
    except Exception as exc:
        log_api_exception("documents.upload", exc)
        get_local_metrics().increment("upload.failed_write")
        raise HTTPException(
            status_code=500,
            detail=safe_ingestion_error_message(exc),
        ) from exc

    get_local_metrics().increment("upload.accepted")

    job = sqlite_store.create_upload_job(
        filename=file.filename,
        file_size=file_size,
        stored_path=stored_path,
    )

    upload_queue.enqueue(
        {
            "job_id": job["id"],
            "filename": file.filename,
            "stored_path": stored_path,
        }
    )

    return {
        "message": "Document uploaded successfully and queued for indexing.",
        "job": job,
    }


@router.get("/jobs")
def list_jobs(sqlite_store: SQLiteStore = Depends(get_sqlite_store)):
    return {"jobs": sqlite_store.list_upload_jobs()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, sqlite_store: SQLiteStore = Depends(get_sqlite_store)):
    job = sqlite_store.get_upload_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job": job}


@router.post("/jobs/{job_id}/retry")
def retry_upload_job(
    job_id: str,
    upload_queue: UploadQueueService = Depends(get_upload_queue_service),
):
    try:
        job = upload_queue.retry_job(job_id)
    except UploadJobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found.")
    except UploadJobNotRetryableError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "message": "Upload job queued for retry.",
        "job": job,
    }


@router.get("")
def list_documents(
    registry: DocumentRegistry = Depends(get_document_registry),
):
    return {"documents": registry.list_all()}


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    delete_service: DocumentDeleteService = Depends(get_document_delete_service),
):
    try:
        return delete_service.delete_document(document_id)
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found.")
    except DocumentDeleteError as exc:
        raise HTTPException(status_code=500, detail=exc.safe_detail) from exc
