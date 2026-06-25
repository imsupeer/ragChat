from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_debug import router as debug_router
from core.dependencies import get_model_runtime_service
from services.model_catalog import load_model_catalog
from services.model_runtime import ModelRuntimeService
from services.model_settings import ModelSettingsService
from services.providers.local_hash_embeddings_provider import LocalHashEmbeddingsProvider
from services.providers.ollama_provider import OllamaProvider
from tests.services.test_model_runtime import FakeOllamaRuntime


class FakeChroma:
    def list_chunk_metadatas(self):
        return [
            {
                "embedding_provider": "ollama",
                "embedding_model": "mxbai-embed-large",
                "embedding_dimension": 1024,
            }
        ]

    def get_collection_status(self):
        return {
            "strategy": "per_embedding_provider",
            "active_collection": "rag_local_hash_local_hash_v1_384",
        }


class FakeRegistry:
    def list_all(self):
        return [{"id": "doc-1"}]


def test_debug_embeddings_endpoint_returns_diagnostics(tmp_path):
    runtime = ModelRuntimeService(
        llm_provider=OllamaProvider(FakeOllamaRuntime()),
        model_settings=ModelSettingsService(
            settings_path=str(tmp_path / "model_settings.json"),
            default_chat_model="llama3.1:8b",
            installed_models_provider=lambda: ["llama3.1:8b"],
            catalog_loader=load_model_catalog,
        ),
        keep_alive="5m",
        embeddings_provider=LocalHashEmbeddingsProvider(),
        chroma_service=FakeChroma(),
        document_registry=FakeRegistry(),
    )

    app = FastAPI()
    app.include_router(debug_router)
    app.dependency_overrides[get_model_runtime_service] = lambda: runtime

    with TestClient(app) as client:
        response = client.get("/debug/embeddings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"]["provider"] == "local_hash"
    assert payload["collection"]["status"] == "mixed"
    assert payload["collection"]["reindex_recommended"] is True
    assert payload["reindex"]["recommended"] is True
    assert "reindex_documents.py --dry-run" in payload["reindex"]["dry_run_command"]
    assert "reindex_guidance" in payload
