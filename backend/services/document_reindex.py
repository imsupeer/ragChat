from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from core.observability import log_structured, safe_ingestion_error_message
from ingestion.loaders import SUPPORTED_EXTENSIONS
from ingestion.processor import process_document
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.embeddings_provider import EmbeddingsProvider
from services.metrics import get_local_metrics
from services.upload_queue import CHROMA_INDEX_BATCH_SIZE

logger = logging.getLogger("uvicorn.error")

REINDEX_DRY_RUN_COMMAND = "python scripts/reindex_documents.py --dry-run"
REINDEX_RUN_COMMAND = "python scripts/reindex_documents.py --run"

STATUS_WOULD_REINDEX = "would_reindex"
STATUS_ALREADY_INDEXED = "already_indexed"
STATUS_MISSING_FILE = "missing_file"
STATUS_UNSUPPORTED = "unsupported"
STATUS_REINDEXED = "reindexed"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"


def build_reindex_guidance(
    *,
    collection_status: str,
    reindex_recommended: bool,
    registered_document_count: int = 0,
) -> dict[str, Any]:
    recommended = bool(reindex_recommended)
    if collection_status in {"mixed", "legacy"}:
        recommended = True
    elif collection_status == "empty" and registered_document_count > 0:
        recommended = True

    if not recommended:
        return {"recommended": False}

    return {
        "recommended": True,
        "dry_run_command": REINDEX_DRY_RUN_COMMAND,
        "run_command": REINDEX_RUN_COMMAND,
        "message": (
            "Reindex recommended for the active embeddings provider. "
            "Run a dry-run first, then reindex when ready."
        ),
    }


