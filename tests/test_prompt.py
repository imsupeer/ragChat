from backend.prompts.rag_prompt import build_rag_prompt


def test_build_rag_prompt():
    prompt = build_rag_prompt("context block", "What is this?")
    assert "context block" in prompt
    assert "What is this?" in prompt
    assert "Only use the provided context" in prompt
