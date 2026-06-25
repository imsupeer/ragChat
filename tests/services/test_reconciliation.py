from pathlib import Path
from unittest.mock import patch

import pytest

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
    def __init__(self, entries: list[dict] | None = None) -> None:
        self.entries = list(entries or [])

    def list_all(self) -> list[dict]:
        return list(self.entries)

    def remove(self, document_id: str) -> dict | None:
        for index, entry in enumerate(self.entries):
            if entry["id"] == document_id:
                return self.entries.pop(index)
        return None


class FakeChromaService:
    def __init__(
        self,
        counts: dict[str, int] | None = None,
        *,
        should_fail: bool = False,
        collections: dict[str, dict[str, int]] | None = None,
        collection_name: str = "rag_chat",
    ) -> None:
        self.counts = dict(counts or {})
        self.collections = dict(collections or {collection_name: dict(counts or {})})
        self.should_fail = should_fail
        self.collection_name = collection_name

    def list_document_ids_with_vector_counts(self) -> dict[str, int]:
        if self.should_fail:
            raise RuntimeError("Chroma unavailable")
        return dict(self.counts)

    def summarize_collections(self) -> dict[str, dict[str, int]]:
        if self.should_fail:
            raise RuntimeError("Chroma unavailable")
        return {name: dict(doc_counts) for name, doc_counts in self.collections.items()}


def build_service(
    tmp_path: Path,
    *,
    registry_entries: list[dict] | None = None,
    chroma_counts: dict[str, int] | None = None,
    chroma_should_fail: bool = False,
) -> tuple[PersistenceReconciliationService, SQLiteStore, Path]:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    sqlite_store = SQLiteStore(str(tmp_path / "app.db"))
    service = PersistenceReconciliationService(
        registry=FakeRegistry(registry_entries),
        chroma_service=FakeChromaService(
            chroma_counts,
            should_fail=chroma_should_fail,
        ),
        sqlite_store=sqlite_store,
        documents_directory=str(docs_dir),
    )
    return service, sqlite_store, docs_dir


