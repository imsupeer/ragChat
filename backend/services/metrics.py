import threading
import time
from typing import Any


class LocalMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.monotonic()
        self._counters: dict[str, int] = {}
        self._last_values: dict[str, Any] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def set_last(self, name: str, value: Any) -> None:
        with self._lock:
            self._last_values[name] = value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": "ok",
                "uptime_seconds": round(time.monotonic() - self._start_time, 2),
                "counters": dict(self._counters),
                "last_values": dict(self._last_values),
            }


_metrics: LocalMetrics | None = None
_metrics_lock = threading.Lock()


def get_local_metrics() -> LocalMetrics:
    global _metrics
    with _metrics_lock:
        if _metrics is None:
            _metrics = LocalMetrics()
        return _metrics


def reset_local_metrics() -> None:
    global _metrics
    with _metrics_lock:
        _metrics = LocalMetrics()
