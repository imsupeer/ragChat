import logging
import os
from typing import Any

from core.observability import log_structured
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.sqlite_store import SQLiteStore

logger = logging.getLogger("uvicorn.error")

DELETE_FAILED_MESSAGE = "Document delete failed before completion."
DELETE_INCOMPLETE_MESSAGE = (
    "Failed to delete document cleanly. The workspace may need reconciliation."
)


class DocumentNotFoundError(Exception):
    pass


class DocumentDeleteError(Exception):
    def __init__(self, safe_detail: str) -> None:
        super().__init__(safe_detail)
        self.safe_detail = safe_detail


class DocumentDeleteService:
    def __init__(
        self,
        chroma_service: ChromaService,
        registry: DocumentRegistry,
        sqlite_store: SQLiteStore,
    ) -> None:
        self.chroma_service = chroma_service
        self.registry = registry
        self.sqlite_store = sqlite_store

    def delete_document(self, document_id: str) -> dict[str, Any]:
        entry = self.registry.get(document_id)
        if not entry:
            raise DocumentNotFoundError(document_id)

        stored_path = entry.get("stored_path")

        try:
            self.chroma_service.delete_document(document_id)
        except Exception as exc:
            logger.exception(
                "Chroma delete failed for document_id=%s",
                document_id,
            )
            log_structured(
                "document.delete.failed",
                document_id,
                {
                    "stage": "chroma",
                    "document_id": document_id,
                    "error": str(exc),
                },
            )
            raise DocumentDeleteError(DELETE_FAILED_MESSAGE) from exc

        if stored_path and os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except OSError as exc:
                logger.exception(
                    "Filesystem delete failed after Chroma delete document_id=%s",
                    document_id,
                )
                log_structured(
                    "document.delete.partial",
                    document_id,
                    {
                        "stage": "filesystem",
                        "document_id": document_id,
                        "error": str(exc),
                    },
                )
                raise DocumentDeleteError(DELETE_INCOMPLETE_MESSAGE) from exc

        try:
            self.registry.remove(document_id)
        except Exception as exc:
            logger.exception(
                "Registry remove failed after Chroma delete document_id=%s",
                document_id,
            )
            log_structured(
                "document.delete.partial",
                document_id,
                {
                    "stage": "registry",
                    "document_id": document_id,
                    "error": str(exc),
                },
            )
            raise DocumentDeleteError(DELETE_INCOMPLETE_MESSAGE) from exc

        self.sqlite_store.clear_upload_job_document_reference(document_id)

        return {
            "message": "Document removed successfully.",
            "document_id": document_id,
        }