def test_clean_state_returns_ok(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    stored_path = save_uploaded_file(b"hello", "sample.txt", str(docs_dir))

    service, _, _ = build_service(
        tmp_path,
        registry_entries=[
            {
                "id": "doc-1",
                "filename": "sample.txt",
                "stored_path": stored_path,
                "total_chunks": 1,
            }
        ],
        chroma_counts={"doc-1": 2},
    )

    report = service.run_report()

    assert report["status"] == "ok"
    assert report["summary"]["chroma_documents"] == 1
    assert report["summary"]["issues"] == 0
    assert report["issues"] == []


def test_reconciliation_includes_chroma_collections(tmp_path: Path):
    service, _, _ = build_service(
        tmp_path,
        registry_entries=[],
        chroma_counts={"doc-1": 1},
    )
    service.chroma_service.collections = {
        "rag_chat": {"doc-legacy": 2},
        "rag_local_hash_local_hash_v1_384": {"doc-1": 1},
    }
    service.chroma_service.collection_name = "rag_local_hash_local_hash_v1_384"

    report = service.run_report()

    assert report["summary"]["active_chroma_collection"] == "rag_local_hash_local_hash_v1_384"
    assert "rag_chat" in report["summary"]["chroma_collections"]
    assert report["summary"]["chroma_collections"]["rag_chat"]["doc-legacy"] == 2


def test_registry_missing_file_is_detected(tmp_path: Path):
    service, _, _ = build_service(
        tmp_path,
        registry_entries=[
            {
                "id": "doc-1",
                "filename": "missing.txt",
                "stored_path": str(tmp_path / "docs" / "missing.txt"),
                "total_chunks": 1,
            }
        ],
        chroma_counts={"doc-1": 1},
    )

    report = service.run_report()

    issue_types = [issue["type"] for issue in report["issues"]]
    assert "registry_missing_file" in issue_types
    assert report["status"] == "drift_detected"


def test_registry_missing_vectors_is_detected(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    stored_path = save_uploaded_file(b"hello", "sample.txt", str(docs_dir))

    service, _, _ = build_service(
        tmp_path,
        registry_entries=[
            {
                "id": "doc-1",
                "filename": "sample.txt",
                "stored_path": stored_path,
                "total_chunks": 1,
            }
        ],
        chroma_counts={},
    )

    report = service.run_report()

    issue_types = [issue["type"] for issue in report["issues"]]
    assert "registry_missing_vectors" in issue_types


def test_orphan_chroma_vectors_are_detected(tmp_path: Path):
    service, _, _ = build_service(
        tmp_path,
        registry_entries=[],
        chroma_counts={"orphan-doc": 3},
    )

    report = service.run_report()

    issue = next(
        issue for issue in report["issues"] if issue["type"] == "orphan_chroma_vectors"
    )
    assert issue["document_id"] == "orphan-doc"
    assert "3 chunk" in issue["details"]


def test_orphan_file_is_detected(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    orphan_path = save_uploaded_file(b"orphan", "orphan.txt", str(docs_dir))

    service, _, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})

    report = service.run_report()

    issue = next(issue for issue in report["issues"] if issue["type"] == "orphan_file")
    assert "orphan.txt" in issue["details"]


def test_orphan_file_skipped_when_referenced_by_recoverable_job(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    stored_path = save_uploaded_file(b"retry me", "retry.txt", str(docs_dir))

    service, sqlite_store, _ = build_service(
        tmp_path,
        registry_entries=[],
        chroma_counts={},
    )
    sqlite_store.create_upload_job(
        filename="retry.txt",
        file_size=8,
        stored_path=stored_path,
    )
    job = sqlite_store.list_upload_jobs()[0]
    sqlite_store.update_upload_job(job["id"], status="failed", error="temporary")

    report = service.run_report()

    assert "orphan_file" not in [issue["type"] for issue in report["issues"]]


def test_upload_job_missing_document_is_detected(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="sample.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "sample.txt"),
    )
    job = sqlite_store.list_upload_jobs()[0]
    sqlite_store.update_upload_job(
        job["id"],
        status="completed",
        document_id="missing-doc",
    )

    report = service.run_report()

    issue = next(
        issue
        for issue in report["issues"]
        if issue["type"] == "upload_job_missing_document"
    )
    assert issue["document_id"] == "missing-doc"
    assert issue["job_id"] == job["id"]


def test_upload_job_missing_file_is_detected(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )

    report = service.run_report()

    issue = next(
        issue for issue in report["issues"] if issue["type"] == "upload_job_missing_file"
    )
    assert issue["severity"] == "error"


def test_report_summary_counts_are_correct(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    stored_path = save_uploaded_file(b"hello", "sample.txt", str(docs_dir))
    save_uploaded_file(b"orphan", "orphan.txt", str(docs_dir))

    service, sqlite_store, _ = build_service(
        tmp_path,
        registry_entries=[
            {
                "id": "doc-1",
                "filename": "sample.txt",
                "stored_path": stored_path,
                "total_chunks": 1,
            }
        ],
        chroma_counts={"doc-1": 1, "orphan-doc": 2},
    )
    sqlite_store.create_upload_job(
        filename="sample.txt",
        file_size=5,
        stored_path=stored_path,
    )

    report = service.run_report()

    assert report["summary"]["registry_documents"] == 1
    assert report["summary"]["filesystem_files"] == 2
    assert report["summary"]["chroma_documents"] == 2
    assert report["summary"]["upload_jobs"] == 1
    assert report["summary"]["issues"] == len(report["issues"])
    assert report["summary"]["issues"] > 0


def test_chroma_inspection_failure_returns_error_report(tmp_path: Path):
    service, _, _ = build_service(
        tmp_path,
        registry_entries=[],
        chroma_should_fail=True,
    )

    report = service.run_report()

    assert report["status"] == "error"
    assert report["error"] == "Chroma unavailable"


def test_repair_plan_clean_state_has_no_actions(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    stored_path = save_uploaded_file(b"hello", "sample.txt", str(docs_dir))

    service, _, _ = build_service(
        tmp_path,
        registry_entries=[
            {
                "id": "doc-1",
                "filename": "sample.txt",
                "stored_path": stored_path,
                "total_chunks": 1,
            }
        ],
        chroma_counts={"doc-1": 1},
    )

    result = service.run_repair(dry_run=True)

    assert result["repair_plan"]["status"] == "ok"
    assert result["repair_plan"]["actions"] == []
    assert result["repair_plan"]["dry_run"] is True


def test_repair_plan_upload_job_missing_document(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="sample.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "sample.txt"),
    )
    job = sqlite_store.list_upload_jobs()[0]
    sqlite_store.update_upload_job(
        job["id"],
        status="completed",
        document_id="missing-doc",
    )

    result = service.run_repair(dry_run=True)
    action_types = [action["type"] for action in result["repair_plan"]["actions"]]

    assert ACTION_CLEAR_JOB_DOCUMENT_REFERENCE in action_types
    assert result["repair_plan"]["actions"][0]["will_apply"] is True


def test_repair_plan_upload_job_missing_file(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )

    result = service.run_repair(dry_run=True)
    action = next(
        action
        for action in result["repair_plan"]["actions"]
        if action["type"] == ACTION_MARK_JOB_MISSING_FILE_FAILED
    )

    assert action["will_apply"] is True


def test_repair_plan_orphan_chroma_vectors_is_manual_review(tmp_path: Path):
    service, _, _ = build_service(
        tmp_path,
        registry_entries=[],
        chroma_counts={"orphan-doc": 2},
    )

    result = service.run_repair(dry_run=True)
    action = next(
        action
        for action in result["repair_plan"]["actions"]
        if action["issue_type"] == "orphan_chroma_vectors"
    )

    assert action["type"] == ACTION_MANUAL_REVIEW
    assert action["will_apply"] is False


def test_repair_plan_orphan_file_is_manual_review(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    save_uploaded_file(b"orphan", "orphan.txt", str(docs_dir))

    service, _, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})

    result = service.run_repair(dry_run=True)
    action = next(
        action
        for action in result["repair_plan"]["actions"]
        if action["issue_type"] == "orphan_file"
    )

    assert action["type"] == ACTION_MANUAL_REVIEW
    assert action["will_apply"] is False


def test_repair_plan_registry_missing_vectors_with_file_is_manual_review(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    stored_path = save_uploaded_file(b"hello", "sample.txt", str(docs_dir))

    service, _, _ = build_service(
        tmp_path,
        registry_entries=[
            {
                "id": "doc-1",
                "filename": "sample.txt",
                "stored_path": stored_path,
                "total_chunks": 1,
            }
        ],
        chroma_counts={},
    )

    result = service.run_repair(dry_run=True)
    action = next(
        action
        for action in result["repair_plan"]["actions"]
        if action["issue_type"] == "registry_missing_vectors"
    )

    assert action["type"] == ACTION_MANUAL_REVIEW
    assert action["will_apply"] is False


def test_repair_plan_does_not_expose_absolute_paths(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )

    result = service.run_repair(dry_run=True)

    assert "C:\\" not in str(result["repair_plan"])
    assert str(tmp_path) not in str(result["repair_plan"])


def test_repair_dry_run_does_not_mutate_sqlite(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )
    job = sqlite_store.list_upload_jobs()[0]
    sqlite_store.update_upload_job(
        job["id"],
        status="completed",
        document_id="missing-doc",
    )
    before = sqlite_store.get_upload_job(job["id"])

    service.run_repair(dry_run=True)

    after = sqlite_store.get_upload_job(job["id"])
    assert after == before


def test_repair_apply_clears_stale_upload_job_document_reference(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="sample.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "sample.txt"),
    )
    job = sqlite_store.list_upload_jobs()[0]
    sqlite_store.update_upload_job(
        job["id"],
        status="completed",
        document_id="missing-doc",
    )

    result = service.run_repair(dry_run=False)

    updated = sqlite_store.get_upload_job(job["id"])
    assert updated["document_id"] is None
    applied = [
        action
        for action in result["repair_plan"]["actions"]
        if action["type"] == ACTION_CLEAR_JOB_DOCUMENT_REFERENCE
    ]
    assert applied[0]["applied"] is True


def test_repair_apply_marks_missing_file_job_failed(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )
    job = sqlite_store.list_upload_jobs()[0]

    result = service.run_repair(dry_run=False)

    updated = sqlite_store.get_upload_job(job["id"])
    assert updated["status"] == "failed"
    assert updated["error"] == MISSING_UPLOAD_FILE_ERROR
    action = next(
        action
        for action in result["repair_plan"]["actions"]
        if action["type"] == ACTION_MARK_JOB_MISSING_FILE_FAILED
    )
    assert action["applied"] is True


def test_repair_apply_is_idempotent(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )

    first = service.run_repair(dry_run=False)
    second = service.run_repair(dry_run=False)

    first_applied = sum(
        1 for action in first["repair_plan"]["actions"] if action.get("applied")
    )
    second_applied = sum(
        1 for action in second["repair_plan"]["actions"] if action.get("applied")
    )
    assert first_applied >= 1
    assert second_applied == 0


def test_repair_apply_continues_after_single_action_failure(tmp_path: Path):
    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="a.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "a.txt"),
    )
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )
    job_a = sqlite_store.list_upload_jobs()[0]
    sqlite_store.update_upload_job(
        job_a["id"],
        status="completed",
        document_id="missing-doc",
    )

    original_clear = sqlite_store.clear_upload_job_document_reference_for_job

    def failing_clear(job_id: str, *, expected_document_id: str | None = None) -> bool:
        if job_id == job_a["id"]:
            raise RuntimeError("simulated failure")
        return original_clear(job_id, expected_document_id=expected_document_id)

    sqlite_store.clear_upload_job_document_reference_for_job = failing_clear

    result = service.run_repair(dry_run=False)

    failed_actions = [
        action for action in result["repair_plan"]["actions"] if action.get("error")
    ]
    applied_actions = [
        action for action in result["repair_plan"]["actions"] if action.get("applied")
    ]
    assert failed_actions
    assert applied_actions
    assert result["repair_plan"]["summary"]["failed"] >= 1
    assert result["repair_plan"]["summary"]["applied"] >= 1


def test_stale_registry_cleanup_not_applied_by_default(tmp_path: Path):
    service, _, _ = build_service(
        tmp_path,
        registry_entries=[
            {
                "id": "doc-1",
                "filename": "missing.txt",
                "stored_path": str(tmp_path / "docs" / "missing.txt"),
                "total_chunks": 1,
            }
        ],
        chroma_counts={},
    )

    result = service.run_repair(dry_run=False)
    stale_actions = [
        action
        for action in result["repair_plan"]["actions"]
        if action["type"] == ACTION_REMOVE_STALE_REGISTRY_ENTRY
    ]

    assert stale_actions
    assert stale_actions[0]["will_apply"] is False
    assert stale_actions[0]["applied"] is False
    assert len(service.registry.list_all()) == 1


def test_stale_registry_cleanup_applied_when_opted_in(tmp_path: Path):
    service, _, _ = build_service(
        tmp_path,
        registry_entries=[
            {
                "id": "doc-1",
                "filename": "missing.txt",
                "stored_path": str(tmp_path / "docs" / "missing.txt"),
                "total_chunks": 1,
            }
        ],
        chroma_counts={},
    )

    result = service.run_repair(
        dry_run=False,
        include_stale_registry_cleanup=True,
    )
    stale_actions = [
        action
        for action in result["repair_plan"]["actions"]
        if action["type"] == ACTION_REMOVE_STALE_REGISTRY_ENTRY
    ]

    assert stale_actions[0]["applied"] is True
    assert service.registry.list_all() == []


def test_repair_increments_metrics(tmp_path: Path):
    from services.metrics import LocalMetrics, reset_local_metrics

    reset_local_metrics()
    metrics = LocalMetrics()

    service, sqlite_store, _ = build_service(tmp_path, registry_entries=[], chroma_counts={})
    sqlite_store.create_upload_job(
        filename="missing.txt",
        file_size=4,
        stored_path=str(tmp_path / "docs" / "missing.txt"),
    )

    with patch("services.reconciliation.get_local_metrics", return_value=metrics):
        service.run_repair(dry_run=True)

    snapshot = metrics.snapshot()
    assert snapshot["counters"].get("reconciliation.repair.plan", 0) >= 1
