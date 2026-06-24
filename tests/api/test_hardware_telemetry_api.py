import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_hardware import router as hardware_router
from core.dependencies import get_hardware_telemetry_service, get_local_metrics_service
from services.hardware_telemetry import HardwareTelemetryService
from services.metrics import LocalMetrics


def build_client(service: HardwareTelemetryService, metrics: LocalMetrics | None = None):
    app = FastAPI()
    app.include_router(hardware_router)
    app.dependency_overrides[get_hardware_telemetry_service] = lambda: service
    app.dependency_overrides[get_local_metrics_service] = lambda: metrics or LocalMetrics()
    return TestClient(app)


@pytest.fixture
def telemetry_service() -> HardwareTelemetryService:
    return HardwareTelemetryService(
        enabled=True,
        timeout_seconds=1.0,
        poll_seconds=5.0,
        gpu_provider="auto",
        cpu_collector=lambda: {
            "status": "ok",
            "usage_percent": 18.5,
            "logical_count": 16,
            "physical_count": 8,
        },
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 34_359_738_368,
            "used_bytes": 17_179_869_184,
            "available_bytes": 17_179_869_184,
            "usage_percent": 50.0,
        },
        nvidia_collector=lambda _timeout: None,
        amd_collector=lambda _timeout: None,
    )


def test_get_hardware_telemetry_returns_expected_shape(telemetry_service: HardwareTelemetryService):
    with build_client(telemetry_service) as client:
        response = client.get("/hardware/telemetry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["cpu"]["usage_percent"] == 18.5
    assert payload["memory"]["usage_percent"] == 50.0
    assert payload["gpu"]["status"] == "unsupported"
    assert payload["poll_interval_seconds"] == 5.0
    assert "checked_at" in payload


def test_get_hardware_telemetry_increments_metrics(telemetry_service: HardwareTelemetryService):
    metrics = LocalMetrics()
    with build_client(telemetry_service, metrics) as client:
        response = client.get("/hardware/telemetry")

    assert response.status_code == 200
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["hardware.telemetry.request"] == 1
    assert snapshot["counters"]["hardware.telemetry.success"] == 1
    assert snapshot["last_values"]["hardware.cpu.usage_percent"] == 18.5


def test_get_hardware_telemetry_no_local_paths(telemetry_service: HardwareTelemetryService):
    with build_client(telemetry_service) as client:
        response = client.get("/hardware/telemetry")

    text = response.text
    assert "C:\\" not in text
    assert "/Users/" not in text


def test_get_hardware_telemetry_gpu_available_metrics():
    service = HardwareTelemetryService(
        enabled=True,
        gpu_provider="nvidia",
        cpu_collector=lambda: {"status": "ok", "usage_percent": 10.0, "logical_count": 8, "physical_count": 4},
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 1000,
            "used_bytes": 500,
            "available_bytes": 500,
            "usage_percent": 50.0,
        },
        nvidia_collector=lambda _timeout: [
            {
                "name": "NVIDIA GeForce RTX 3060",
                "vendor": "NVIDIA",
                "usage_percent": 62.0,
                "memory_total_bytes": 12_884_901_888,
                "memory_used_bytes": 6_442_450_944,
                "memory_usage_percent": 50.0,
            }
        ],
        amd_collector=lambda _timeout: None,
    )
    metrics = LocalMetrics()
    with build_client(service, metrics) as client:
        response = client.get("/hardware/telemetry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gpu"]["status"] == "ok"
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["hardware.telemetry.gpu_available"] == 1
    assert snapshot["last_values"]["hardware.gpu.usage_percent"] == 62.0
