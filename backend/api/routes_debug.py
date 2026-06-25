from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.dependencies import get_local_metrics_service, get_model_runtime_service, get_reconciliation_service
from core.observability import safe_reconciliation_error_message
from services.metrics import LocalMetrics
from services.model_runtime import ModelRuntimeService
from services.reconciliation import PersistenceReconciliationService

router = APIRouter(prefix="/debug", tags=["debug"])


class ReconciliationRepairRequest(BaseModel):
    dry_run: bool = True
    include_stale_registry_cleanup: bool = False


@router.get("/reconciliation")
def get_reconciliation_report(
    reconciliation_service: PersistenceReconciliationService = Depends(
        get_reconciliation_service
    ),
):
    try:
        return reconciliation_service.run_report()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=safe_reconciliation_error_message(exc),
        ) from exc


@router.post("/reconciliation/repair")
def post_reconciliation_repair(
    payload: ReconciliationRepairRequest | None = None,
    reconciliation_service: PersistenceReconciliationService = Depends(
        get_reconciliation_service
    ),
    settings: Settings = Depends(get_settings),
):
    request = payload or ReconciliationRepairRequest()
    include_stale_registry = (
        request.include_stale_registry_cleanup
        and settings.reconcile_allow_stale_registry_repair
    )

    try:
        return reconciliation_service.run_repair(
            dry_run=request.dry_run,
            include_stale_registry_cleanup=include_stale_registry,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=safe_reconciliation_error_message(exc),
        ) from exc


@router.get("/metrics")
def get_metrics_snapshot(
    metrics: LocalMetrics = Depends(get_local_metrics_service),
):
    return metrics.snapshot()


@router.get("/embeddings")
def get_embeddings_diagnostics(
    runtime: ModelRuntimeService = Depends(get_model_runtime_service),
):
    return runtime.get_embeddings_diagnostics()
