from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

ALLOWED_GPU_PROVIDERS = frozenset({"auto", "nvidia", "amd", "disabled"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mi_b_to_bytes(value: float) -> int:
    return int(value * 1024 * 1024)


def _safe_percent(used: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round((used / total) * 100.0, 1)


def _collect_cpu_psutil() -> dict[str, Any]:
    import psutil

    usage = psutil.cpu_percent(interval=0.1)
    return {
        "status": "ok",
        "usage_percent": round(float(usage), 1),
        "logical_count": psutil.cpu_count(logical=True),
        "physical_count": psutil.cpu_count(logical=False),
    }


def _collect_memory_psutil() -> dict[str, Any]:
    import psutil

    memory = psutil.virtual_memory()
    return {
        "status": "ok",
        "total_bytes": int(memory.total),
        "used_bytes": int(memory.used),
        "available_bytes": int(memory.available),
        "usage_percent": round(float(memory.percent), 1),
    }


def _run_command(command: list[str], timeout: float) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        logger.info("Hardware telemetry command failed: %s", exc)
        return None


def _parse_nvidia_smi_output(stdout: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) < 5:
            continue
        name = parts[0]
        try:
            usage_percent = float(parts[1])
            memory_total = _mi_b_to_bytes(float(parts[2]))
            memory_used = _mi_b_to_bytes(float(parts[3]))
            memory_free = _mi_b_to_bytes(float(parts[4])) if len(parts) > 4 else None
            temperature = float(parts[5]) if len(parts) > 5 and parts[5] not in {"", "[N/A]"} else None
        except ValueError:
            continue

        device: dict[str, Any] = {
            "name": name,
            "vendor": "NVIDIA",
            "usage_percent": round(usage_percent, 1),
            "memory_total_bytes": memory_total,
            "memory_used_bytes": memory_used,
            "memory_usage_percent": _safe_percent(memory_used, memory_total),
        }
        if memory_free is not None:
            device["memory_free_bytes"] = memory_free
        if temperature is not None:
            device["temperature_c"] = round(temperature, 1)
        devices.append(device)
    return devices


def _collect_nvidia_devices(timeout: float) -> list[dict[str, Any]] | None:
    if shutil.which("nvidia-smi") is None:
        return None

    result = _run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.total,memory.used,memory.free,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout,
    )
    if result is None or result.returncode != 0:
        return None

    devices = _parse_nvidia_smi_output(result.stdout)
    return devices or None


def _parse_rocm_smi_output(stdout: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("gpu"):
            continue
        if "," not in stripped:
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) < 4:
            continue
        try:
            name = parts[0]
            usage_percent = float(parts[1])
            memory_total = int(float(parts[2]) * 1024 * 1024)
            memory_used = int(float(parts[3]) * 1024 * 1024)
        except ValueError:
            continue
        devices.append(
            {
                "name": name,
                "vendor": "AMD",
                "usage_percent": round(usage_percent, 1),
                "memory_total_bytes": memory_total,
                "memory_used_bytes": memory_used,
                "memory_usage_percent": _safe_percent(memory_used, memory_total),
            }
        )
    return devices


def _collect_amd_devices(timeout: float) -> list[dict[str, Any]] | None:
    if shutil.which("rocm-smi") is not None:
        result = _run_command(
            [
                "rocm-smi",
                "--showproductname",
                "--showuse",
                "--showmeminfo",
                "vram",
                "--csv",
            ],
            timeout,
        )
        if result is not None and result.returncode == 0 and result.stdout.strip():
            devices = _parse_rocm_smi_output(result.stdout)
            if devices:
                return devices

    if shutil.which("amd-smi") is not None:
        result = _run_command(["amd-smi", "metric", "--csv"], timeout)
        if result is not None and result.returncode == 0:
            devices = _parse_rocm_smi_output(result.stdout)
            if devices:
                return devices

    return None


class HardwareTelemetryService:
    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 2.0,
        poll_seconds: float = 5.0,
        gpu_provider: str = "auto",
        cpu_collector: Callable[[], dict[str, Any]] | None = None,
        memory_collector: Callable[[], dict[str, Any]] | None = None,
        nvidia_collector: Callable[[float], list[dict[str, Any]] | None] | None = None,
        amd_collector: Callable[[float], list[dict[str, Any]] | None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        normalized_provider = (gpu_provider or "auto").strip().lower()
        if normalized_provider not in ALLOWED_GPU_PROVIDERS:
            normalized_provider = "auto"
        self.gpu_provider = normalized_provider
        self._cpu_collector = cpu_collector or _collect_cpu_psutil
        self._memory_collector = memory_collector or _collect_memory_psutil
        self._nvidia_collector = nvidia_collector or _collect_nvidia_devices
        self._amd_collector = amd_collector or _collect_amd_devices

    def get_snapshot(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "status": "disabled",
                "checked_at": _utc_now_iso(),
                "poll_interval_seconds": self.poll_seconds,
                "cpu": {"status": "disabled"},
                "memory": {"status": "disabled"},
                "gpu": {
                    "status": "disabled",
                    "provider": "none",
                    "devices": [],
                    "message": "Hardware telemetry is disabled.",
                },
            }

        cpu = self._safe_collect(self._cpu_collector, "cpu")
        memory = self._safe_collect(self._memory_collector, "memory")
        gpu = self._collect_gpu()

        status = "ok"
        if cpu.get("status") == "error" or memory.get("status") == "error":
            status = "degraded"
        elif gpu.get("status") == "error":
            status = "degraded"

        return {
            "status": status,
            "checked_at": _utc_now_iso(),
            "poll_interval_seconds": self.poll_seconds,
            "cpu": cpu,
            "memory": memory,
            "gpu": gpu,
        }

    def _safe_collect(self, collector: Callable[[], dict[str, Any]], label: str) -> dict[str, Any]:
        try:
            return collector()
        except Exception as exc:
            logger.info("Hardware telemetry %s collection failed: %s", label, exc)
            return {"status": "error", "message": f"Failed to collect {label} telemetry."}

    def _collect_gpu(self) -> dict[str, Any]:
        if self.gpu_provider == "disabled":
            return {
                "status": "disabled",
                "provider": "none",
                "devices": [],
                "message": "GPU telemetry is disabled by configuration.",
            }

        providers_to_try: list[str]
        if self.gpu_provider == "auto":
            providers_to_try = ["nvidia", "amd"]
        else:
            providers_to_try = [self.gpu_provider]

        errors: list[str] = []
        for provider in providers_to_try:
            try:
                if provider == "nvidia":
                    devices = self._nvidia_collector(self.timeout_seconds)
                elif provider == "amd":
                    devices = self._amd_collector(self.timeout_seconds)
                else:
                    continue
            except Exception as exc:
                logger.info("GPU provider %s failed: %s", provider, exc)
                errors.append(provider)
                continue

            if devices:
                return {
                    "status": "ok",
                    "provider": provider,
                    "devices": devices,
                    "message": None,
                }

            errors.append(provider)

        if self.gpu_provider in {"nvidia", "amd"}:
            message = (
                f"{self.gpu_provider.upper()} monitoring tools were not available. "
                "Install the vendor GPU tools to enable GPU/VRAM metrics."
            )
            return {
                "status": "unavailable",
                "provider": self.gpu_provider,
                "devices": [],
                "message": message,
            }

        return {
            "status": "unsupported",
            "provider": "none",
            "devices": [],
            "message": (
                "GPU telemetry unavailable. CPU/RAM metrics are still available. "
                "Install NVIDIA or AMD monitoring tools to enable GPU/VRAM metrics."
            ),
        }
