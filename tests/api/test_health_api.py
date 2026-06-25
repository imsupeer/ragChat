from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_health import router as health_router
from core.dependencies import get_readiness_service


def test_health_ready_returns_dependency_checks():
    readiness = MagicMock()
    readiness.check.return_value = {
        "status": "ok",
        "checks": {
            "sqlite": {"status": "ok"},
            "chroma": {"status": "ok", "document_count": 2},
            "upload_queue": {"status": "ok", "worker_alive": True},
            "reconciliation": {"status": "ok"},
            "ollama": {"status": "ok"},
            "embeddings": {"status": "ok", "provider": "ollama"},
        },
    }

    app = FastAPI()
    app.include_router(health_router)
    app.dependency_overrides[get_readiness_service] = lambda: readiness

    with TestClient(app) as client:
        health = client.get("/health/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    readiness.check.assert_called_once()


def test_health_ready_reports_degraded_when_ollama_unavailable():
    readiness = MagicMock()
    readiness.check.return_value = {
        "status": "degraded",
        "checks": {
            "sqlite": {"status": "ok"},
            "chroma": {"status": "ok", "document_count": 0},
            "upload_queue": {"status": "ok", "worker_alive": True},
            "reconciliation": {"status": "ok"},
            "ollama": {"status": "degraded", "message": "Ollama unavailable"},
            "embeddings": {"status": "ok", "provider": "ollama"},
        },
    }

    app = FastAPI()
    app.include_router(health_router)
    app.dependency_overrides[get_readiness_service] = lambda: readiness

    with TestClient(app) as client:
        response = client.get("/health/ready")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "degraded"
    assert "C:\\" not in str(payload)


def test_readiness_service_marks_sqlite_error(tmp_path):
    from core.config import Settings
    from services.chroma_service import ChromaService
    from services.metrics import LocalMetrics
    from services.readiness import ReadinessService
    from services.sqlite_store import SQLiteStore
    from services.upload_queue import UploadQueueService

    class FailingSQLite(SQLiteStore):
        def ping(self) -> None:
            raise RuntimeError("db down")

    class FakeChroma:
        def list_document_ids_with_vector_counts(self):
            return {}

    class FakeQueue:
        @property
        def is_worker_alive(self) -> bool:
            return True

    service = ReadinessService(
        settings=Settings(sqlite_path=str(tmp_path / "app.db")),
        sqlite_store=FailingSQLite(str(tmp_path / "app.db")),
        chroma_service=FakeChroma(),
        upload_queue=FakeQueue(),
        metrics=LocalMetrics(),
    )

    report = service.check()
    assert report["status"] == "error"
    assert report["checks"]["sqlite"]["status"] == "error"


def test_readiness_service_ollama_degraded_without_network_call(tmp_path):
    from core.config import Settings
    from services.metrics import LocalMetrics
    from services.model_catalog import load_model_catalog
    from services.model_runtime import ModelRuntimeService
    from services.model_settings import ModelSettingsService
    from services.readiness import ReadinessService
    from services.sqlite_store import SQLiteStore
    from services.providers.ollama_provider import OllamaProvider
    from tests.services.test_model_runtime import FakeOllamaRuntime

    class FakeChroma:
        def list_document_ids_with_vector_counts(self):
            return {}

    class FakeQueue:
        @property
        def is_worker_alive(self) -> bool:
            return True

    settings_service = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: [],
        catalog_loader=load_model_catalog,
    )
    runtime = ModelRuntimeService(
        llm_provider=OllamaProvider(FakeOllamaRuntime(reachable=False)),
        model_settings=settings_service,
        keep_alive="5m",
    )

    service = ReadinessService(
        settings=Settings(sqlite_path=str(tmp_path / "app.db")),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
        chroma_service=FakeChroma(),
        upload_queue=FakeQueue(),
        metrics=LocalMetrics(),
        model_runtime=runtime,
    )

    report = service.check()

    assert report["checks"]["ollama"]["status"] == "degraded"
    assert report["checks"]["ollama"]["reachable"] is False
    assert report["checks"]["ollama"]["active_chat_model"] == "llama3.1:8b"
    assert report["checks"]["ollama"]["provider"] == "ollama"
    assert report["status"] == "degraded"


def test_readiness_service_reports_embeddings_provider(tmp_path):
    from core.config import Settings
    from services.metrics import LocalMetrics
    from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider
    from services.readiness import ReadinessService
    from services.sqlite_store import SQLiteStore

    class FakeChroma:
        def list_document_ids_with_vector_counts(self):
            return {}

        def list_chunk_metadatas(self):
            return []

    class FakeQueue:
        @property
        def is_worker_alive(self) -> bool:
            return True

    service = ReadinessService(
        settings=Settings(sqlite_path=str(tmp_path / "app.db")),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
        chroma_service=FakeChroma(),
        upload_queue=FakeQueue(),
        metrics=LocalMetrics(),
        embeddings_provider=LocalHashEmbeddingsProvider(),
    )

    report = service.check()
    assert report["checks"]["embeddings"]["provider"] == "local_hash"
    assert report["checks"]["embeddings"]["quality"] == "demo"


def test_readiness_collection_mismatch_warns_without_provider_degradation(tmp_path):
    from core.config import Settings
    from services.metrics import LocalMetrics
    from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider
    from services.readiness import ReadinessService
    from services.sqlite_store import SQLiteStore

    class FakeChroma:
        def list_document_ids_with_vector_counts(self):
            return {"doc-1": 1}

        def list_chunk_metadatas(self):
            return [
                {
                    "embedding_provider": "ollama",
                    "embedding_model": "mxbai-embed-large",
                    "embedding_dimension": 1024,
                }
            ]

    class FakeQueue:
        @property
        def is_worker_alive(self) -> bool:
            return True

    service = ReadinessService(
        settings=Settings(sqlite_path=str(tmp_path / "app.db")),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
        chroma_service=FakeChroma(),
        upload_queue=FakeQueue(),
        metrics=LocalMetrics(),
        embeddings_provider=LocalHashEmbeddingsProvider(),
    )

    report = service.check()
    embeddings_check = report["checks"]["embeddings"]
    assert embeddings_check["status"] == "ok"
    assert embeddings_check["collection"]["status"] == "mixed"
    assert embeddings_check["reindex_recommended"] is True
    assert "collection_warning" in embeddings_check


def test_readiness_service_degrades_for_sentence_transformers_missing_dependency(
    tmp_path, monkeypatch
):
    from core.config import Settings
    from services.metrics import LocalMetrics
    from services.providers.sentence_transformers_embeddings_provider import (
        SentenceTransformersEmbeddingsProvider,
    )
    from services.readiness import ReadinessService
    from services.sqlite_store import SQLiteStore

    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: None,
    )

    class FakeChroma:
        def list_document_ids_with_vector_counts(self):
            return {}

        def list_chunk_metadatas(self):
            return []

    class FakeQueue:
        @property
        def is_worker_alive(self) -> bool:
            return True

    service = ReadinessService(
        settings=Settings(sqlite_path=str(tmp_path / "app.db")),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
        chroma_service=FakeChroma(),
        upload_queue=FakeQueue(),
        metrics=LocalMetrics(),
        embeddings_provider=SentenceTransformersEmbeddingsProvider(),
    )

    report = service.check()
    assert report["checks"]["embeddings"]["status"] == "degraded"
    assert report["checks"]["embeddings"]["provider"] == "sentence_transformers"
    assert report["status"] == "degraded"
