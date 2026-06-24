from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import (
    get_local_metrics_service,
    get_model_recommender_service,
    get_model_runtime_service,
    get_model_settings_service,
)
from services.metrics import LocalMetrics
from services.model_recommender import (
    HardwareProfileRequest,
    ModelRecommenderService,
    RecommendationResponse,
)
from services.model_runtime import ModelRuntimeError, ModelRuntimeService
from services.model_settings import ModelSettingsConflictError, ModelSettingsService

router = APIRouter(prefix="/models", tags=["models"])


def _record_runtime_metrics(metrics: LocalMetrics, status: dict) -> None:
    runtime = status.get("runtime") or {}
    active = status.get("active_model") or {}
    detection = runtime.get("loaded_detection", "unavailable")

    if detection == "available":
        metrics.increment("models.runtime.ps_success")
    else:
        metrics.increment("models.runtime.ps_unavailable")

    metrics.set_last("models.runtime.running_count", runtime.get("running_models_count", 0))
    loaded = active.get("loaded")
    if loaded is not None:
        metrics.set_last("models.runtime.active_loaded", loaded)
    metrics.set_last("models.runtime.loaded_detection", detection)
    cold_start = runtime.get("cold_start_likely")
    if cold_start is not None:
        metrics.set_last("models.runtime.cold_start_likely", cold_start)


class UpdateModelSettingsRequest(BaseModel):
    chat_model: str = Field(..., min_length=1)
    require_installed: bool = True


@router.get("/catalog")
def get_model_catalog(
    recommender: ModelRecommenderService = Depends(get_model_recommender_service),
):
    return {
        "status": "ok",
        "models": recommender.get_catalog(),
    }


@router.post("/recommendations", response_model=RecommendationResponse)
def post_model_recommendations(
    payload: HardwareProfileRequest,
    recommender: ModelRecommenderService = Depends(get_model_recommender_service),
    metrics: LocalMetrics = Depends(get_local_metrics_service),
):
    metrics.increment("models.recommendation.request")

    try:
        response = recommender.recommend(payload)
    except ValueError as exc:
        metrics.increment("models.recommendation.error")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        metrics.increment("models.recommendation.error")
        raise

    metrics.increment("models.recommendation.success")
    metrics.set_last("models.recommendation.last_confidence", response.confidence)
    metrics.set_last(
        "models.recommendation.last_detected_tier",
        response.hardware_summary.detected_tier,
    )
    return response


@router.get("/settings")
def get_model_settings(
    model_settings: ModelSettingsService = Depends(get_model_settings_service),
):
    return model_settings.get_state()


@router.put("/settings")
def put_model_settings(
    payload: UpdateModelSettingsRequest,
    model_settings: ModelSettingsService = Depends(get_model_settings_service),
    metrics: LocalMetrics = Depends(get_local_metrics_service),
):
    metrics.increment("models.settings.update")
    try:
        return model_settings.update_chat_model(
            payload.chat_model,
            require_installed=payload.require_installed,
        )
    except ModelSettingsConflictError as exc:
        metrics.increment("models.settings.error")
        raise HTTPException(status_code=409, detail={
            "status": "error",
            "message": str(exc),
            **({"install_command": exc.install_command} if exc.install_command else {}),
        }) from exc
    except ValueError as exc:
        metrics.increment("models.settings.error")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        metrics.increment("models.settings.error")
        raise


@router.post("/settings/reset")
def post_model_settings_reset(
    model_settings: ModelSettingsService = Depends(get_model_settings_service),
    metrics: LocalMetrics = Depends(get_local_metrics_service),
):
    metrics.increment("models.settings.reset")
    try:
        return model_settings.reset()
    except Exception:
        metrics.increment("models.settings.error")
        raise


@router.get("/runtime")
def get_model_runtime(
    runtime: ModelRuntimeService = Depends(get_model_runtime_service),
    metrics: LocalMetrics = Depends(get_local_metrics_service),
):
    metrics.increment("models.runtime.status")
    status = runtime.get_runtime_status()
    _record_runtime_metrics(metrics, status)
    return status


@router.post("/runtime/preload")
def post_model_runtime_preload(
    runtime: ModelRuntimeService = Depends(get_model_runtime_service),
    metrics: LocalMetrics = Depends(get_local_metrics_service),
):
    metrics.increment("models.runtime.preload")
    try:
        result = runtime.preload_active_model()
        runtime_status = result.get("runtime")
        if isinstance(runtime_status, dict):
            _record_runtime_metrics(metrics, runtime_status)
            if runtime_status.get("active_model", {}).get("loaded") is True:
                metrics.increment("models.runtime.loaded_active")
        return result
    except ModelRuntimeError as exc:
        metrics.increment("models.runtime.preload_error")
        detail = {"status": "error", "message": str(exc)}
        if exc.install_command:
            detail["install_command"] = exc.install_command
        raise HTTPException(status_code=409, detail=detail) from exc
    except Exception:
        metrics.increment("models.runtime.preload_error")
        raise


@router.post("/runtime/unload")
def post_model_runtime_unload(
    runtime: ModelRuntimeService = Depends(get_model_runtime_service),
    metrics: LocalMetrics = Depends(get_local_metrics_service),
):
    metrics.increment("models.runtime.unload")
    try:
        result = runtime.unload_active_model()
        runtime_status = result.get("runtime")
        if isinstance(runtime_status, dict):
            _record_runtime_metrics(metrics, runtime_status)
            if runtime_status.get("active_model", {}).get("loaded") is False:
                metrics.increment("models.runtime.unloaded_active")
        return result
    except ModelRuntimeError as exc:
        metrics.increment("models.runtime.unload_error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        metrics.increment("models.runtime.unload_error")
        raise
