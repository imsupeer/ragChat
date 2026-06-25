import asyncio
from unittest.mock import MagicMock

from langchain_core.documents import Document

from services.chat_service import ChatService
from services.model_catalog import load_model_catalog
from services.model_settings import ModelSettingsService
from services.ollama_service import OllamaService
from services.providers.ollama_provider import OllamaProvider
from services.query_rewriter import QueryRewriter


class TrackingOllamaService(OllamaService):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.generate_models: list[str] = []
        self.stream_models: list[str] = []

    async def generate(self, prompt: str, model: str | None = None) -> str:
        active = model or self.model
        self.generate_models.append(active)
        return f"answer from {active}"

    async def stream(self, prompt: str, model: str | None = None):
        active = model or self.model
        self.stream_models.append(active)
        for token in ["ok"]:
            yield token


def build_chat_stack(tmp_path, installed=None):
    installed = installed or ["llama3.1:8b", "qwen3:8b"]
    settings_service = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        query_rewrite_model="llama3.1:8b",
        use_chat_model_for_query_rewrite=False,
        installed_models_provider=lambda: installed,
        catalog_loader=load_model_catalog,
    )

    ollama = TrackingOllamaService(
        base_url="http://127.0.0.1:11434",
        model="llama3.1:8b",
        model_resolver=settings_service.get_active_chat_model,
    )
    provider = OllamaProvider(ollama)

    chroma_service = MagicMock()
    chat_service = ChatService(
        chroma_service=chroma_service,
        llm_provider=provider,
        top_k=3,
        max_context_chunks=3,
    )
    chat_service.retriever = MagicMock()
    chat_service.retriever.top_k = 3
    chat_service.retriever.enable_hybrid = False
    chat_service.retriever.search.return_value = [
        Document(
            page_content="Sample context.",
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

    return settings_service, ollama, chat_service


def test_chat_ask_uses_active_selected_model(tmp_path):
    settings_service, ollama, chat_service = build_chat_stack(tmp_path)
    settings_service.update_chat_model("qwen3:8b", require_installed=True)

    result = asyncio.run(chat_service.ask("What is in the docs?"))

    assert ollama.generate_models == ["qwen3:8b"]
    assert result["debug"]["generation"]["model"] == "qwen3:8b"


async def _collect_stream(ollama: TrackingOllamaService, prompt: str):
    tokens = []
    async for token in ollama.stream(prompt):
        tokens.append(token)
    return "".join(tokens)


def test_chat_stream_uses_active_selected_model(tmp_path):
    settings_service, ollama, chat_service = build_chat_stack(tmp_path)
    settings_service.update_chat_model("qwen3:8b", require_installed=True)
    prepared = asyncio.run(chat_service.prepare_request("Stream question?"))

    asyncio.run(_collect_stream(ollama, prepared["prompt"]))

    assert ollama.stream_models == ["qwen3:8b"]


def test_query_rewrite_model_config_is_independent_of_active_chat_model(tmp_path):
    settings_service, ollama, _chat_service = build_chat_stack(tmp_path)
    settings_service.update_chat_model("qwen3:8b", require_installed=True)

    rewriter = QueryRewriter(
        enabled=True,
        history_turns=2,
        llm_provider=OllamaProvider(ollama),
        rewrite_model="llama3.1:8b",
    )

    assert rewriter._resolve_rewrite_model() == "llama3.1:8b"
    assert ollama.model == "qwen3:8b"
