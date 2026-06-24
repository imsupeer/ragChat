from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark local retrieval latency with optional fake embeddings."
    )
    parser.add_argument(
        "--fake-embeddings",
        action="store_true",
        help="Use deterministic fake embeddings (no Ollama required).",
    )
    parser.add_argument(
        "--from-eval",
        action="store_true",
        help="Index eval fixture docs and use eval dataset questions.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=ROOT_DIR / "scripts" / "eval_data" / "docs",
        help="Fixture docs directory when using --from-eval.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT_DIR / "scripts" / "eval_data" / "dataset.json",
        help="Eval dataset JSON when using --from-eval.",
    )
    parser.add_argument(
        "--queries",
        nargs="*",
        default=None,
        help="Explicit queries to benchmark.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=5,
        help="Number of timed runs per query after warmup.",
    )
    parser.add_argument(
        "--hybrid",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Benchmark hybrid retrieval (lexical + dense).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Retrieval top_k.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    return round(ordered[index], 2)


def load_queries(args: argparse.Namespace) -> list[dict]:
    if args.queries:
        return [{"question": query, "document_ids": None} for query in args.queries]

    if not args.from_eval:
        return [
            {"question": "What are the limitations?", "document_ids": None},
            {"question": "Does PDF handling include OCR?", "document_ids": None},
        ]

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    queries = []
    for example in dataset.get("examples", []):
        if not example.get("question"):
            continue
        queries.append(
            {
                "question": example["question"],
                "document_ids": example.get("document_ids"),
            }
        )
    return queries


def build_services(args: argparse.Namespace, chroma_dir: Path):
    from core.config import Settings
    from retrieval.retriever import Retriever
    from services.chroma_service import ChromaService

    settings = Settings()

    if args.fake_embeddings:
        from embeddings.fake_embeddings import FakeEmbeddings

        embedding_function = FakeEmbeddings()
    else:
        from embeddings.embedding_provider import EmbeddingProvider

        embedding_function = EmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embed_model,
        ).get_embeddings()

    chroma_service = ChromaService(
        persist_directory=str(chroma_dir),
        embedding_function=embedding_function,
    )
    retriever = Retriever(
        chroma_service=chroma_service,
        top_k=args.top_k,
        enable_hybrid=args.hybrid,
    )
    return chroma_service, retriever, settings


def index_eval_docs(docs_dir: Path, chroma_service, settings) -> int:
    from ingestion.processor import process_document

    chunk_count = 0
    for doc_path in sorted(docs_dir.glob("*")):
        if not doc_path.is_file():
            continue

        chunks = process_document(
            file_path=str(doc_path),
            original_filename=doc_path.name,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        chroma_service.add_documents(document_id=doc_path.stem, docs=chunks)
        chunk_count += len(chunks)

    return chunk_count


def run_benchmark(
    retriever,
    chroma_service,
    queries: list[dict],
    *,
    repeat: int,
) -> dict:
    warmup = queries[0] if queries else {"question": "warmup", "document_ids": None}
    retriever.search(
        question=warmup["question"],
        document_ids=warmup.get("document_ids"),
    )

    per_query: list[dict] = []
    all_latencies: list[float] = []

    for item in queries:
        latencies: list[float] = []
        for _ in range(repeat):
            started = time.perf_counter()
            retriever.search(
                question=item["question"],
                document_ids=item.get("document_ids"),
            )
            latencies.append(round((time.perf_counter() - started) * 1000, 2))

        all_latencies.extend(latencies)
        per_query.append(
            {
                "question": item["question"],
                "document_ids": item.get("document_ids"),
                "min_ms": min(latencies),
                "avg_ms": round(statistics.mean(latencies), 2),
                "p95_ms": percentile(latencies, 95),
                "runs": latencies,
            }
        )

    cache_stats = chroma_service.get_last_lexical_cache_stats()

    return {
        "summary": {
            "query_count": len(queries),
            "repeat": repeat,
            "min_ms": min(all_latencies) if all_latencies else 0.0,
            "avg_ms": round(statistics.mean(all_latencies), 2) if all_latencies else 0.0,
            "p95_ms": percentile(all_latencies, 95),
        },
        "lexical_cache": cache_stats,
        "queries": per_query,
    }


def format_text_report(report: dict, *, hybrid: bool, chunk_count: int) -> str:
    summary = report["summary"]
    cache = report.get("lexical_cache") or {}
    lines = [
        "Retrieval Benchmark",
        "===================",
        f"Mode: {'hybrid' if hybrid else 'dense'}",
        f"Indexed chunks: {chunk_count}",
        f"Queries: {summary['query_count']} x {summary['repeat']} runs",
        "",
        "Latency (ms)",
        f"  min: {summary['min_ms']}",
        f"  avg: {summary['avg_ms']}",
        f"  p95: {summary['p95_ms']}",
        "",
        "Lexical cache (last query)",
        f"  cache_hit: {cache.get('cache_hit')}",
        f"  corpus_cache_hit: {cache.get('corpus_cache_hit')}",
        f"  index_cache_hit: {cache.get('index_cache_hit')}",
        f"  corpus_size: {cache.get('corpus_size')}",
        f"  cache_key: {cache.get('cache_key')}",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    queries = load_queries(args)

    if not queries:
        print("No queries to benchmark.", file=sys.stderr)
        return 1

    with TemporaryDirectory(prefix="rag-benchmark-", ignore_cleanup_errors=True) as temp_dir:
        chroma_dir = Path(temp_dir) / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)

        chroma_service, retriever, settings = build_services(args, chroma_dir)
        chunk_count = 0
        if args.from_eval or args.docs_dir.exists():
            chunk_count = index_eval_docs(args.docs_dir, chroma_service, settings)

        report = run_benchmark(
            retriever,
            chroma_service,
            queries,
            repeat=max(args.repeat, 1),
        )
        report["config"] = {
            "fake_embeddings": args.fake_embeddings,
            "hybrid": args.hybrid,
            "top_k": args.top_k,
            "from_eval": args.from_eval,
        }
        report["indexed_chunk_count"] = chunk_count

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            format_text_report(
                report,
                hybrid=args.hybrid,
                chunk_count=chunk_count,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
