from services.metrics import LocalMetrics, get_local_metrics


def test_local_metrics_increment_and_snapshot():
    metrics = LocalMetrics()
    metrics.increment("chat.stream.completed", 2)
    metrics.set_last("reconciliation.status", "ok")

    snapshot = metrics.snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["counters"]["chat.stream.completed"] == 2
    assert snapshot["last_values"]["reconciliation.status"] == "ok"
    assert snapshot["uptime_seconds"] >= 0


def test_get_local_metrics_returns_singleton():
    first = get_local_metrics()
    second = get_local_metrics()
    assert first is second
