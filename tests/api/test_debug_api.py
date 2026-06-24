from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_debug import router as debug_router
from core.config import Settings, get_settings
from core.dependencies import get_local_metrics_service, get_reconciliation_service
from services.metrics import LocalMetrics
from ingestion.processor import save_uploaded_file
from services.reconciliation import (
    ACTION_CLEAR_JOB_DOCUMENT_REFERENCE,
    ACTION_MANUAL_REVIEW,
    ACTION_MARK_JOB_MISSING_FILE_FAILED,
    ACTION_REMOVE_STALE_REGISTRY_ENTRY,
    MISSING_UPLOAD_FILE_ERROR,
    PersistenceReconciliationService,
)
from services.sqlite_store import SQLiteStore


class FakeRegistry:
    def __init__(self, entries: list[dict]) -> None:
        self.entries = list(entries)

    def list_all(self) -> list[dict]:
        return list(self.entries)

    def remove(self, document_id: str) -> dict | None:
        for index, entry in enumerate(self.entries):
            if entry["id"] == document_id:
                return self.entries.pop(index)
        return None


class FakeChromaService:
    def list_document_ids_with_vector_counts(self) -> dict[str, int]:
        return {"doc-1": 1}


def build_reconciliation_service(tmp_path: Path) -> PersistenceReconciliationService:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    stored_path = save_uploaded_file(b"hello", "sample.txt", str(docs_dir))

    return PersistenceReconciliationService(
        registry=FakeRegistry(
            [
                {
                    "id": "doc-1",
                    "filename": "sample.txt",
                    "stored_path": stored_path,
                    "total_chunks": 1,
                }
            ]
        ),
        chroma_service=FakeChromaService(),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
        documents_directory=str(docs_dir),
    )


