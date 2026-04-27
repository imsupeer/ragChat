import os
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from core.config import Settings, get_settings
from core.dependencies import (
    get_chroma_service,
    get_document_registry,
    get_sqlite_store,
    get_upload_queue_service,
)
from ingestion.loaders import SUPPORTED_EXTENSIONS
from ingestion.processor import save_uploaded_file
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.sqlite_store import SQLiteStore
from services.upload_queue import UploadQueueService

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

    file_bytes = await file.read()

    stored_path = save_uploaded_file(
        file_bytes=file_bytes,
        filename=file.filename,
        target_dir=settings.documents_directory,
    )

    job = sqlite_store.create_upload_job(
        filename=file.filename,
        file_size=len(file_bytes),
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


@router.get("")
def list_documents(
    registry: DocumentRegistry = Depends(get_document_registry),
):
    return {"documents": registry.list_all()}


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    chroma_service: ChromaService = Depends(get_chroma_service),
    registry: DocumentRegistry = Depends(get_document_registry),
):
    entry = registry.get(document_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Document not found.")

    chroma_service.delete_document(document_id)

    stored_path = entry.get("stored_path")
    if stored_path and os.path.exists(stored_path):
        os.remove(stored_path)

    registry.remove(document_id)

    return {"message": "Document removed successfully.", "document_id": document_id}
