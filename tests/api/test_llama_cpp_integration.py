import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from api.routes_chat import router as chat_router
from api.routes_health import router as health_router
from api.routes_models import router as models_router
from core.dependencies import get_chat_service, get_local_metrics_service, get_model_runtime_service, get_readiness_service
from services.chat_service import ChatService
from services.metrics import LocalMetrics
from services.model_catalog import load_model_catalog
from services.model_runtime import ModelRuntimeError, ModelRuntimeService
from services.model_settings import ModelSettingsService
from services.providers.llama_cpp_provider import LlamaCppProvider


class FakeLlamaCppProvider(LlamaCppProvider):
    def __init__(
        self,
        *,
        reachable: bool = True,
        installed: list[str] | None = None,
        generate_text: str = "llama.cpp answer",
        stream_tokens: list[str] | None = None,
    ) -> None:
        super().__init__(
            base_url="http://127.0.0.1:11435",
            chat_model="demo-model.gguf",
        )
        self._reachable = reachable
        self._installed = installed or ["demo-model.gguf"]
        self._generate_text = generate_text
        self._stream_tokens = stream_tokens or ["tok"]
        self.generate_calls: list[str] = []
        self.stream_calls: list[str] = []

    def is_reachable(self, timeout: float | None = None) -> bool:
        del timeout
        return self._reachable

    def list_installed_model_details(
        self, timeout: float | None = None
    ) -> list[dict]:
        del timeout
        if not self._reachable:
            return []
        return [
            {"name": name, "family": None, "size": None, "modified_at": None, "status": "server"}
            for name in self._installed
        ]

    def list_running_models_status(self, timeout: float | None = None) -> dict:
        del timeout
        if not self._reachable:
            return {"detection": "unavailable", "detection_method": "server_reachable", "models": []}
        return {
            "detection": "available",
            "detection_method": "provider_runtime",
            "models": [{"name": self.model, "status": "loaded"}],
        }

    async def generate(self, prompt: str, model: str | None = None) -> str:
        del model
        self.generate_calls.append(prompt)
        if not self._reachable:
            raise RuntimeError("llama.cpp server is unavailable.")
        return self._generate_text

    async def stream(self, prompt: str, model: str | None = None):
        del model
        self.stream_calls.append(prompt)
        if not self._reachable:
            raise RuntimeError("llama.cpp server is unavailable.")
        for token in self._stream_tokens:
            yield token

    def preload_model_sync(self, model: str) -> None:
        del model
        if not self._reachable:
            raise RuntimeError("llama.cpp server is unavailable.")


@pytest.fixture
def llama_runtime_stack(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    models_dir = tmp_path / "demo"
    binary_dir = tmp_path / "bin"
    models_dir.mkdir()
    binary_dir.mkdir()
    manifest_path.write_text(
        '{"id":"demo-gguf","display_name":"Demo","provider":"llama_cpp","model_file":"model.gguf"}',
        encoding="utf-8",
    )
    settings = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="demo-model.gguf",
        installed_models_provider=lambda: ["demo-model.gguf"],
        catalog_loader=load_model_catalog,
    )
    provider = FakeLlamaCppProvider()
    runtime = ModelRuntimeService(
        llm_provider=provider,
        model_settings=settings,
        keep_alive="",
        llama_cpp_manifest_path=str(manifest_path),
        llama_cpp_models_dir=str(models_dir),
        llama_cpp_binary_dir=str(binary_dir),
    )
    return settings, provider, runtime, manifest_path, models_dir, binary_dir


def test_model_runtime_includes_llama_cpp_provider_block(llama_runtime_stack):
    _, _, runtime, *_ = llama_runtime_stack
    status = runtime.get_runtime_status()

    assert status["provider"]["name"] == "llama_cpp"
    assert status["provider"]["display_name"] == "llama.cpp"
    assert status["provider"]["capabilities"]["unload"] is False
    assert status["runtime"]["unload_supported"] is False
    assert status["runtime"]["keep_alive"] == ""
    assert "local_runtime" in status
    assert status["local_runtime"]["manifest_found"] is True
    assert status["local_runtime"]["model_file_found"] is False
    assert "/" not in status["local_runtime"]["message"] or "models/demo" in status["local_runtime"]["message"]


def test_model_runtime_preload_llama_cpp_message(llama_runtime_stack):
    _, _, runtime, *_ = llama_runtime_stack
    result = runtime.preload_active_model()
    assert "managed by the server process" in result["message"]


def test_model_runtime_unload_unsupported_for_llama_cpp(llama_runtime_stack):
    _, _, runtime, *_ = llama_runtime_stack
    with pytest.raises(ModelRuntimeError, match="not supported"):
        runtime.unload_active_model()


def test_readiness_includes_llama_cpp_provider(tmp_path: Path):
    from core.config import Settings
    from services.readiness import ReadinessService
    from services.sqlite_store import SQLiteStore

    class FakeChroma:
        def list_document_ids_with_vector_counts(self):
            return {}

    class FakeQueue:
        @property
        def is_worker_alive(self) -> bool:
            return True

    settings_service = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="demo-model.gguf",
        installed_models_provider=lambda: [],
        catalog_loader=load_model_catalog,
    )
    provider = FakeLlamaCppProvider(reachable=False)
    runtime = ModelRuntimeService(
        llm_provider=provider,
        model_settings=settings_service,
        keep_alive="",
    )
    service = ReadinessService(
        settings=Settings(sqlite_path=str(tmp_path / "app.db"), llm_provider="llama_cpp"),
        sqlite_store=SQLiteStore(str(tmp_path / "app.db")),
        chroma_service=FakeChroma(),
        upload_queue=FakeQueue(),
        metrics=LocalMetrics(),
        model_runtime=runtime,
    )

    report = service.check()
    assert report["checks"]["ollama"]["provider"] == "llama_cpp"
    assert report["checks"]["ollama"]["status"] == "degraded"


def test_chat_uses_llama_cpp_provider(tmp_path: Path):
    provider = FakeLlamaCppProvider()
    chroma = MagicMock()
    chat = ChatService(
        chroma_service=chroma,
        llm_provider=provider,
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

    assert provider.generate_calls
    assert result["answer"] == "llama.cpp answer"
    assert result["debug"]["generation"]["model"] == "demo-model.gguf"
    assert result["debug"]["generation"].get("keep_alive") is None


def test_runtime_api_with_llama_cpp_provider(llama_runtime_stack):
    _, _, runtime, *_ = llama_runtime_stack
    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_model_runtime_service] = lambda: runtime
    app.dependency_overrides[get_local_metrics_service] = lambda: LocalMetrics()

    with TestClient(app) as client:
        response = client.get("/models/runtime")

    payload = response.json()
    assert response.status_code == 200
    assert payload["provider"]["name"] == "llama_cpp"
    assert payload["local_runtime"]["manifest_found"] is True
