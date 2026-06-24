import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.observability import log_structured, safe_ingestion_error_message
from services.metrics import get_local_metrics
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.sqlite_store import SQLiteStore

logger = logging.getLogger("uvicorn.error")

RECOVERABLE_JOB_STATUSES = frozenset({"queued", "processing", "failed"})

MISSING_UPLOAD_FILE_ERROR = (
    "Source file is missing. Please re-upload the document."
)

ACTION_CLEAR_JOB_DOCUMENT_REFERENCE = "clear_upload_job_document_reference"
ACTION_MARK_JOB_MISSING_FILE_FAILED = "mark_upload_job_missing_file_failed"
ACTION_REMOVE_STALE_REGISTRY_ENTRY = "remove_stale_registry_entry"
ACTION_MANUAL_REVIEW = "manual_review"


class PersistenceReconciliationService:
    def __init__(
        self,
        registry: DocumentRegistry,
        chroma_service: ChromaService,
        sqlite_store: SQLiteStore,
        documents_directory: str,
    ) -> None:
        self.registry = registry
        self.chroma_service = chroma_service
        self.sqlite_store = sqlite_store
        self.documents_directory = documents_directory

    def run_report(self) -> dict[str, Any]:
        trace_id = str(uuid.uuid4())
        log_structured("persistence.reconciliation.started", trace_id, {})

        try:
            report = self._build_report(trace_id)
        except Exception as exc:
            logger.exception("Persistence reconciliation failed.")
            report = {
                "status": "error",
                "trace_id": trace_id,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "registry_documents": 0,
                    "filesystem_files": 0,
                    "chroma_documents": 0,
                    "upload_jobs": 0,
                    "issues": 0,
                },
                "issues": [],
                "error": safe_ingestion_error_message(exc),
            }
            get_local_metrics().increment("reconciliation.failed")
            get_local_metrics().set_last("reconciliation.status", "error")
            log_structured(
                "persistence.reconciliation.failed",
                trace_id,
                {"error": str(exc)},
            )
            return report

        self.log_report(report)
        return report

    def log_report(self, report: dict[str, Any]) -> None:
        trace_id = report.get("trace_id", "reconciliation")
        summary = report.get("summary", {})
        issue_count = summary.get("issues", 0)
        metrics = get_local_metrics()
        metrics.increment("reconciliation.runs")
        metrics.set_last("reconciliation.status", report.get("status"))
        metrics.set_last("reconciliation.issues", issue_count)

        payload = {
            "status": report.get("status"),
            "issue_count": summary.get("issues", 0),
            "registry_documents": summary.get("registry_documents", 0),
            "chroma_documents": summary.get("chroma_documents", 0),
            "filesystem_files": summary.get("filesystem_files", 0),
            "upload_jobs": summary.get("upload_jobs", 0),
        }

        if report.get("status") == "error":
            metrics.increment("reconciliation.failed")
            log_structured(
                "persistence.reconciliation.failed",
                trace_id,
                {**payload, "error": report.get("error", "unknown error")},
            )
            return

        if report.get("status") == "drift_detected":
            metrics.increment("reconciliation.drift_detected")
            log_structured("persistence.reconciliation.drift_detected", trace_id, payload)
            return

        metrics.increment("reconciliation.completed")
        log_structured("persistence.reconciliation.completed", trace_id, payload)

    def _build_report(self, trace_id: str) -> dict[str, Any]:
        registry_entries = self.registry.list_all()
        upload_jobs = self.sqlite_store.list_upload_jobs()
        recoverable_jobs = self.sqlite_store.list_recoverable_upload_jobs()
        filesystem_files = self._list_filesystem_files()
        chroma_counts = self.chroma_service.list_document_ids_with_vector_counts()

        registry_by_id = {entry["id"]: entry for entry in registry_entries}
        registry_paths = {
            self._normalize_path(entry["stored_path"])
            for entry in registry_entries
            if entry.get("stored_path")
        }
        recoverable_paths = {
            self._normalize_path(job["stored_path"])
            for job in recoverable_jobs
            if job.get("stored_path")
        }

        issues: list[dict[str, Any]] = []

        for entry in registry_entries:
            document_id = entry["id"]
            stored_path = entry.get("stored_path")
            relative_path = self._storage_relative_path(stored_path)

            if stored_path and not os.path.exists(stored_path):
                issues.append(
                    self._issue(
                        issue_type="registry_missing_file",
                        severity="warning",
                        document_id=document_id,
                        details=f"Registry entry references missing file '{relative_path}'.",
                        suggested_action=(
                            "Re-upload the document or run a future repair to remove "
                            "the stale registry entry."
                        ),
                    )
                )

            vector_count = chroma_counts.get(document_id, 0)
            if vector_count == 0:
                issues.append(
                    self._issue(
                        issue_type="registry_missing_vectors",
                        severity="warning",
                        document_id=document_id,
                        details=(
                            f"Registry entry '{entry.get('filename', document_id)}' "
                            "has no Chroma vectors."
                        ),
                        suggested_action=(
                            "Reindex the document if the raw file still exists; "
                            "future repair can enqueue reindex."
                        ),
                    )
                )

        for document_id, vector_count in chroma_counts.items():
            if document_id not in registry_by_id:
                issues.append(
                    self._issue(
                        issue_type="orphan_chroma_vectors",
                        severity="warning",
                        document_id=document_id,
                        details=(
                            f"Chroma contains {vector_count} chunk(s) for document_id "
                            f"'{document_id}' with no registry entry."
                        ),
                        suggested_action=(
                            "Future repair can delete orphan vectors after confirmation."
                        ),
                    )
                )

        for file_path in filesystem_files:
            normalized_path = self._normalize_path(file_path)
            if normalized_path in registry_paths:
                continue
            if normalized_path in recoverable_paths:
                continue

            relative_path = self._storage_relative_path(file_path)
            issues.append(
                self._issue(
                    issue_type="orphan_file",
                    severity="info",
                    details=f"File '{relative_path}' is not referenced by the registry.",
                    suggested_action=(
                        "Future repair can delete the orphan file after confirmation."
                    ),
                )
            )

        for job in self.sqlite_store.list_upload_jobs_with_document_id():
            document_id = job.get("document_id")
            if not document_id:
                continue
            if document_id not in registry_by_id:
                issues.append(
                    self._issue(
                        issue_type="upload_job_missing_document",
                        severity="warning",
                        document_id=document_id,
                        job_id=job["id"],
                        details=(
                            f"Upload job '{job['id']}' references missing document_id "
                            f"'{document_id}'."
                        ),
                        suggested_action=(
                            "Future repair can clear upload_jobs.document_id for this job."
                        ),
                    )
                )

        for job in recoverable_jobs:
            stored_path = job.get("stored_path")
            if not stored_path:
                continue
            if os.path.exists(stored_path):
                continue

            relative_path = self._storage_relative_path(stored_path)
            issues.append(
                self._issue(
                    issue_type="upload_job_missing_file",
                    severity="error",
                    job_id=job["id"],
                    details=(
                        f"Recoverable upload job '{job['id']}' ({job['status']}) "
                        f"references missing file '{relative_path}'."
                    ),
                    suggested_action=(
                        "Re-upload the document or mark the job failed with a safe message."
                    ),
                )
            )

        status = "ok" if not issues else "drift_detected"
        return {
            "status": status,
            "trace_id": trace_id,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "registry_documents": len(registry_entries),
                "filesystem_files": len(filesystem_files),
                "chroma_documents": len(chroma_counts),
                "upload_jobs": len(upload_jobs),
                "issues": len(issues),
            },
            "issues": issues,
        }

    def _list_filesystem_files(self) -> list[str]:
        directory = Path(self.documents_directory)
        if not directory.exists():
            return []

        return [
            str(path)
            for path in directory.iterdir()
            if path.is_file()
        ]

    def _normalize_path(self, path: str | None) -> str:
        if not path:
            return ""
        return os.path.normcase(os.path.normpath(path))

    def _storage_relative_path(self, path: str | None) -> str:
        if not path:
            return ""
        try:
            return os.path.relpath(path, self.documents_directory)
        except ValueError:
            return os.path.basename(path)

    @staticmethod
    def _issue(
        *,
        issue_type: str,
        severity: str,
        details: str,
        suggested_action: str,
        document_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        issue: dict[str, Any] = {
            "type": issue_type,
            "severity": severity,
            "details": details,
            "suggested_action": suggested_action,
        }
        if document_id is not None:
            issue["document_id"] = document_id
        if job_id is not None:
            issue["job_id"] = job_id
        return issue

    def build_repair_plan(
        self,
        report: dict[str, Any],
        *,
        dry_run: bool = True,
        include_stale_registry_cleanup: bool = False,
    ) -> dict[str, Any]:
        issues = report.get("issues") or []
        actions: list[dict[str, Any]] = []
        handled_stale_registry: set[str] = set()

        missing_file_docs = {
            issue["document_id"]
            for issue in issues
            if issue.get("type") == "registry_missing_file" and issue.get("document_id")
        }
        missing_vector_docs = {
            issue["document_id"]
            for issue in issues
            if issue.get("type") == "registry_missing_vectors" and issue.get("document_id")
        }
        stale_registry_docs = missing_file_docs & missing_vector_docs

        for issue in issues:
            issue_type = issue.get("type")
            if issue_type == "upload_job_missing_document":
                job_id = issue["job_id"]
                document_id = issue.get("document_id")
                actions.append(
                    self._repair_action(
                        action_type=ACTION_CLEAR_JOB_DOCUMENT_REFERENCE,
                        issue_type=issue_type,
                        severity="safe",
                        description="Clear stale document reference from upload job.",
                        will_apply=True,
                        job_id=job_id,
                        document_id=document_id,
                    )
                )
            elif issue_type == "upload_job_missing_file":
                actions.append(
                    self._repair_action(
                        action_type=ACTION_MARK_JOB_MISSING_FILE_FAILED,
                        issue_type=issue_type,
                        severity="safe",
                        description="Mark upload job failed because source file is missing.",
                        will_apply=True,
                        job_id=issue["job_id"],
                    )
                )
            elif issue_type == "registry_missing_file":
                document_id = issue.get("document_id")
                if document_id in stale_registry_docs:
                    if document_id in handled_stale_registry:
                        continue
                    handled_stale_registry.add(document_id)
                    actions.append(
                        self._repair_action(
                            action_type=ACTION_REMOVE_STALE_REGISTRY_ENTRY,
                            issue_type="registry_stale_entry",
                            severity="medium",
                            description=(
                                "Remove stale registry entry with missing file and no vectors."
                            ),
                            will_apply=include_stale_registry_cleanup,
                            document_id=document_id,
                        )
                    )
                else:
                    actions.append(
                        self._repair_action(
                            action_type=ACTION_MANUAL_REVIEW,
                            issue_type=issue_type,
                            severity="manual_review",
                            description="Registry entry references missing file but vectors may remain.",
                            will_apply=False,
                            document_id=document_id,
                        )
                    )
            elif issue_type == "registry_missing_vectors":
                document_id = issue.get("document_id")
                if document_id in stale_registry_docs:
                    continue
                actions.append(
                    self._repair_action(
                        action_type=ACTION_MANUAL_REVIEW,
                        issue_type=issue_type,
                        severity="manual_review",
                        description="Registry entry has no vectors; reindex may be required.",
                        will_apply=False,
                        document_id=document_id,
                    )
                )
            elif issue_type in {"orphan_chroma_vectors", "orphan_file"}:
                actions.append(
                    self._repair_action(
                        action_type=ACTION_MANUAL_REVIEW,
                        issue_type=issue_type,
                        severity="manual_review",
                        description=issue.get("suggested_action", "Manual review required."),
                        will_apply=False,
                        document_id=issue.get("document_id"),
                        job_id=issue.get("job_id"),
                    )
                )

        repairable = sum(1 for action in actions if action["will_apply"])
        manual_review = sum(
            1 for action in actions if action["severity"] == "manual_review"
        )
        unsupported = sum(
            1
            for action in actions
            if action["severity"] == "medium" and not action["will_apply"]
        )

        if not actions:
            status = "ok"
        elif repairable > 0:
            status = "repair_available"
        elif manual_review > 0 or unsupported > 0:
            status = "manual_review_required"
        else:
            status = "ok"

        return {
            "status": status,
            "dry_run": dry_run,
            "summary": {
                "issues": len(issues),
                "repairable": repairable,
                "manual_review": manual_review,
                "unsupported": unsupported,
                "applied": 0,
                "failed": 0,
            },
            "actions": actions,
        }

    def apply_repair_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        applied_count = 0
        failed_count = 0

        for action in plan.get("actions", []):
            if not action.get("will_apply"):
                continue

            try:
                did_apply = self._apply_repair_action(action)
                action["applied"] = did_apply
                action["error"] = None
                if did_apply:
                    applied_count += 1
            except Exception as exc:
                logger.exception("Repair action failed: %s", action.get("action_id"))
                action["applied"] = False
                action["error"] = safe_ingestion_error_message(exc)
                failed_count += 1

        summary = dict(plan.get("summary", {}))
        summary["applied"] = applied_count
        summary["failed"] = failed_count
        plan["summary"] = summary
        plan["dry_run"] = False
        return plan

    def run_repair(
        self,
        *,
        dry_run: bool = True,
        include_stale_registry_cleanup: bool = False,
    ) -> dict[str, Any]:
        trace_id = str(uuid.uuid4())
        metrics = get_local_metrics()
        log_structured(
            "persistence.reconciliation.repair_plan.started",
            trace_id,
            {"dry_run": dry_run},
        )

        try:
            report = self._build_report(trace_id)
            plan = self.build_repair_plan(
                report,
                dry_run=dry_run,
                include_stale_registry_cleanup=include_stale_registry_cleanup,
            )

            if dry_run:
                metrics.increment("reconciliation.repair.plan")
                if plan["summary"]["manual_review"] > 0:
                    metrics.increment(
                        "reconciliation.repair.manual_review",
                        plan["summary"]["manual_review"],
                    )
                metrics.set_last("reconciliation.repair.last_status", plan["status"])
                log_structured(
                    "persistence.reconciliation.repair_plan.completed",
                    trace_id,
                    {
                        "status": plan["status"],
                        "repairable": plan["summary"]["repairable"],
                        "manual_review": plan["summary"]["manual_review"],
                    },
                )
                return {"report": report, "repair_plan": plan}

            log_structured("persistence.reconciliation.repair_apply.started", trace_id, {})
            plan = self.apply_repair_plan(plan)
            metrics.increment("reconciliation.repair.applied", plan["summary"]["applied"])
            if plan["summary"]["failed"]:
                metrics.increment("reconciliation.repair.failed", plan["summary"]["failed"])
            metrics.set_last("reconciliation.repair.last_status", plan["status"])
            metrics.set_last("reconciliation.repair.last_applied", plan["summary"]["applied"])
            metrics.set_last("reconciliation.repair.last_failed", plan["summary"]["failed"])
            log_structured(
                "persistence.reconciliation.repair_apply.completed",
                trace_id,
                {
                    "applied": plan["summary"]["applied"],
                    "failed": plan["summary"]["failed"],
                },
            )
            return {"report": report, "repair_plan": plan}
        except Exception as exc:
            metrics.increment("reconciliation.repair.failed")
            log_structured(
                "persistence.reconciliation.repair_apply.failed",
                trace_id,
                {"error": safe_ingestion_error_message(exc)},
            )
            raise

    def _apply_repair_action(self, action: dict[str, Any]) -> bool:
        action_type = action["type"]

        if action_type == ACTION_CLEAR_JOB_DOCUMENT_REFERENCE:
            return self.sqlite_store.clear_upload_job_document_reference_for_job(
                action["job_id"],
                expected_document_id=action.get("document_id"),
            )

        if action_type == ACTION_MARK_JOB_MISSING_FILE_FAILED:
            job = self.sqlite_store.get_upload_job(action["job_id"])
            if job is None or job.get("status") not in RECOVERABLE_JOB_STATUSES:
                return False
            return self.sqlite_store.mark_upload_job_failed_safe(
                action["job_id"],
                error_message=MISSING_UPLOAD_FILE_ERROR,
            )

        if action_type == ACTION_REMOVE_STALE_REGISTRY_ENTRY:
            document_id = action.get("document_id")
            if not document_id:
                return False
            removed = self.registry.remove(document_id)
            return removed is not None

        return False

    @staticmethod
    def _repair_action(
        *,
        action_type: str,
        issue_type: str,
        severity: str,
        description: str,
        will_apply: bool,
        document_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        action_id_parts = [action_type]
        if job_id:
            action_id_parts.append(job_id)
        elif document_id:
            action_id_parts.append(document_id)

        action: dict[str, Any] = {
            "action_id": ":".join(action_id_parts),
            "type": action_type,
            "issue_type": issue_type,
            "severity": severity,
            "description": description,
            "will_apply": will_apply,
            "applied": False,
            "error": None,
        }
        if document_id is not None:
            action["document_id"] = document_id
        if job_id is not None:
            action["job_id"] = job_id
        return action
