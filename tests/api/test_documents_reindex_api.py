from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_documents import router as documents_router
from core.dependencies import get_document_reindex_service
from services.document_reindex import DocumentReindexService


class FakeReindexService:
    def __init__(self) -> None:
        self.plan_calls = 0
        self.run_calls = 0
        self.last_force = False
        self.last_document_ids = None

    def build_reindex_plan(self, *, document_ids=None, force=False, dry_run=True):
        self.plan_calls += 1
        self.last_force = force
        self.last_document_ids = document_ids
        return {
            "dry_run": dry_run,
            "force": force,
            "active_provider": "local_hash",
            "active_model": "local-hash-v1",
            "active_dimension": 384,
            "active_collection": "rag_local_hash_local_hash_v1_384",
            "documents": [
                {
                    "document_id": "doc-1",
                    "filename": "sample.txt",
                    "status": "would_reindex",
                    "reason": "Ready to reindex into the active embeddings collection.",
                }
            ],
            "summary": {
                "total": 1,
                "would_reindex": 1,
                "already_indexed": 0,
                "missing_file": 0,
                "unsupported": 0,
                "errors": 0,
            },
        }

    def run_reindex_plan(self, *, document_ids=None, force=False):
        self.run_calls += 1
        self.last_force = force
        self.last_document_ids = document_ids
        return {
            "dry_run": False,
            "force": force,
            "trace_id": "trace-1",
            "active_provider": "local_hash",
            "active_model": "local-hash-v1",
            "active_dimension": 384,
            "active_collection": "rag_local_hash_local_hash_v1_384",
            "documents": [
                {
                    "document_id": "doc-1",
                    "filename": "sample.txt",
                    "status": "reindexed",
                    "reason": "Indexed 2 chunk(s) into the active collection.",
                    "chunks_indexed": 2,
                }
            ],
            "summary": {
                "total": 1,
                "reindexed": 1,
                "skipped": 0,
                "missing_file": 0,
                "unsupported": 0,
                "failed": 0,
            },
        }


@pytest.fixture
def client():
    service = FakeReindexService()
    app = FastAPI()
    app.include_router(documents_router)
    app.dependency_overrides[get_document_reindex_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client, service


def test_reindex_defaults_to_dry_run(client):
    test_client, service = client
    response = test_client.post("/documents/reindex", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert service.plan_calls == 1
    assert service.run_calls == 0


def test_reindex_empty_body_defaults_to_dry_run(client):
    test_client, service = client
    response = test_client.post("/documents/reindex")

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert service.plan_calls == 1


def test_reindex_run_mode_mutates(client):
    test_client, service = client
    response = test_client.post(
        "/documents/reindex",
        json={"dry_run": False, "force": True, "document_ids": ["doc-1"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is False
    assert service.run_calls == 1
    assert service.last_force is True
    assert service.last_document_ids == ["doc-1"]


def test_reindex_response_has_no_absolute_paths(client, tmp_path: Path):
    test_client, _service = client
    response = test_client.post("/documents/reindex", json={"dry_run": True})

    payload = response.json()
    serialized = str(payload)
    assert str(tmp_path).replace("\\", "/") not in serialized
    assert "page_content" not in serialized
