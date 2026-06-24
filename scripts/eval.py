from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if TYPE_CHECKING:
    from core.config import Settings
    from services.chat_service import ChatService


WHITESPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\s]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a lightweight evaluation harness against the local RAG pipeline."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT_DIR / "scripts" / "eval_data" / "dataset.json",
        help="Path to the evaluation dataset JSON file.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=ROOT_DIR / "scripts" / "eval_data" / "docs",
        help="Directory containing fixture documents to index for evaluation.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override retrieval top_k. Defaults to backend settings.",
    )
    parser.add_argument(
        "--max-context-chunks",
        type=int,
        default=None,
        help="Override max context chunks. Defaults to backend settings.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Override chunk size. Defaults to backend settings.",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=None,
        help="Override chunk overlap. Defaults to backend settings.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for the final report.",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Only evaluate retrieval and prompt construction.",
    )
    parser.add_argument(
        "--enable-hybrid",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override ENABLE_HYBRID from backend settings.",
    )
    parser.add_argument(
        "--enable-reranking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override ENABLE_RERANKING from backend settings.",
    )
    parser.add_argument(
        "--rerank-top-m",
        type=int,
        default=None,
        help="Override RERANK_TOP_M. Defaults to backend settings.",
    )
    parser.add_argument(
        "--rerank-top-k",
        type=int,
        default=None,
        help="Override RERANK_TOP_K. Defaults to backend settings.",
    )
    parser.add_argument(
        "--fake-embeddings",
        action="store_true",
        help="Use deterministic local fake embeddings instead of Ollama (CI/offline).",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=None,
        help="Write a Markdown evaluation report to the given file path.",
    )
    return parser.parse_args()


def load_settings() -> Settings:
    from core.config import Settings

    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        return Settings(_env_file=env_file)
    return Settings()


def load_dataset(dataset_path: Path) -> dict[str, Any]:
    with open(dataset_path, "r", encoding="utf-8") as file:
        return json.load(file)


def normalize_text(value: str) -> str:
    lowered = value.lower()
    stripped = PUNCT_RE.sub(" ", lowered)
    collapsed = WHITESPACE_RE.sub(" ", stripped)
    return collapsed.strip()


def answer_matches(expected: str, actual: str) -> bool:
    expected_norm = normalize_text(expected)
    actual_norm = normalize_text(actual)

    if not expected_norm:
        return True

    if not actual_norm:
        return False

    if expected_norm == actual_norm:
        return True

    if expected_norm in actual_norm or actual_norm in expected_norm:
        return True

    expected_tokens = set(expected_norm.split())
    actual_tokens = set(actual_norm.split())

    if expected_tokens and expected_tokens.issubset(actual_tokens):
        return True

    overlap = len(expected_tokens & actual_tokens) / max(len(expected_tokens), 1)
    return overlap >= 0.8


def logical_chunk_id_from_metadata(metadata: dict[str, Any] | None) -> str | None:
    metadata = metadata or {}
    logical_chunk_id = metadata.get("logical_chunk_id")
    if logical_chunk_id:
        return str(logical_chunk_id)

    source = metadata.get("source")
    chunk_index = metadata.get("chunk_index")
    if source is not None and chunk_index is not None:
        return f"{source}:{chunk_index}"

    return None


def logical_chunk_id_from_result(result: dict[str, Any]) -> str | None:
    metadata = result.get("metadata") or {}
    logical_chunk_id = logical_chunk_id_from_metadata(metadata)
    if logical_chunk_id:
        return logical_chunk_id

    source = result.get("source")
    chunk_index = result.get("chunk_index")
    if source is not None and chunk_index is not None:
        return f"{source}:{chunk_index}"

    return None


def build_chat_service(
    settings: Settings,
    chroma_dir: Path,
    top_k: int,
    max_context_chunks: int,
    enable_hybrid: bool,
    enable_reranking: bool,
    rerank_top_m: int,
    rerank_top_k: int,
    fake_embeddings: bool = False,
) -> ChatService:
    from services.chat_service import ChatService
    from services.chroma_service import ChromaService
    from services.ollama_service import OllamaService

    if fake_embeddings:
        from embeddings.fake_embeddings import FakeEmbeddings

        embedding_function = FakeEmbeddings()
    else:
        from embeddings.embedding_provider import EmbeddingProvider

        embedding_provider = EmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embed_model,
        )
        embedding_function = embedding_provider.get_embeddings()

    chroma_service = ChromaService(
        persist_directory=str(chroma_dir),
        embedding_function=embedding_function,
    )
    ollama_service = OllamaService(
        base_url=settings.ollama_base_url,
        model=settings.ollama_chat_model,
    )
    return ChatService(
        chroma_service=chroma_service,
        ollama_service=ollama_service,
        top_k=top_k,
        max_context_chunks=max_context_chunks,
        enable_hybrid=enable_hybrid,
        enable_reranking=enable_reranking,
        rerank_top_m=rerank_top_m,
        rerank_top_k=rerank_top_k,
        answer_mode=settings.answer_mode,
    )


