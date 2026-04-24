from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
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
) -> ChatService:
    from embeddings.embedding_provider import EmbeddingProvider
    from services.chat_service import ChatService
    from services.chroma_service import ChromaService
    from services.ollama_service import OllamaService

    embedding_provider = EmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
    )
    chroma_service = ChromaService(
        persist_directory=str(chroma_dir),
        embedding_function=embedding_provider.get_embeddings(),
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
    )


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

    lines.append("RAG Evaluation Report")
    lines.append("=" * 21)
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
    results: list[dict[str, Any]] = []

    for example in dataset["examples"]:
        if skip_generation:
            response = chat_service.prepare(question=example["question"])
            actual_answer = None
            answer_correct = None
            generation_skipped = True
        else:
            response = await chat_service.ask(question=example["question"])
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

    top_k = args.top_k or settings.top_k
    max_context_chunks = args.max_context_chunks or settings.max_context_chunks
    chunk_size = args.chunk_size or settings.chunk_size
    chunk_overlap = args.chunk_overlap or settings.chunk_overlap

    with TemporaryDirectory(prefix="rag-eval-") as temp_dir:
        chroma_dir = Path(temp_dir) / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)

        chat_service = build_chat_service(
            settings=settings,
            chroma_dir=chroma_dir,
            top_k=top_k,
            max_context_chunks=max_context_chunks,
        )
        indexed_chunks = index_fixture_docs(
            docs_dir=args.docs_dir,
            chat_service=chat_service,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        results = await evaluate_examples(
            chat_service=chat_service,
            dataset=dataset,
            skip_generation=args.skip_generation,
        )

    report = {
        "dataset": {
            "path": str(args.dataset),
            "doc_count": len(list(args.docs_dir.glob("*"))),
            "example_count": len(dataset["examples"]),
            "indexed_chunk_count": len(indexed_chunks),
        },
        "config": {
            "ollama_base_url": settings.ollama_base_url,
            "chat_model": settings.ollama_chat_model,
            "embed_model": settings.ollama_embed_model,
            "top_k": top_k,
            "max_context_chunks": max_context_chunks,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "skip_generation": args.skip_generation,
        },
        "summary": summarize_metrics(results),
        "results": results,
    }

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
