from fastapi import APIRouter, Depends

from core.dependencies import get_local_metrics_service, get_readiness_service
from services.metrics import LocalMetrics
from services.readiness import ReadinessService

router = APIRouter(tags=["health"])


@router.get("/health/ready")
def health_ready(
    readiness_service: ReadinessService = Depends(get_readiness_service),
):
    return readiness_service.check()
