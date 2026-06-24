from langchain_core.documents import Document

from backend.core.observability import (
    build_chunk_debug,
    build_failed_generation_debug,
    build_generation_debug,
    build_prompt_debug,
    estimate_token_count,
    get_chunk_id,
    safe_generation_error_message,
)


def test_estimate_token_count_returns_zero_for_empty_text():
    assert estimate_token_count("") == 0


def test_get_chunk_id_falls_back_to_document_and_chunk_index():
    doc = Document(
        page_content="Example content",
        metadata={"document_id": "doc-1", "chunk_index": 3},
    )

    assert get_chunk_id(doc) == "doc-1:3"


def test_build_prompt_debug_includes_length_and_token_estimates():
    docs = [
        Document(
            page_content="Context block",
            metadata={"chunk_id": "chunk-1"},
        )
    ]

    debug = build_prompt_debug(
        prompt="SYSTEM\nCONTEXT\nQUESTION",
        context="Context block",
        used_docs=docs,
        latency_ms=12.5,
    )

    assert debug["latency_ms"] == 12.5
    assert debug["answer_mode"] == "strict_rag"
    assert debug["used_chunk_count"] == 1
    assert debug["used_chunk_ids"] == ["chunk-1"]
    assert len(debug["used_chunks"]) == 1
    assert debug["used_chunks"][0]["chunk_id"] == "chunk-1"
    assert debug["prompt_length_chars"] > 0
    assert debug["prompt_token_estimate"] > 0


def test_build_generation_debug_includes_output_metrics():
    debug = build_generation_debug(
        model="llama3.1",
        output_text="Answer text",
        latency_ms=42.0,
    )

    assert debug["model"] == "llama3.1"
    assert debug["latency_ms"] == 42.0
    assert debug["output_length_chars"] == len("Answer text")
    assert debug["output_token_estimate"] > 0


def test_build_failed_generation_debug_marks_failure_metadata():
    debug = build_failed_generation_debug(
        model="llama3.1",
        output_text="Partial",
        latency_ms=12.0,
        error_code="generation_failed",
        error_message="Generation failed.",
    )

    assert debug["status"] == "failed"
    assert debug["error_code"] == "generation_failed"
    assert debug["partial_answer"] is True
    assert debug["output_length_chars"] == len("Partial")


def test_safe_generation_error_message_redacts_path_like_errors():
    assert (
        safe_generation_error_message(
            RuntimeError(r"failed to read C:\Users\secret\file.txt")
        )
        == "Generation failed."
    )
    assert safe_generation_error_message(RuntimeError("Ollama unavailable")) == (
        "Ollama unavailable"
    )


def test_redact_local_paths_handles_windows_and_unix_paths():
    from core.observability import redact_local_paths

    windows = redact_local_paths(r"C:\Users\secret\storage\docs\abc.pdf failed")
    assert "C:\\Users" not in windows
    assert "[path]" in windows

    unix = redact_local_paths("/home/user/storage/docs/sample.txt missing")
    assert "/home/user" not in unix
    assert "[path]" in unix


def test_build_chunk_debug_omits_file_path_from_metadata():
    doc = Document(
        page_content="Example content",
        metadata={
            "source": "sample.txt",
            "document_id": "doc-1",
            "chunk_index": 0,
            "chunk_id": "chunk-1",
            "file_path": r"C:\Users\secret\storage\docs\sample.txt",
        },
    )

    debug = build_chunk_debug(doc)

    assert "file_path" not in debug["metadata"]
    assert debug["source"] == "sample.txt"
    assert "C:\\Users" not in str(debug)


def test_build_chunk_debug_prefers_rerank_score_and_rank_when_present():
    doc = Document(
        page_content="registry.json stores document registry entries",
        metadata={
            "source": "file.txt",
            "document_id": "doc-1",
            "chunk_index": 0,
            "chunk_id": "chunk-1",
            "_retrieval_score": 0.123,
            "_retrieval_rank": 2,
            "_retrieval_score_type": "rrf",
            "_retrieval_method": "hybrid",
            "_retrieval_methods": ["dense", "lexical"],
            "_rerank_score": 7.4,
            "_rerank_rank": 1,
        },
    )

    debug = build_chunk_debug(doc)

    assert debug["rank"] == 1
    assert debug["score"] == 7.4
    assert debug["score_type"] == "rerank"
    assert debug["retrieval_rank"] == 2
    assert debug["retrieval_score"] == 0.123
    assert debug["rerank_rank"] == 1
    assert debug["rerank_score"] == 7.4
