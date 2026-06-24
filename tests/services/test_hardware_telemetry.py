from services.hardware_telemetry import HardwareTelemetryService


def test_cpu_and_memory_success_with_fake_collectors():
    service = HardwareTelemetryService(
        cpu_collector=lambda: {
            "status": "ok",
            "usage_percent": 12.5,
            "logical_count": 8,
            "physical_count": 4,
        },
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 16_000_000_000,
            "used_bytes": 8_000_000_000,
            "available_bytes": 8_000_000_000,
            "usage_percent": 50.0,
        },
        nvidia_collector=lambda _timeout: None,
        amd_collector=lambda _timeout: None,
    )

    snapshot = service.get_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["cpu"]["usage_percent"] == 12.5
    assert snapshot["memory"]["total_bytes"] == 16_000_000_000
    assert snapshot["gpu"]["status"] == "unsupported"


def test_telemetry_disabled_returns_disabled_status():
    service = HardwareTelemetryService(enabled=False)

    snapshot = service.get_snapshot()

    assert snapshot["status"] == "disabled"
    assert snapshot["cpu"]["status"] == "disabled"
    assert snapshot["gpu"]["status"] == "disabled"


def test_gpu_provider_disabled_keeps_cpu_ram():
    service = HardwareTelemetryService(
        gpu_provider="disabled",
        cpu_collector=lambda: {"status": "ok", "usage_percent": 5.0, "logical_count": 4, "physical_count": 2},
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 1000,
            "used_bytes": 500,
            "available_bytes": 500,
            "usage_percent": 50.0,
        },
    )

    snapshot = service.get_snapshot()

    assert snapshot["cpu"]["status"] == "ok"
    assert snapshot["memory"]["status"] == "ok"
    assert snapshot["gpu"]["status"] == "disabled"


def test_nvidia_provider_unavailable_without_crashing():
    service = HardwareTelemetryService(
        gpu_provider="nvidia",
        cpu_collector=lambda: {"status": "ok", "usage_percent": 5.0, "logical_count": 4, "physical_count": 2},
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 1000,
            "used_bytes": 500,
            "available_bytes": 500,
            "usage_percent": 50.0,
        },
        nvidia_collector=lambda _timeout: None,
    )

    snapshot = service.get_snapshot()

    assert snapshot["gpu"]["status"] == "unavailable"
    assert snapshot["status"] == "ok"


def test_amd_provider_unavailable_without_crashing():
    service = HardwareTelemetryService(
        gpu_provider="amd",
        cpu_collector=lambda: {"status": "ok", "usage_percent": 5.0, "logical_count": 4, "physical_count": 2},
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 1000,
            "used_bytes": 500,
            "available_bytes": 500,
            "usage_percent": 50.0,
        },
        amd_collector=lambda _timeout: None,
    )

    snapshot = service.get_snapshot()

    assert snapshot["gpu"]["status"] == "unavailable"


def test_cpu_collector_error_marks_degraded():
    service = HardwareTelemetryService(
        cpu_collector=lambda: (_ for _ in ()).throw(RuntimeError("cpu down")),
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 1000,
            "used_bytes": 500,
            "available_bytes": 500,
            "usage_percent": 50.0,
        },
        nvidia_collector=lambda _timeout: None,
        amd_collector=lambda _timeout: None,
    )

    snapshot = service.get_snapshot()

    assert snapshot["status"] == "degraded"
    assert snapshot["cpu"]["status"] == "error"


def test_command_timeout_returns_safe_unavailable(monkeypatch):
    import subprocess

    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["nvidia-smi"], timeout=1)

    monkeypatch.setattr("services.hardware_telemetry.subprocess.run", timeout_run)
    monkeypatch.setattr("services.hardware_telemetry.shutil.which", lambda _cmd: "nvidia-smi")

    service = HardwareTelemetryService(
        gpu_provider="nvidia",
        cpu_collector=lambda: {"status": "ok", "usage_percent": 1.0, "logical_count": 1, "physical_count": 1},
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 1000,
            "used_bytes": 500,
            "available_bytes": 500,
            "usage_percent": 50.0,
        },
    )

    snapshot = service.get_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["gpu"]["status"] == "unavailable"


def test_snapshot_has_no_serial_numbers():
    service = HardwareTelemetryService(
        nvidia_collector=lambda _timeout: [
            {
                "name": "NVIDIA GeForce RTX 3060",
                "vendor": "NVIDIA",
                "usage_percent": 10.0,
                "memory_total_bytes": 1000,
                "memory_used_bytes": 500,
                "memory_usage_percent": 50.0,
            }
        ],
        amd_collector=lambda _timeout: None,
        cpu_collector=lambda: {"status": "ok", "usage_percent": 1.0, "logical_count": 1, "physical_count": 1},
        memory_collector=lambda: {
            "status": "ok",
            "total_bytes": 1000,
            "used_bytes": 500,
            "available_bytes": 500,
            "usage_percent": 50.0,
        },
        gpu_provider="nvidia",
    )

    snapshot = service.get_snapshot()
    text = str(snapshot)

    assert "serial" not in text.lower()
    assert "uuid" not in text.lower()
