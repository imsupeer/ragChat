import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.eval import (
    analyze_dataset,
    collect_failed_cases,
    escape_markdown_table,
    render_markdown_report,
    write_markdown_report,
)


def build_sample_report(*, include_failure: bool = False) -> dict:
    results = [
        {
            "id": "retrieval-filter",
            "question": "How can retrieval be restricted?",
            "retrieval_question": None,
            "document_ids": ["retrieval_design"],
            "expected_source_chunk_ids": ["retrieval_design.md:0"],
            "retrieved_chunk_ids": ["retrieval_design.md:0"],
            "correct_chunk_retrieved": False if include_failure else True,
            "generation_skipped": True,
            "answer_correct": None,
            "actual_answer": None,
            "notes": None,
        },
        {
            "id": "follow-up-reranking-default",
            "question": "Is it enabled by default?",
            "retrieval_question": "Is reranking enabled by default in the system?",
            "document_ids": [],
            "expected_source_chunk_ids": ["limitations.md:0"],
            "retrieved_chunk_ids": ["limitations.md:0"],
            "correct_chunk_retrieved": True,
            "generation_skipped": True,
            "answer_correct": None,
            "actual_answer": None,
            "notes": None,
        },
    ]

    return {
        "dataset_overview": {
            "total": 2,
            "example_ids": [result["id"] for result in results],
            "with_document_ids": 1,
            "with_retrieval_question": 1,
            "follow_up_examples": 1,
            "refusal_oriented": 0,
            "document_scoped": 1,
            "dataset_path": "scripts/eval_data/dataset.json",
        },
        "config": {
            "answer_mode": "strict_rag",
            "enable_hybrid": False,
            "enable_reranking": False,
            "enable_query_rewriting": False,
            "top_k": 5,
            "max_context_chunks": 5,
            "rerank_top_m": 10,
            "rerank_top_k": 5,
            "query_rewrite_history_turns": 4,
            "embed_model": "nomic-embed-text",
            "chat_model": "llama3.2:1b",
            "ollama_base_url": "http://localhost:11434",
            "fake_embeddings": True,
            "skip_generation": True,
        },
        "meta": {
            "run_timestamp": "2026-06-23T12:00:00+00:00",
            "command": "python scripts/eval.py --skip-generation --fake-embeddings --report-md out.md",
        },
        "summary": {
            "examples_total": 2,
            "retrieval_examples": 2,
            "generation_examples": 0,
            "retrieval_recall_at_k": 0.5 if include_failure else 1.0,
            "correct_chunk_retrieval_rate": 0.5 if include_failure else 1.0,
            "answer_accuracy": None,
        },
        "results": results,
    }


REQUIRED_SECTIONS = [
    "# Evaluation Report",
    "## Summary",
    "## Active Configuration",
    "## Dataset Overview",
    "## Per-example Results",
    "## Failed Cases",
    "## Notes",
]


def test_render_markdown_report_includes_required_sections():
    markdown = render_markdown_report(build_sample_report())

    for section in REQUIRED_SECTIONS:
        assert section in markdown


def test_render_markdown_report_includes_answer_mode_and_query_rewriting():
    markdown = render_markdown_report(build_sample_report())

    assert "Answer mode" in markdown
    assert "strict_rag" in markdown
    assert "Query rewriting" in markdown
    assert "Fake embeddings" in markdown


def test_render_markdown_report_includes_chunk_ids_and_skip_generation():
    markdown = render_markdown_report(build_sample_report())

    assert "retrieval_design.md:0" in markdown
    assert "limitations.md:0" in markdown
    assert "Generation skipped." in markdown
    assert "N/A — generation skipped" in markdown


def test_render_markdown_report_writes_no_failed_cases_exactly():
    markdown = render_markdown_report(build_sample_report(include_failure=False))

    assert "## Failed Cases\n\nNo failed cases." in markdown


def test_render_markdown_report_includes_failed_recall_case():
    markdown = render_markdown_report(build_sample_report(include_failure=True))

    assert "Failure type: recall" in markdown
    assert collect_failed_cases(build_sample_report(include_failure=True)["results"])


def test_escape_markdown_table_escapes_pipes():
    assert escape_markdown_table("a|b") == "a\\|b"


def test_write_markdown_report_creates_parent_directories(tmp_path: Path):
    report_path = tmp_path / "nested" / "dir" / "eval_report.md"
    write_markdown_report(build_sample_report(), report_path)

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "# Evaluation Report" in content


def test_analyze_dataset_counts_follow_up_and_refusal_examples():
    dataset = {
        "examples": [
            {"id": "a", "document_ids": ["doc"], "expected_source_chunk_ids": ["a:0"]},
            {
                "id": "b",
                "retrieval_question": "rewritten",
                "conversation_history": [{"role": "user", "content": "x"}],
                "expected_source_chunk_ids": ["b:0"],
            },
            {
                "id": "c",
                "expected_answer": "The provided context does not contain enough information to answer this.",
                "expected_source_chunk_ids": [],
            },
        ]
    }

    overview = analyze_dataset(dataset, "scripts/eval_data/dataset.json")

    assert overview["total"] == 3
    assert overview["with_document_ids"] == 1
    assert overview["with_retrieval_question"] == 1
    assert overview["follow_up_examples"] == 1
    assert overview["refusal_oriented"] == 1


def test_eval_cli_writes_markdown_report(tmp_path: Path):
    report_path = tmp_path / "eval_report.md"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT_DIR / "scripts" / "eval.py"),
            "--skip-generation",
            "--fake-embeddings",
            "--report-md",
            str(report_path),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in content
    assert "Retrieval recall@k: 1.0" in result.stdout
