import pytest

from backend.prompts.rag_prompt import (
    EMPTY_CONTEXT_PLACEHOLDER,
    build_rag_prompt,
    resolve_answer_mode,
)


def test_build_rag_prompt_strict_mode_includes_context_question_and_grounding_rules():
    prompt = build_rag_prompt("context block", "What is this?", answer_mode="strict_rag")

    assert "context block" in prompt
    assert "What is this?" in prompt
    assert "Use ONLY the provided context." in prompt
    assert "The provided context is your ONLY source of truth." in prompt
    assert (
        "The provided context does not contain enough information to answer this."
        in prompt
    )
    assert "### Evidence" in prompt
    assert "Document Evidence" not in prompt


def test_build_rag_prompt_hybrid_mode_uses_hybrid_instructions():
    prompt = build_rag_prompt("context block", "What is this?", answer_mode="hybrid_assistant")

    assert "context block" in prompt
    assert "What is this?" in prompt
    assert "general model knowledge" in prompt.lower()
    assert "### Document Evidence" in prompt
    assert "### General Knowledge Used" in prompt
    assert (
        "The provided context does not contain enough information to answer this from the uploaded documents."
        in prompt
    )
    assert "Do NOT fabricate document evidence." in prompt
    assert "highest-priority source" in prompt.lower()


def test_build_rag_prompt_defaults_to_strict_mode():
    prompt = build_rag_prompt("context block", "What is this?")

    assert "Use ONLY the provided context." in prompt


def test_build_rag_prompt_renders_empty_context_placeholder():
    prompt = build_rag_prompt("", "What is this?", answer_mode="hybrid_assistant")

    assert EMPTY_CONTEXT_PLACEHOLDER in prompt


def test_resolve_answer_mode_normalizes_case():
    assert resolve_answer_mode("STRICT_RAG") == "strict_rag"
    assert resolve_answer_mode("Hybrid_Assistant") == "hybrid_assistant"


def test_resolve_answer_mode_rejects_invalid_value():
    with pytest.raises(ValueError, match="Invalid answer_mode"):
        resolve_answer_mode("creative_mode")

    with pytest.raises(ValueError, match="Invalid answer_mode"):
        build_rag_prompt("context", "question", answer_mode="invalid")
