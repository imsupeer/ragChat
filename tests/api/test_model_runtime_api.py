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
from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider
from services.providers.ollama_provider import OllamaProvider
from services.providers.sentence_transformers_embeddings_provider import (
    SentenceTransformersEmbeddingsProvider,
)
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
        llm_provider=OllamaProvider(FakeOllamaRuntime()),
        model_settings=settings,
        keep_alive="5m",
    )


def test_get_model_runtime_returns_status(runtime_service: ModelRuntimeService):
    with build_runtime_client(runtime_service) as client:
        response = client.get("/models/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ollama"]["reachable"] is True
    assert payload["provider"]["name"] == "ollama"
    assert payload["provider"]["display_name"] == "Ollama"
    assert payload["runtime"]["keep_alive"] == "5m"
    assert "loaded_detection" in payload["runtime"]
    assert "running_models" in payload
    assert "loaded" in payload["active_model"]
    assert "local_runtime" not in payload


def test_get_model_runtime_includes_embeddings_provider(runtime_service: ModelRuntimeService):
    class FakeChroma:
        def list_chunk_metadatas(self):
            return [
                {
                    "embedding_provider": "local_hash",
                    "embedding_model": "local-hash-v1",
                    "embedding_dimension": 384,
                }
            ]

        def get_collection_status(self):
            return {
                "strategy": "per_embedding_provider",
                "active_collection": "rag_local_hash_local_hash_v1_384",
            }

    class FakeRegistry:
        def list_all(self):
            return []

    runtime = ModelRuntimeService(
        llm_provider=runtime_service._provider,
        model_settings=runtime_service._model_settings,
        keep_alive="5m",
        embeddings_provider=LocalHashEmbeddingsProvider(),
        chroma_service=FakeChroma(),
        document_registry=FakeRegistry(),
    )
    with build_runtime_client(runtime) as client:
        response = client.get("/models/runtime")

    payload = response.json()
    assert payload["embeddings"]["provider"] == "local_hash"
    assert payload["embeddings"]["quality"] == "demo"
    assert payload["embeddings"]["collection"]["status"] == "ok"
    assert payload["embeddings"]["collection"]["reindex_recommended"] is False
    assert payload["embeddings"]["collection"]["strategy"] == "per_embedding_provider"
    assert (
        payload["embeddings"]["collection"]["active_collection"]
        == "rag_local_hash_local_hash_v1_384"
    )
    assert payload["embeddings"]["reindex"]["recommended"] is False


def test_get_model_runtime_includes_sentence_transformers_embeddings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.sentence_transformers_runtime.import_sentence_transformer_class",
        lambda: None,
    )
    runtime = ModelRuntimeService(
        llm_provider=OllamaProvider(FakeOllamaRuntime()),
        model_settings=ModelSettingsService(
            settings_path=str(tmp_path / "model_settings.json"),
            default_chat_model="llama3.1:8b",
            installed_models_provider=lambda: ["llama3.1:8b"],
            catalog_loader=load_model_catalog,
        ),
        keep_alive="5m",
        embeddings_provider=SentenceTransformersEmbeddingsProvider(),
    )
    with build_runtime_client(runtime) as client:
        response = client.get("/models/runtime")

    payload = response.json()
    assert payload["embeddings"]["provider"] == "sentence_transformers"
    assert payload["embeddings"]["status"] == "missing_dependency"


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
        llm_provider=OllamaProvider(FakeOllamaRuntime(installed=["llama3.1:8b"])),
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

    from services.ollama_service import OllamaService
    from services.providers.ollama_provider import OllamaProvider

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
    chat = ChatService(
        chroma_service=chroma,
        llm_provider=OllamaProvider(ollama),
        top_k=3,
        max_context_chunks=3,
    )
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
