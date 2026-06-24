import logging
from typing import Any

from core.config import Settings
from services.chroma_service import ChromaService
from services.metrics import LocalMetrics
from services.model_runtime import ModelRuntimeService
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
    ) -> None:
        self.settings = settings
        self.sqlite_store = sqlite_store
        self.chroma_service = chroma_service
        self.upload_queue = upload_queue
        self.metrics = metrics
        self.model_runtime = model_runtime

    def check(self) -> dict[str, Any]:
        checks: dict[str, dict[str, Any]] = {}

        checks["sqlite"] = self._check_sqlite()
        checks["chroma"] = self._check_chroma()
        checks["upload_queue"] = self._check_upload_queue()
        checks["reconciliation"] = self._check_reconciliation()
        checks["ollama"] = self._check_ollama()

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
            return {"status": "ok", "document_count": document_count}
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
