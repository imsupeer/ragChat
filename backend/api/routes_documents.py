import os
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from core.config import Settings, get_settings
from core.dependencies import get_chroma_service, get_document_registry
from ingestion.processor import (
    save_uploaded_file,
    process_document,
    build_registry_entry,
)
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    chroma_service: ChromaService = Depends(get_chroma_service),
    registry: DocumentRegistry = Depends(get_document_registry),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    file_bytes = await file.read()
    stored_path = save_uploaded_file(
        file_bytes, file.filename, settings.documents_directory
    )

    try:
        chunks = process_document(
            file_path=stored_path,
            original_filename=file.filename,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = str(uuid.uuid4())
    chroma_service.add_documents(document_id=document_id, docs=chunks)

    entry = build_registry_entry(
        document_id=document_id,
        original_filename=file.filename,
        stored_path=stored_path,
        total_chunks=len(chunks),
    )
    registry.add(entry)

    return {
        "message": "Document uploaded and indexed successfully.",
        "document": entry,
    }


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
    entry = registry.remove(document_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Document not found.")

    chroma_service.delete_document(document_id)

    stored_path = entry.get("stored_path")
    if stored_path and os.path.exists(stored_path):
        os.remove(stored_path)

    return {"message": "Document removed successfully.", "document_id": document_id}