def resolve_eval_config(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    enable_hybrid = (
        settings.enable_hybrid if args.enable_hybrid is None else args.enable_hybrid
    )
    enable_reranking = (
        settings.enable_reranking
        if args.enable_reranking is None
        else args.enable_reranking
    )
    rerank_top_m = args.rerank_top_m or settings.rerank_top_m
    rerank_top_k = args.rerank_top_k or settings.rerank_top_k

    return {
        "top_k": args.top_k or settings.top_k,
        "max_context_chunks": args.max_context_chunks or settings.max_context_chunks,
        "chunk_size": args.chunk_size or settings.chunk_size,
        "chunk_overlap": args.chunk_overlap or settings.chunk_overlap,
        "enable_hybrid": enable_hybrid,
        "enable_reranking": enable_reranking,
        "rerank_top_m": rerank_top_m,
        "rerank_top_k": rerank_top_k,
        "retrieval_mode": "hybrid" if enable_hybrid else "dense",
    }


def index_fixture_docs(
    docs_dir: Path,
    chat_service: ChatService,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    from ingestion.processor import process_document

    indexed_chunks: list[dict[str, Any]] = []

    for doc_path in sorted(docs_dir.glob("*")):
        if not doc_path.is_file():
            continue

        chunks = process_document(
            file_path=str(doc_path),
            original_filename=doc_path.name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        for chunk in chunks:
            logical_chunk_id = f"{doc_path.name}:{chunk.metadata['chunk_index']}"
            chunk.metadata["logical_chunk_id"] = logical_chunk_id

        document_id = doc_path.stem
        chat_service.chroma_service.add_documents(document_id=document_id, docs=chunks)

        for chunk in chunks:
            indexed_chunks.append(
                {
                    "document_id": document_id,
                    "logical_chunk_id": chunk.metadata["logical_chunk_id"],
                    "source": chunk.metadata.get("source"),
                    "chunk_index": chunk.metadata.get("chunk_index"),
                    "preview": chunk.page_content[:160],
                }
            )

    return indexed_chunks


REFUSAL_PHRASE = (
    "The provided context does not contain enough information to answer this."
)


def escape_markdown_table(value: Any) -> str:
    if value is None:
        return "N/A"
    text = str(value).replace("|", "\\|").replace("\n", " ").strip()
    return text if text else "N/A"


def format_bool(value: bool | None) -> str:
    if value is None:
        return "N/A"
    return "true" if value else "false"


def analyze_dataset(dataset: dict[str, Any], dataset_path: Path | str) -> dict[str, Any]:
    examples = dataset.get("examples", [])
    example_ids = [example["id"] for example in examples]
    with_document_ids = sum(1 for example in examples if example.get("document_ids"))
    with_retrieval_question = sum(
        1 for example in examples if example.get("retrieval_question")
    )
    follow_up_examples = sum(
        1
        for example in examples
        if example.get("retrieval_question") or example.get("conversation_history")
    )
    refusal_oriented = sum(
        1
        for example in examples
        if not example.get("expected_source_chunk_ids")
        or REFUSAL_PHRASE in (example.get("expected_answer") or "")
    )

    return {
        "total": len(examples),
        "example_ids": example_ids,
        "with_document_ids": with_document_ids,
        "with_retrieval_question": with_retrieval_question,
        "follow_up_examples": follow_up_examples,
        "refusal_oriented": refusal_oriented,
        "document_scoped": with_document_ids,
        "dataset_path": str(dataset_path),
    }


def collect_failed_cases(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    for result in results:
        failure_types: list[str] = []
        if result.get("expected_source_chunk_ids") and result.get(
            "correct_chunk_retrieved"
        ) is False:
            failure_types.append("recall")
        if result.get("answer_correct") is False:
            failure_types.append("answer")
        if result.get("error"):
            failure_types.append("runtime")

        if failure_types:
            failures.append({**result, "failure_types": failure_types})

    return failures


def determine_overall_status(results: list[dict[str, Any]]) -> str:
    return "fail" if collect_failed_cases(results) else "pass"


def format_recall_status(result: dict[str, Any]) -> str:
    if result.get("correct_chunk_retrieved") is True:
        return "pass"
    if result.get("correct_chunk_retrieved") is False:
        return "fail"
    return "N/A"


def format_answer_accuracy_status(result: dict[str, Any]) -> str:
    if result.get("generation_skipped"):
        return "N/A — generation skipped"
    if result.get("answer_correct") is True:
        return "pass"
    if result.get("answer_correct") is False:
        return "fail"
    return "N/A"


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    config = report["config"]
    dataset_overview = report["dataset_overview"]
    results = report["results"]
    meta = report.get("meta", {})
    failures = collect_failed_cases(results)
    overall_status = determine_overall_status(results)
    skip_generation = config.get("skip_generation", False)
    fake_embeddings = config.get("fake_embeddings", False)
    if fake_embeddings and skip_generation:
        real_ollama_display = "no"
    elif fake_embeddings:
        real_ollama_display = "generation only"
    elif skip_generation:
        real_ollama_display = "embeddings only"
    else:
        real_ollama_display = "yes"

    if skip_generation:
        answer_accuracy_display = "N/A — generation skipped"
    elif summary.get("answer_accuracy") is None:
        answer_accuracy_display = "N/A"
    else:
        answer_accuracy_display = str(summary["answer_accuracy"])

    lines: list[str] = [
        "# Evaluation Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Run timestamp | {escape_markdown_table(meta.get('run_timestamp'))} |",
        f"| Total examples | {summary['examples_total']} |",
        f"| Recall@k | {escape_markdown_table(summary.get('retrieval_recall_at_k'))} |",
        f"| Answer accuracy | {escape_markdown_table(answer_accuracy_display)} |",
        f"| Generation | {'skipped' if skip_generation else 'enabled'} |",
        f"| Fake embeddings | {'enabled' if fake_embeddings else 'disabled'} |",
        f"| Real Ollama embeddings/generation | {real_ollama_display} |",
        f"| Report command | {escape_markdown_table(meta.get('command'))} |",
        f"| Overall status | {overall_status} |",
        "",
        "## Active Configuration",
        "",
        "| Setting | Value |",
        "| --- | --- |",
        f"| Answer mode | {escape_markdown_table(config.get('answer_mode'))} |",
        f"| Hybrid retrieval | {format_bool(config.get('enable_hybrid'))} |",
        f"| Reranking | {format_bool(config.get('enable_reranking'))} |",
        f"| Query rewriting | {format_bool(config.get('enable_query_rewriting'))} |",
        f"| top_k | {escape_markdown_table(config.get('top_k'))} |",
        f"| max_context_chunks | {escape_markdown_table(config.get('max_context_chunks'))} |",
        f"| rerank_top_m | {escape_markdown_table(config.get('rerank_top_m'))} |",
        f"| rerank_top_k | {escape_markdown_table(config.get('rerank_top_k'))} |",
        f"| Query rewrite history turns | {escape_markdown_table(config.get('query_rewrite_history_turns'))} |",
        f"| Embedding model | {escape_markdown_table(config.get('embed_model'))} |",
        f"| Chat model | {escape_markdown_table(config.get('chat_model'))} |",
        f"| Ollama base URL | {escape_markdown_table(config.get('ollama_base_url'))} |",
        f"| Fake embeddings | {format_bool(fake_embeddings)} |",
        f"| Generation skipped | {format_bool(skip_generation)} |",
        "",
        "## Dataset Overview",
        "",
        "| Item | Count |",
        "| ---: | ---: |",
        f"| Total examples | {dataset_overview['total']} |",
        f"| Examples with document_ids | {dataset_overview['with_document_ids']} |",
        f"| Examples with retrieval_question | {dataset_overview['with_retrieval_question']} |",
        f"| Follow-up examples | {dataset_overview['follow_up_examples']} |",
        f"| Refusal-oriented examples | {dataset_overview['refusal_oriented']} |",
        f"| Document-scoped examples | {dataset_overview['document_scoped']} |",
        "",
        f"Dataset path: `{dataset_overview['dataset_path']}`",
        "",
        "### Example IDs",
        "",
    ]

    for example_id in dataset_overview["example_ids"]:
        lines.append(f"- {example_id}")

    lines.extend(["", "## Per-example Results", ""])

    for result in results:
        retrieval_question = result.get("retrieval_question")
        question = result.get("question", "")
        retrieval_display = (
            retrieval_question
            if retrieval_question and retrieval_question.strip() != question.strip()
            else "N/A"
        )
        document_ids = ", ".join(result.get("document_ids") or []) or "N/A"
        expected_chunks = ", ".join(result.get("expected_source_chunk_ids") or []) or "N/A"
        retrieved_chunks = ", ".join(result.get("retrieved_chunk_ids") or []) or "N/A"
        retrieval_override = (
            "yes"
            if retrieval_question and retrieval_question.strip() != question.strip()
            else "no"
        )

        lines.extend(
            [
                f"### {result['id']}",
                "",
                "| Field | Value |",
                "| --- | --- |",
                f"| Question | {escape_markdown_table(question)} |",
                f"| Retrieval question | {escape_markdown_table(retrieval_display)} |",
                f"| document_ids | {escape_markdown_table(document_ids)} |",
                f"| Expected chunks | {escape_markdown_table(expected_chunks)} |",
                f"| Retrieved chunks | {escape_markdown_table(retrieved_chunks)} |",
                f"| Recall | {format_recall_status(result)} |",
                f"| Answer accuracy | {format_answer_accuracy_status(result)} |",
                f"| Query rewriting / retrieval override | {retrieval_override} |",
                "",
                "#### Generated Answer",
                "",
            ]
        )

        if result.get("generation_skipped"):
            lines.append("Generation skipped.")
        else:
            lines.append(result.get("actual_answer") or "N/A")

        if result.get("notes"):
            lines.extend(["", "#### Notes", "", str(result["notes"])])

        lines.append("")

    lines.extend(["## Failed Cases", ""])

    if not failures:
        lines.append("No failed cases.")
    else:
        for failure in failures:
            failure_types = ", ".join(failure.get("failure_types", []))
            expected_chunks = ", ".join(failure.get("expected_source_chunk_ids") or []) or "N/A"
            retrieved_chunks = ", ".join(failure.get("retrieved_chunk_ids") or []) or "N/A"
            notes = failure.get("notes") or failure.get("error") or "N/A"
            lines.extend(
                [
                    f"### {failure['id']}",
                    "",
                    f"- Failure type: {failure_types}",
                    f"- Expected chunks: {expected_chunks}",
                    f"- Retrieved chunks: {retrieved_chunks}",
                    f"- Notes: {notes}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Notes",
            "",
            "- Fake embeddings are deterministic and useful for offline local validation without Ollama.",
            "- Full generation eval requires Ollama running locally with the configured models pulled.",
            "- `strict_rag` is best for evidence-sensitive evaluation and document-grounded demos.",
            "- `hybrid_assistant` is useful for general assistant behavior enriched by uploaded documents; do not use it to inflate document-grounded evals unless explicitly intended.",
            "- Query rewriting may affect retrieval query construction, but final answers remain grounded in retrieved documents.",
            "- When running eval from the host, `OLLAMA_BASE_URL` should usually be `http://localhost:11434`.",
            "- When running the backend in Docker, `OLLAMA_BASE_URL` may need `http://host.docker.internal:11434`.",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    content = render_markdown_report(report)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def summarize_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_results = [
        result for result in results if result["expected_source_chunk_ids"]
    ]
    generation_results = [
        result
        for result in results
        if result["answer_correct"] is not None and not result["generation_skipped"]
    ]

    retrieval_hits = sum(
        1 for result in retrieval_results if result["correct_chunk_retrieved"]
    )
    answer_hits = sum(1 for result in generation_results if result["answer_correct"])

    return {
        "examples_total": len(results),
        "retrieval_examples": len(retrieval_results),
        "generation_examples": len(generation_results),
        "retrieval_recall_at_k": (
            round(retrieval_hits / len(retrieval_results), 4)
            if retrieval_results
            else None
        ),
        "correct_chunk_retrieval_rate": (
            round(retrieval_hits / len(retrieval_results), 4)
            if retrieval_results
            else None
        ),
        "answer_accuracy": (
            round(answer_hits / len(generation_results), 4)
            if generation_results
            else None
        ),
    }


def format_text_report(report: dict[str, Any]) -> str:
    lines = []
    summary = report["summary"]
    config = report["config"]

    lines.append("RAG Evaluation Report")
    lines.append("=" * 21)
    lines.append("Active configuration")
    lines.append("-" * 19)
    lines.append(f"Retrieval mode: {config['retrieval_mode']}")
    lines.append(f"Hybrid enabled: {config['enable_hybrid']}")
    lines.append(f"Reranking enabled: {config['enable_reranking']}")
    if config["enable_reranking"]:
        lines.append(
            f"Rerank top_m/top_k: {config['rerank_top_m']}/{config['rerank_top_k']}"
        )
    lines.append(f"top_k: {config['top_k']}")
    lines.append(f"max_context_chunks: {config['max_context_chunks']}")
    lines.append("")
    lines.append(f"Examples: {summary['examples_total']}")
    lines.append(f"Retrieval examples: {summary['retrieval_examples']}")
    lines.append(f"Generation examples: {summary['generation_examples']}")
    lines.append(f"Retrieval recall@k: {summary['retrieval_recall_at_k']}")
    lines.append(
        f"Correct chunk retrieval rate: {summary['correct_chunk_retrieval_rate']}"
    )
    lines.append(f"Answer accuracy: {summary['answer_accuracy']}")
    lines.append("")
    lines.append("Per-example results")
    lines.append("-" * 19)

    for result in report["results"]:
        matched_chunks = ", ".join(result["matched_chunk_ids"]) or "-"
        expected_chunks = ", ".join(result["expected_source_chunk_ids"]) or "-"
        retrieved_chunks = ", ".join(result["retrieved_chunk_ids"]) or "-"
        lines.append(f"[{result['id']}] {result['question']}")
        if result.get("document_ids"):
            lines.append(f"  document_ids: {', '.join(result['document_ids'])}")
        lines.append(f"  expected chunks: {expected_chunks}")
        lines.append(f"  retrieved chunks: {retrieved_chunks}")
        lines.append(f"  matched chunks: {matched_chunks}")
        lines.append(
            f"  correct chunk retrieved: {result['correct_chunk_retrieved']} | best rank: {result['best_rank']}"
        )
        lines.append(
            f"  retrieval latency ms: {result['retrieval_latency_ms']} | prompt latency ms: {result['prompt_latency_ms']}"
        )
        if result["generation_skipped"]:
            lines.append("  generation: skipped")
        else:
            lines.append(
                f"  answer correct: {result['answer_correct']} | generation latency ms: {result['generation_latency_ms']}"
            )
            lines.append(f"  expected answer: {result['expected_answer']}")
            lines.append(f"  actual answer: {result['actual_answer']}")
        lines.append("")

    return "\n".join(lines).rstrip()


async def evaluate_examples(
    chat_service: ChatService,
    dataset: dict[str, Any],
    skip_generation: bool,
) -> list[dict[str, Any]]:
    from core.observability import build_query_rewriting_debug

    results: list[dict[str, Any]] = []

    for example in dataset["examples"]:
        document_ids = example.get("document_ids")
        retrieval_question = example.get("retrieval_question")
        rewrite_debug = None
        if retrieval_question:
            history = example.get("conversation_history") or []
            rewrite_debug = build_query_rewriting_debug(
                enabled=True,
                used=retrieval_question.strip().casefold()
                != example["question"].strip().casefold(),
                original_question=example["question"],
                rewritten_query=retrieval_question,
                history_turns_used=sum(
                    1
                    for index, message in enumerate(history)
                    if message.get("role") == "assistant"
                    and index > 0
                    and history[index - 1].get("role") == "user"
                ),
                latency_ms=0.0,
            )

        if skip_generation:
            response = chat_service.prepare(
                user_question=example["question"],
                document_ids=document_ids,
                retrieval_question=retrieval_question,
                query_rewriting_debug=rewrite_debug,
            )
            actual_answer = None
            answer_correct = None
            generation_skipped = True
        else:
            response = await chat_service.ask(
                question=example["question"],
                document_ids=document_ids,
                retrieval_question=retrieval_question,
                query_rewriting_debug=rewrite_debug,
            )
            actual_answer = response["answer"]
            answer_correct = answer_matches(example["expected_answer"], actual_answer)
            generation_skipped = False

        retrieval_results = response["debug"]["retrieval"]["results"]
        retrieved_chunk_ids = [
            logical_chunk_id
            for logical_chunk_id in (
                logical_chunk_id_from_result(item) for item in retrieval_results
            )
            if logical_chunk_id
        ]

        expected_chunk_ids = example.get("expected_source_chunk_ids", [])
        matched_chunk_ids = [
            chunk_id
            for chunk_id in retrieved_chunk_ids
            if chunk_id in expected_chunk_ids
        ]

        best_rank = None
        for item in retrieval_results:
            logical_chunk_id = logical_chunk_id_from_result(item)
            if logical_chunk_id and logical_chunk_id in expected_chunk_ids:
                rank = item.get("rank")
                if isinstance(rank, int):
                    best_rank = rank
                    break

        result = {
            "id": example["id"],
            "question": example["question"],
            "retrieval_question": retrieval_question,
            "document_ids": document_ids or [],
            "expected_answer": example["expected_answer"],
            "actual_answer": actual_answer,
            "expected_source_chunk_ids": expected_chunk_ids,
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "matched_chunk_ids": matched_chunk_ids,
            "correct_chunk_retrieved": (
                bool(matched_chunk_ids) if expected_chunk_ids else None
            ),
            "best_rank": best_rank,
            "answer_correct": answer_correct,
            "generation_skipped": generation_skipped,
            "notes": example.get("notes"),
            "trace_id": response["debug"]["trace_id"],
            "retrieval_latency_ms": response["debug"]["retrieval"]["latency_ms"],
            "prompt_latency_ms": response["debug"]["prompt"]["latency_ms"],
            "generation_latency_ms": (
                response["debug"]["generation"]["latency_ms"]
                if not skip_generation and response["debug"].get("generation")
                else None
            ),
        }
        results.append(result)

    return results


async def main() -> int:
    args = parse_args()
    settings = load_settings()
    dataset = load_dataset(args.dataset)
    eval_config = resolve_eval_config(settings, args)

    with TemporaryDirectory(prefix="rag-eval-", ignore_cleanup_errors=True) as temp_dir:
        chroma_dir = Path(temp_dir) / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)

        chat_service = build_chat_service(
            settings=settings,
            chroma_dir=chroma_dir,
            top_k=eval_config["top_k"],
            max_context_chunks=eval_config["max_context_chunks"],
            enable_hybrid=eval_config["enable_hybrid"],
            enable_reranking=eval_config["enable_reranking"],
            rerank_top_m=eval_config["rerank_top_m"],
            rerank_top_k=eval_config["rerank_top_k"],
            fake_embeddings=args.fake_embeddings,
        )
        indexed_chunks = index_fixture_docs(
            docs_dir=args.docs_dir,
            chat_service=chat_service,
            chunk_size=eval_config["chunk_size"],
            chunk_overlap=eval_config["chunk_overlap"],
        )
        results = await evaluate_examples(
            chat_service=chat_service,
            dataset=dataset,
            skip_generation=args.skip_generation,
        )
        del chat_service

    report = {
        "dataset": {
            "path": str(args.dataset),
            "doc_count": len(list(args.docs_dir.glob("*"))),
            "example_count": len(dataset["examples"]),
            "indexed_chunk_count": len(indexed_chunks),
        },
        "dataset_overview": analyze_dataset(dataset, args.dataset),
        "config": {
            "ollama_base_url": settings.ollama_base_url,
            "chat_model": settings.ollama_chat_model,
            "embed_model": settings.ollama_embed_model,
            "top_k": eval_config["top_k"],
            "max_context_chunks": eval_config["max_context_chunks"],
            "chunk_size": eval_config["chunk_size"],
            "chunk_overlap": eval_config["chunk_overlap"],
            "enable_hybrid": eval_config["enable_hybrid"],
            "enable_reranking": eval_config["enable_reranking"],
            "rerank_top_m": eval_config["rerank_top_m"],
            "rerank_top_k": eval_config["rerank_top_k"],
            "retrieval_mode": eval_config["retrieval_mode"],
            "enable_query_rewriting": settings.enable_query_rewriting,
            "query_rewrite_history_turns": settings.query_rewrite_history_turns,
            "query_rewrite_model": settings.query_rewrite_model,
            "answer_mode": settings.answer_mode,
            "skip_generation": args.skip_generation,
            "fake_embeddings": args.fake_embeddings,
        },
        "meta": {
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "command": " ".join(sys.argv),
        },
        "summary": summarize_metrics(results),
        "results": results,
    }

    if args.report_md is not None:
        write_markdown_report(report, args.report_md)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except ModuleNotFoundError as exc:
        print(
            f"Missing Python dependency: {exc.name}. Install backend dependencies before running the evaluation harness.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
