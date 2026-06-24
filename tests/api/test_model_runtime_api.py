from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_models import router as models_router
from core.dependencies import get_local_metrics_service, get_model_runtime_service
from services.metrics import LocalMetrics
from services.model_catalog import load_model_catalog
from services.model_runtime import ModelRuntimeError, ModelRuntimeService
from services.model_settings import ModelSettingsService
from services.ollama_service import OllamaService
from tests.services.test_model_runtime import FakeOllamaRuntime


def build_runtime_client(runtime: ModelRuntimeService):
    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_model_runtime_service] = lambda: runtime
    app.dependency_overrides[get_local_metrics_service] = lambda: LocalMetrics()
    return TestClient(app)


@pytest.fixture
def runtime_service(tmp_path: Path) -> ModelRuntimeService:
    settings = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: ["llama3.1:8b", "qwen3:8b"],
        catalog_loader=load_model_catalog,
    )
    return ModelRuntimeService(
        ollama_service=FakeOllamaRuntime(),
        model_settings=settings,
        keep_alive="5m",
    )


def test_get_model_runtime_returns_status(runtime_service: ModelRuntimeService):
    with build_runtime_client(runtime_service) as client:
        response = client.get("/models/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ollama"]["reachable"] is True
    assert payload["runtime"]["keep_alive"] == "5m"
    assert "loaded_detection" in payload["runtime"]
    assert "running_models" in payload
    assert "loaded" in payload["active_model"]


def test_post_model_runtime_preload_success(runtime_service: ModelRuntimeService):
    with build_runtime_client(runtime_service) as client:
        response = client.post("/models/runtime/preload")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["model"] == "llama3.1:8b"
    assert payload["runtime"]["active_model"]["name"] == "llama3.1:8b"


def test_post_model_runtime_preload_not_installed(tmp_path: Path):
    settings = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: ["llama3.1:8b"],
        catalog_loader=load_model_catalog,
    )
    settings.update_chat_model("mistral:7b", require_installed=False)
    runtime = ModelRuntimeService(
        ollama_service=FakeOllamaRuntime(installed=["llama3.1:8b"]),
        model_settings=settings,
        keep_alive="5m",
    )

    with build_runtime_client(runtime) as client:
        response = client.post("/models/runtime/preload")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["status"] == "error"
    assert "ollama pull" in detail["message"].lower()


def test_post_model_runtime_unload_success(runtime_service: ModelRuntimeService):
    with build_runtime_client(runtime_service) as client:
        response = client.post("/models/runtime/unload")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "remains unchanged" in payload["message"]
    assert "runtime" in payload


def test_get_model_runtime_records_ps_metrics(runtime_service: ModelRuntimeService):
    metrics = LocalMetrics()
    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_model_runtime_service] = lambda: runtime_service
    app.dependency_overrides[get_local_metrics_service] = lambda: metrics

    with TestClient(app) as client:
        response = client.get("/models/runtime")

    assert response.status_code == 200
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["models.runtime.ps_success"] == 1
    assert snapshot["last_values"]["models.runtime.loaded_detection"] == "available"


def test_post_model_runtime_preload_increments_metrics(runtime_service: ModelRuntimeService):
    metrics = LocalMetrics()
    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_model_runtime_service] = lambda: runtime_service
    app.dependency_overrides[get_local_metrics_service] = lambda: metrics

    with TestClient(app) as client:
        response = client.post("/models/runtime/preload")

    assert response.status_code == 200
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["models.runtime.preload"] == 1


def test_chat_generation_passes_keep_alive(tmp_path: Path):
    from services.chat_service import ChatService
    from langchain_core.documents import Document
    import asyncio

    class TrackingOllama(OllamaService):
        def __init__(self) -> None:
            super().__init__(
                base_url="http://127.0.0.1:11434",
                model="llama3.1:8b",
                keep_alive="5m",
            )
            self.last_keep_alive = None

        async def generate(self, prompt: str, model: str | None = None) -> str:
            self.last_keep_alive = self.keep_alive
            return "ok"

    ollama = TrackingOllama()
    chroma = MagicMock()
    chat = ChatService(chroma_service=chroma, ollama_service=ollama, top_k=3, max_context_chunks=3)
    chat.retriever = MagicMock()
    chat.retriever.top_k = 3
    chat.retriever.enable_hybrid = False
    chat.retriever.search.return_value = [
        Document(
            page_content="ctx",
            metadata={
                "source": "sample.md",
                "chunk_id": "sample.md:0",
                "chunk_index": 0,
                "document_id": "sample",
                "_retrieval_score": 0.9,
                "_retrieval_rank": 1,
                "_retrieval_score_type": "distance",
            },
        )
    ]

    result = asyncio.run(chat.ask("question?"))

    assert ollama.last_keep_alive == "5m"
    assert result["debug"]["generation"]["keep_alive"] == "5m"
