from backend.prompts.rag_prompt import build_rag_prompt


def test_build_rag_prompt_includes_context_question_and_grounding_rules():
    prompt = build_rag_prompt("context block", "What is this?")

    assert "context block" in prompt
    assert "What is this?" in prompt
    assert "Use ONLY the provided context." in prompt
    assert "The provided context is your ONLY source of truth." in prompt
    assert (
        "The provided context does not contain enough information to answer this."
        in prompt
    )
