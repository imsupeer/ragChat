import asyncio

from services.query_rewriter import (
    QueryRewriter,
    format_history_turns,
    is_context_dependent,
    normalize_rewritten_query,
    trim_history_messages,
)


def test_is_context_dependent():
    assert is_context_dependent("Is it enabled by default?") is True
    assert is_context_dependent("What about that?") is True
    assert is_context_dependent("How does hybrid retrieval work?") is False
    assert is_context_dependent("Which storage system keeps vectors?") is False


def test_trim_history_messages_keeps_recent_turns():
    messages = [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "Second question"},
        {"role": "assistant", "content": "Second answer"},
        {"role": "user", "content": "Third question"},
        {"role": "assistant", "content": "Third answer"},
    ]

    trimmed = trim_history_messages(messages, max_turns=2)

    assert [message["content"] for message in trimmed] == [
        "Second question",
        "Second answer",
        "Third question",
        "Third answer",
    ]


def test_format_history_turns():
    history = format_history_turns(
        [
            {"role": "user", "content": "Does it use reranking?"},
            {"role": "assistant", "content": "Optional reranking exists."},
        ]
    )

    assert "User: Does it use reranking?" in history
    assert "Assistant: Optional reranking exists." in history


def test_normalize_rewritten_query():
    assert normalize_rewritten_query('"Is reranking enabled by default?"') == (
        "Is reranking enabled by default?"
    )


def test_rewrite_skips_standalone_question():
    async def should_not_run(prompt: str) -> str:
        raise AssertionError("should not call llm")

    rewriter = QueryRewriter(
        enabled=True,
        history_turns=4,
        generate_fn=should_not_run,
    )

    outcome = asyncio.run(
        rewriter.rewrite(
            "Which storage system keeps vectors?",
            [
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
            ],
        )
    )

    assert outcome.enabled is True
    assert outcome.used is False
    assert outcome.rewritten_query == "Which storage system keeps vectors?"


def test_rewrite_follow_up_uses_llm_output():
    async def fake_generate(prompt: str) -> str:
        assert "Follow-up question" in prompt
        return "Is reranking enabled by default in the system?"

    rewriter = QueryRewriter(
        enabled=True,
        history_turns=4,
        generate_fn=fake_generate,
    )

    outcome = asyncio.run(
        rewriter.rewrite(
            "Is it enabled by default?",
            [
                {"role": "user", "content": "Does the system use reranking?"},
                {"role": "assistant", "content": "Optional reranking is available."},
            ],
        )
    )

    assert outcome.used is True
    assert outcome.rewritten_query == "Is reranking enabled by default in the system?"
    assert outcome.history_turns_used == 1
    assert outcome.latency_ms >= 0


def test_rewrite_disabled_returns_original():
    rewriter = QueryRewriter(enabled=False, history_turns=4)

    outcome = asyncio.run(
        rewriter.rewrite(
            "Is it enabled by default?",
            [{"role": "user", "content": "Previous"}],
        )
    )

    assert outcome.enabled is False
    assert outcome.used is False
    assert outcome.rewritten_query == "Is it enabled by default?"