class DocumentReindexService:
    def __init__(
        self,
        *,
        chroma_service: ChromaService,
        registry: DocumentRegistry,
        embeddings_provider: EmbeddingsProvider,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self.chroma_service = chroma_service
        self.registry = registry
        self.embeddings_provider = embeddings_provider
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def build_reindex_plan(
        self,
        *,
        document_ids: list[str] | None = None,
        force: bool = False,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        get_local_metrics().increment("documents.reindex.plan")
        entries = self._select_entries(document_ids)
        provider_info = self.embeddings_provider.provider_info()
        collection_status = self.chroma_service.get_collection_status()
        active_counts = self.chroma_service.list_document_ids_with_vector_counts()

        documents: list[dict[str, Any]] = []
        summary = {
            "total": 0,
            "would_reindex": 0,
            "already_indexed": 0,
            "missing_file": 0,
            "unsupported": 0,
            "errors": 0,
        }

        for entry in entries:
            document_id = str(entry["id"])
            filename = str(entry.get("filename") or document_id)
            stored_path = entry.get("stored_path")
            status, reason = self._evaluate_document(
                document_id=document_id,
                filename=filename,
                stored_path=stored_path,
                active_counts=active_counts,
                force=force,
            )
            documents.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "status": status,
                    "reason": reason,
                }
            )
            summary["total"] += 1
            if status == STATUS_WOULD_REINDEX:
                summary["would_reindex"] += 1
            elif status == STATUS_ALREADY_INDEXED:
                summary["already_indexed"] += 1
            elif status == STATUS_MISSING_FILE:
                summary["missing_file"] += 1
            elif status == STATUS_UNSUPPORTED:
                summary["unsupported"] += 1

        return {
            "dry_run": dry_run,
            "force": force,
            "active_provider": str(provider_info["provider"]),
            "active_model": str(provider_info["model"]),
            "active_dimension": int(provider_info["dimension"]),
            "active_collection": collection_status.get("active_collection"),
            "documents": documents,
            "summary": summary,
        }

    def run_reindex_plan(
        self,
        *,
        document_ids: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        trace_id = str(uuid.uuid4())
        get_local_metrics().increment("documents.reindex.run")
        plan = self.build_reindex_plan(
            document_ids=document_ids,
            force=force,
            dry_run=False,
        )

        results: list[dict[str, Any]] = []
        summary = {
            "total": plan["summary"]["total"],
            "reindexed": 0,
            "skipped": 0,
            "missing_file": 0,
            "unsupported": 0,
            "failed": 0,
        }

        for item in plan["documents"]:
            document_id = item["document_id"]
            filename = item["filename"]
            planned_status = item["status"]

            if planned_status == STATUS_ALREADY_INDEXED:
                get_local_metrics().increment("documents.reindex.skipped")
                results.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "status": STATUS_SKIPPED,
                        "reason": item["reason"],
                    }
                )
                summary["skipped"] += 1
                continue

            if planned_status == STATUS_MISSING_FILE:
                results.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "status": STATUS_MISSING_FILE,
                        "reason": item["reason"],
                    }
                )
                summary["missing_file"] += 1
                continue

            if planned_status == STATUS_UNSUPPORTED:
                results.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "status": STATUS_UNSUPPORTED,
                        "reason": item["reason"],
                    }
                )
                summary["unsupported"] += 1
                continue

            entry = self.registry.get(document_id)
            if entry is None:
                get_local_metrics().increment("documents.reindex.failed")
                results.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "status": STATUS_ERROR,
                        "reason": "Document is no longer registered.",
                    }
                )
                summary["failed"] += 1
                continue

            try:
                chunk_count = self._reindex_document(
                    entry=entry,
                    force=force,
                )
                get_local_metrics().increment("documents.reindex.completed")
                results.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "status": STATUS_REINDEXED,
                        "reason": f"Indexed {chunk_count} chunk(s) into the active collection.",
                        "chunks_indexed": chunk_count,
                    }
                )
                summary["reindexed"] += 1
            except Exception as exc:
                logger.exception("Document reindex failed for %s", document_id)
                get_local_metrics().increment("documents.reindex.failed")
                log_structured(
                    "documents.reindex.failed",
                    trace_id,
                    {"document_id": document_id, "error": safe_ingestion_error_message(exc)},
                )
                results.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "status": STATUS_ERROR,
                        "reason": safe_ingestion_error_message(exc),
                    }
                )
                summary["failed"] += 1

        return {
            "dry_run": False,
            "force": force,
            "trace_id": trace_id,
            "active_provider": plan["active_provider"],
            "active_model": plan["active_model"],
            "active_dimension": plan["active_dimension"],
            "active_collection": plan["active_collection"],
            "documents": results,
            "summary": summary,
        }

    def _select_entries(self, document_ids: list[str] | None) -> list[dict[str, Any]]:
        entries = self.registry.list_all()
        if not document_ids:
            return entries

        selected_ids = {str(document_id) for document_id in document_ids}
        return [entry for entry in entries if str(entry["id"]) in selected_ids]

    def _evaluate_document(
        self,
        *,
        document_id: str,
        filename: str,
        stored_path: str | None,
        active_counts: dict[str, int],
        force: bool,
    ) -> tuple[str, str]:
        if not stored_path or not os.path.exists(stored_path):
            return STATUS_MISSING_FILE, "Registered file is missing on disk."

        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            return STATUS_UNSUPPORTED, f"Unsupported file type: {suffix or 'unknown'}."

        if active_counts.get(document_id, 0) > 0 and not force:
            return (
                STATUS_ALREADY_INDEXED,
                "Document already has vectors in the active embeddings collection.",
            )

        return STATUS_WOULD_REINDEX, "Ready to reindex into the active embeddings collection."

    def _reindex_document(self, *, entry: dict[str, Any], force: bool) -> int:
        document_id = str(entry["id"])
        filename = str(entry.get("filename") or document_id)
        stored_path = str(entry["stored_path"])

        if force:
            self.chroma_service.delete_document_from_active_collection(document_id)

        chunks = process_document(
            file_path=stored_path,
            original_filename=filename,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        if not chunks:
            raise ValueError("Document produced no indexable chunks.")

        for start in range(0, len(chunks), CHROMA_INDEX_BATCH_SIZE):
            batch = chunks[start : start + CHROMA_INDEX_BATCH_SIZE]
            self.chroma_service.add_documents(document_id=document_id, docs=batch)

        self.registry.update(document_id, {"total_chunks": len(chunks)})
        return len(chunks)
