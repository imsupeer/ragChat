import asyncio
from unittest.mock import MagicMock

from langchain_core.documents import Document

from services.chat_service import ChatService
from services.query_rewriter import QueryRewriter


def build_chat_service():
    chroma_service = MagicMock()
    ollama_service = MagicMock()
    service = ChatService(
        chroma_service=chroma_service,
        ollama_service=ollama_service,
        top_k=3,
        max_context_chunks=3,
    )
    service.retriever = MagicMock()
    service.retriever.top_k = 3
    service.retriever.enable_hybrid = False
    service.retriever.search.return_value = [
        Document(
            page_content="PDF handling does not include OCR.",
            metadata={
                "source": "limitations.md",
                "chunk_id": "limitations.md:0",
                "chunk_index": 0,
                "document_id": "limitations",
                "_retrieval_score": 0.9,
                "_retrieval_rank": 1,
                "_retrieval_score_type": "distance",
            },
        )
    ]
    return service


def test_prepare_uses_retrieval_query_for_search_but_original_for_prompt():
    chat_service = build_chat_service()
    prepared = chat_service.prepare(
        user_question="Is it enabled by default?",
        retrieval_question="Is reranking enabled by default in the system?",
        query_rewriting_debug={
            "enabled": True,
            "used": True,
            "original_question": "Is it enabled by default?",
            "rewritten_query": "Is reranking enabled by default in the system?",
            "history_turns_used": 1,
            "latency_ms": 12.5,
        },
    )

    chat_service.retriever.search.assert_called_once_with(
        question="Is reranking enabled by default in the system?",
        document_ids=None,
    )
    assert "Is it enabled by default?" in prepared["prompt"]
    assert prepared["debug"]["query_rewriting"]["used"] is True
    assert prepared["debug"]["retrieval"]["query"] == (
        "Is reranking enabled by default in the system?"
    )
    assert "PDF handling does not include OCR." in prepared["prompt"]


def test_prepare_without_rewrite_keeps_question_unchanged():
    chat_service = build_chat_service()
    prepared = chat_service.prepare(
        user_question="Does PDF handling include OCR?",
    )

    chat_service.retriever.search.assert_called_once_with(
        question="Does PDF handling include OCR?",
        document_ids=None,
    )
    assert prepared["debug"]["query_rewriting"]["enabled"] is False
    assert prepared["debug"]["query_rewriting"]["used"] is False


def test_prepare_request_rewrites_follow_up_before_retrieval():
    chat_service = build_chat_service()

    async def fake_generate(prompt: str) -> str:
        return "Is reranking enabled by default in the system?"

    chat_service.query_rewriter = QueryRewriter(
        enabled=True,
        history_turns=4,
        generate_fn=fake_generate,
    )

    prepared = asyncio.run(
        chat_service.prepare_request(
            question="Is it enabled by default?",
            chat_history=[
                {"role": "user", "content": "Does the system use reranking?"},
                {"role": "assistant", "content": "Optional reranking is available."},
            ],
        )
    )

    chat_service.retriever.search.assert_called_once_with(
        question="Is reranking enabled by default in the system?",
        document_ids=None,
    )
    assert prepared["debug"]["query_rewriting"]["used"] is True
    assert "Is it enabled by default?" in prepared["prompt"]


def test_prepare_request_standalone_question_skips_rewrite():
    chat_service = build_chat_service()

    async def should_not_run(prompt: str) -> str:
        raise AssertionError("should not rewrite")

    chat_service.query_rewriter = QueryRewriter(
        enabled=True,
        history_turns=4,
        generate_fn=should_not_run,
    )

    prepared = asyncio.run(
        chat_service.prepare_request(
            question="Which storage system keeps vectors?",
            chat_history=[
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
            ],
        )
    )

    chat_service.retriever.search.assert_called_once_with(
        question="Which storage system keeps vectors?",
        document_ids=None,
    )
    assert prepared["debug"]["query_rewriting"]["used"] is False


def test_prompt_template_does_not_include_chat_history():
    chat_service = build_chat_service()
    prepared = chat_service.prepare(
        user_question="Follow-up question",
        retrieval_question="Standalone retrieval query about reranking defaults",
    )

    assert "Assistant:" not in prepared["prompt"]
    assert "Conversation history" not in prepared["prompt"]
    assert "Follow-up question" in prepared["prompt"]
    assert "### CONTEXT" in prepared["prompt"]
    assert "### QUESTION" in prepared["prompt"]
