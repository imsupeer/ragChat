import logging
from typing import Any

from core.config import Settings
from services.chroma_service import ChromaService
from services.metrics import LocalMetrics
from services.model_runtime import ModelRuntimeService
from services.embeddings_provider import EmbeddingsProvider
from services.embedding_collection_diagnostics import build_embedding_collection_diagnostics
from services.document_registry import DocumentRegistry
from services.document_reindex import build_reindex_guidance
from services.sqlite_store import SQLiteStore
from services.upload_queue import UploadQueueService

logger = logging.getLogger("uvicorn.error")


class ReadinessService:
    def __init__(
        self,
        *,
        settings: Settings,
        sqlite_store: SQLiteStore,
        chroma_service: ChromaService,
        upload_queue: UploadQueueService,
        metrics: LocalMetrics,
        model_runtime: ModelRuntimeService | None = None,
        embeddings_provider: EmbeddingsProvider | None = None,
        document_registry: DocumentRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.sqlite_store = sqlite_store
        self.chroma_service = chroma_service
        self.upload_queue = upload_queue
        self.metrics = metrics
        self.model_runtime = model_runtime
        self.embeddings_provider = embeddings_provider
        self.document_registry = document_registry

    def check(self) -> dict[str, Any]:
        checks: dict[str, dict[str, Any]] = {}

        checks["sqlite"] = self._check_sqlite()
        checks["chroma"] = self._check_chroma()
        checks["upload_queue"] = self._check_upload_queue()
        checks["reconciliation"] = self._check_reconciliation()
        checks["ollama"] = self._check_ollama()
        checks["embeddings"] = self._check_embeddings()

        statuses = [check["status"] for check in checks.values()]
        if any(status == "error" for status in statuses):
            overall = "error"
        elif any(status == "degraded" for status in statuses):
            overall = "degraded"
        else:
            overall = "ok"

        self.metrics.increment("models.runtime.status")
        return {"status": overall, "checks": checks}

    def _check_sqlite(self) -> dict[str, Any]:
        try:
            self.sqlite_store.ping()
            return {"status": "ok"}
        except Exception as exc:
            logger.warning("Readiness SQLite check failed: %s", exc)
            return {"status": "error", "message": "SQLite unavailable"}

    def _check_chroma(self) -> dict[str, Any]:
        try:
            document_count = len(self.chroma_service.list_document_ids_with_vector_counts())
            check: dict[str, Any] = {"status": "ok", "document_count": document_count}
            if hasattr(self.chroma_service, "get_collection_status"):
                status = self.chroma_service.get_collection_status()
                check["strategy"] = status.get("strategy")
                check["active_collection"] = status.get("active_collection")
            return check
        except Exception as exc:
            logger.warning("Readiness Chroma check failed: %s", exc)
            return {"status": "error", "message": "Chroma unavailable"}

    def _check_upload_queue(self) -> dict[str, Any]:
        if self.upload_queue.is_worker_alive:
            return {"status": "ok", "worker_alive": True}
        return {
            "status": "degraded",
            "worker_alive": False,
            "message": "Upload queue worker is not running",
        }

    def _check_reconciliation(self) -> dict[str, Any]:
        snapshot = self.metrics.snapshot()
        last_values = snapshot["last_values"]
        last_status = last_values.get("reconciliation.status")
        last_issues = last_values.get("reconciliation.issues")

        if last_status is None:
            return {"status": "ok", "message": "No reconciliation run recorded yet"}

        check: dict[str, Any] = {
            "status": "ok" if last_status in {"ok", "drift_detected"} else "degraded",
            "last_status": last_status,
        }
        if last_issues is not None:
            check["issues"] = last_issues
        if last_status == "error":
            check["status"] = "degraded"
            check["message"] = "Last reconciliation run failed"
        return check

    def _check_ollama(self) -> dict[str, Any]:
        if self.model_runtime is not None:
            try:
                return self.model_runtime.readiness_summary()
            except Exception as exc:
                logger.warning("Readiness model runtime check failed: %s", exc)
                return {
                    "status": "degraded",
                    "reachable": False,
                    "message": "Ollama unavailable",
                }

        return {
            "status": "degraded",
            "reachable": False,
            "message": "Ollama runtime status unavailable",
        }

    def _check_embeddings(self) -> dict[str, Any]:
        if self.embeddings_provider is None:
            return {"status": "ok", "message": "Embeddings provider status unavailable"}

        info = self.embeddings_provider.provider_info()
        check: dict[str, Any] = {
            "status": "ok",
            **info,
        }
        diagnostics = build_embedding_collection_diagnostics(
            self.chroma_service,
            provider=str(info["provider"]),
            model=str(info["model"]),
            dimension=int(info["dimension"]),
        )
        collection = diagnostics.get("collection", {})
        chroma_status = (
            self.chroma_service.get_collection_status()
            if hasattr(self.chroma_service, "get_collection_status")
            else {}
        )
        check["collection"] = {
            "strategy": chroma_status.get("strategy"),
            "active_collection": chroma_status.get("active_collection"),
            "status": diagnostics.get("status"),
            "reindex_recommended": diagnostics.get("reindex_recommended", False),
            "total_chunks": collection.get("total_chunks", 0),
            "matching_chunks": collection.get("matching_chunks", 0),
            "mismatched_provider_chunks": collection.get("mismatched_provider_chunks", 0),
            "legacy_chunks": collection.get("legacy_chunks", 0),
            "message": diagnostics.get("message"),
        }
        provider_status = str(info.get("status") or "ok")
        if provider_status != "ok":
            check["status"] = "degraded"
        if info.get("provider") == "local_hash":
            check["message"] = "Using demo-quality local hash embeddings."
        elif info.get("provider") == "sentence_transformers":
            if provider_status == "missing_dependency":
                check["message"] = info.get("message") or (
                    "Install sentence-transformers to use semantic local embeddings."
                )
            elif provider_status == "model_missing":
                check["message"] = info.get("message") or (
                    "Cache the configured sentence-transformers model locally."
                )
            elif provider_status != "ok":
                check["message"] = info.get("message") or (
                    "Sentence-transformers embeddings are unavailable."
                )

        collection = check.get("collection")
        if isinstance(collection, dict):
            if collection.get("reindex_recommended"):
                check["collection_warning"] = collection.get("message")
                check["collection_status"] = collection.get("status")
                check["reindex_recommended"] = True
            reindex = build_reindex_guidance(
                collection_status=str(diagnostics.get("status") or "unknown"),
                reindex_recommended=bool(diagnostics.get("reindex_recommended")),
                registered_document_count=(
                    len(self.document_registry.list_all())
                    if self.document_registry is not None
                    else 0
                ),
            )
            if reindex.get("recommended"):
                check["reindex"] = reindex
        return check