def test_debug_reconciliation_endpoint_returns_report(tmp_path: Path):
    app = FastAPI()
    app.include_router(debug_router)
    service = build_reconciliation_service(tmp_path)
    app.dependency_overrides[get_reconciliation_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/debug/reconciliation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["summary"]["registry_documents"] == 1
    assert "checked_at" in payload


def test_debug_reconciliation_endpoint_handles_drift(tmp_path: Path):
    app = FastAPI()
    app.include_router(debug_router)

    service = PersistenceReconciliationService(
        registry=FakeRegistry(
            [
                {
                    "id": "doc-1",
                    "filename": "missing.txt",
                    "stored_path": str(tmp_path / "docs" / "missing.txt"),
                    "total_chunks": 1,
                }
            ]
        ),
        chroma_service=FakeChromaService(),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
        documents_directory=str(tmp_path / "docs"),
    )
    app.dependency_overrides[get_reconciliation_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/debug/reconciliation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "drift_detected"
    assert payload["summary"]["issues"] > 0
    assert "C:\\" not in payload["issues"][0]["details"]


def test_debug_reconciliation_endpoint_is_read_only(tmp_path: Path):
    app = FastAPI()
    app.include_router(debug_router)
    service = build_reconciliation_service(tmp_path)
    registry_entries_before = service.registry.list_all()
    app.dependency_overrides[get_reconciliation_service] = lambda: service

    with TestClient(app) as client:
        client.get("/debug/reconciliation")
        client.get("/debug/reconciliation")

    assert service.registry.list_all() == registry_entries_before


def test_startup_runs_reconciliation_without_crashing(tmp_path: Path):
    mock_queue = MagicMock()
    mock_reconciliation = MagicMock()
    mock_reconciliation.run_report.return_value = {
        "status": "drift_detected",
        "summary": {"issues": 1},
    }

    with patch("main.get_upload_queue_service", return_value=mock_queue):
        with patch("main.get_reconciliation_service", return_value=mock_reconciliation):
            with patch("main.settings") as mock_settings:
                mock_settings.reconcile_on_startup = True
                mock_settings.reconcile_repair_on_startup = False
                from main import app as lifespan_app

                with TestClient(lifespan_app) as client:
                    response = client.get("/health")

    assert response.status_code == 200
    mock_reconciliation.run_report.assert_called_once()
    mock_queue.shutdown.assert_called_once()


def test_debug_metrics_endpoint_returns_safe_snapshot():
    app = FastAPI()
    app.include_router(debug_router)
    metrics = LocalMetrics()
    metrics.increment("chat.stream.completed")
    metrics.set_last("retrieval.last_latency_ms", 12.3)
    app.dependency_overrides[get_local_metrics_service] = lambda: metrics

    with TestClient(app) as client:
        response = client.get("/debug/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counters"]["chat.stream.completed"] == 1
    assert payload["last_values"]["retrieval.last_latency_ms"] == 12.3
    assert "C:\\" not in str(payload)
    assert "prompt" not in str(payload).lower() or "chat.stream.completed" in str(
        payload["counters"]
    )


def _build_debug_app(
    tmp_path: Path,
    *,
    allow_stale_registry_repair: bool = False,
) -> tuple[TestClient, PersistenceReconciliationService]:
    app = FastAPI()
    app.include_router(debug_router)
    service = build_reconciliation_service(tmp_path)
    app.dependency_overrides[get_reconciliation_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(
        reconcile_allow_stale_registry_repair=allow_stale_registry_repair,
    )
    return TestClient(app), service


def test_reconciliation_repair_endpoint_defaults_to_dry_run(tmp_path: Path):
    client, service = _build_debug_app(tmp_path)
    sqlite_store = service.sqlite_store
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )
    job = sqlite_store.list_upload_jobs()[0]
    before = sqlite_store.get_upload_job(job["id"])

    with client:
        response = client.post("/debug/reconciliation/repair")

    assert response.status_code == 200
    payload = response.json()
    assert payload["repair_plan"]["dry_run"] is True
    assert sqlite_store.get_upload_job(job["id"]) == before


def test_reconciliation_repair_endpoint_apply_mutates_safe_cases(tmp_path: Path):
    client, service = _build_debug_app(tmp_path)
    sqlite_store = service.sqlite_store
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )
    job = sqlite_store.list_upload_jobs()[0]

    with client:
        response = client.post(
            "/debug/reconciliation/repair",
            json={"dry_run": False},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repair_plan"]["dry_run"] is False
    assert payload["repair_plan"]["summary"]["applied"] >= 1
    updated = sqlite_store.get_upload_job(job["id"])
    assert updated["status"] == "failed"
    assert updated["error"] == MISSING_UPLOAD_FILE_ERROR


def test_reconciliation_repair_endpoint_includes_summary_and_actions(tmp_path: Path):
    client, service = _build_debug_app(tmp_path)
    service.sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )

    with client:
        response = client.post("/debug/reconciliation/repair")

    payload = response.json()
    assert "report" in payload
    assert "repair_plan" in payload
    assert "summary" in payload["repair_plan"]
    assert isinstance(payload["repair_plan"]["actions"], list)


def test_reconciliation_repair_endpoint_hides_absolute_paths(tmp_path: Path):
    client, service = _build_debug_app(tmp_path)
    service.sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )

    with client:
        response = client.post("/debug/reconciliation/repair")

    assert "C:\\" not in response.text
    assert str(tmp_path) not in response.text


def test_reconciliation_repair_stale_registry_requires_config_flag(tmp_path: Path):
    app = FastAPI()
    app.include_router(debug_router)
    service = PersistenceReconciliationService(
        registry=FakeRegistry(
            [
                {
                    "id": "doc-1",
                    "filename": "missing.txt",
                    "stored_path": str(tmp_path / "docs" / "missing.txt"),
                    "total_chunks": 1,
                }
            ]
        ),
        chroma_service=FakeChromaService(),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
        documents_directory=str(tmp_path / "docs"),
    )

    class EmptyChroma:
        def list_document_ids_with_vector_counts(self) -> dict[str, int]:
            return {}

    service.chroma_service = EmptyChroma()
    app.dependency_overrides[get_reconciliation_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(
        reconcile_allow_stale_registry_repair=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/debug/reconciliation/repair",
            json={"dry_run": False, "include_stale_registry_cleanup": True},
        )

    payload = response.json()
    stale_actions = [
        action
        for action in payload["repair_plan"]["actions"]
        if action["type"] == ACTION_REMOVE_STALE_REGISTRY_ENTRY
    ]
    assert stale_actions
    assert stale_actions[0]["will_apply"] is False
    assert len(service.registry.list_all()) == 1
