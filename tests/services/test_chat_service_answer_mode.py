from unittest.mock import MagicMock

from langchain_core.documents import Document

from backend.core.config import Settings
from services.chat_service import ChatService


def build_chat_service(*, answer_mode: str = "strict_rag") -> ChatService:
    chroma_service = MagicMock()
    ollama_service = MagicMock()
    llm_provider = ollama_service
    llm_provider.model = "test-model"
    llm_provider.keep_alive = "5m"
    service = ChatService(
        chroma_service=chroma_service,
        llm_provider=llm_provider,
        top_k=3,
        max_context_chunks=3,
        answer_mode=answer_mode,
    )
    service.retriever = MagicMock()
    service.retriever.top_k = 3
    service.retriever.enable_hybrid = False
    service.retriever.search.return_value = [
        Document(
            page_content="Registry stores document metadata.",
            metadata={
                "source": "registry.json",
                "chunk_id": "registry.json:0",
                "chunk_index": 0,
                "document_id": "registry",
                "_retrieval_score": 0.9,
                "_retrieval_rank": 1,
                "_retrieval_score_type": "distance",
            },
        )
    ]
    return service


def test_prepare_strict_mode_uses_strict_prompt_and_debug_metadata():
    chat_service = build_chat_service(answer_mode="strict_rag")
    prepared = chat_service.prepare(user_question="Where is metadata stored?")

    assert "Use ONLY the provided context." in prepared["prompt"]
    assert prepared["debug"]["prompt"]["answer_mode"] == "strict_rag"


def test_prepare_hybrid_mode_uses_hybrid_prompt_and_debug_metadata():
    chat_service = build_chat_service(answer_mode="hybrid_assistant")
    prepared = chat_service.prepare(user_question="Where is metadata stored?")

    assert "### Document Evidence" in prepared["prompt"]
    assert "### General Knowledge Used" in prepared["prompt"]
    assert prepared["debug"]["prompt"]["answer_mode"] == "hybrid_assistant"


def test_settings_default_answer_mode_is_strict_rag():
    settings = Settings()

    assert settings.answer_mode == "strict_rag"
