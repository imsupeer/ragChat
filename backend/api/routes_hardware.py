from fastapi import APIRouter, Depends

from core.dependencies import get_hardware_telemetry_service, get_local_metrics_service
from services.hardware_telemetry import HardwareTelemetryService
from services.metrics import LocalMetrics

router = APIRouter(prefix="/hardware", tags=["hardware"])


def _record_hardware_metrics(metrics: LocalMetrics, snapshot: dict) -> None:
    gpu = snapshot.get("gpu") or {}
    gpu_status = gpu.get("status")
    if gpu_status == "ok":
        metrics.increment("hardware.telemetry.gpu_available")
    elif gpu_status in {"unsupported", "unavailable", "error"}:
        metrics.increment("hardware.telemetry.gpu_unavailable")

    cpu = snapshot.get("cpu") or {}
    if cpu.get("usage_percent") is not None:
        metrics.set_last("hardware.cpu.usage_percent", cpu["usage_percent"])

    memory = snapshot.get("memory") or {}
    if memory.get("usage_percent") is not None:
        metrics.set_last("hardware.memory.usage_percent", memory["usage_percent"])

    devices = gpu.get("devices") or []
    metrics.set_last("hardware.gpu.provider", gpu.get("provider"))
    metrics.set_last("hardware.gpu.device_count", len(devices))

    if devices:
        primary = devices[0]
        if primary.get("usage_percent") is not None:
            metrics.set_last("hardware.gpu.usage_percent", primary["usage_percent"])
        if primary.get("memory_usage_percent") is not None:
            metrics.set_last("hardware.gpu.memory_usage_percent", primary["memory_usage_percent"])


@router.get("/telemetry")
def get_hardware_telemetry(
    telemetry: HardwareTelemetryService = Depends(get_hardware_telemetry_service),
    metrics: LocalMetrics = Depends(get_local_metrics_service),
):
    metrics.increment("hardware.telemetry.request")
    try:
        snapshot = telemetry.get_snapshot()
    except Exception:
        metrics.increment("hardware.telemetry.error")
        raise

    metrics.increment("hardware.telemetry.success")
    _record_hardware_metrics(metrics, snapshot)
    return snapshot
