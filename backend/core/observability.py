import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.documents import Document

logger = logging.getLogger("uvicorn.error")

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
INTERNAL_METADATA_KEYS = {
    "_retrieval_score",
    "_retrieval_rank",
    "_retrieval_score_type",
    "_retrieval_method",
    "_retrieval_methods",
    "_dense_score",
    "_dense_rank",
    "_lexical_score",
    "_lexical_rank",
    "_hybrid_fused_score",
    "_rerank_score",
    "_rerank_rank",
}


def elapsed_ms(start_time: float, end_time: float) -> float:
    return round((end_time - start_time) * 1000, 2)


def estimate_token_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return len(TOKEN_PATTERN.findall(stripped))


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(key): _sanitize_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]

    return str(value)


def clean_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}

    for key, value in (metadata or {}).items():
        if key in INTERNAL_METADATA_KEYS:
            continue
        cleaned[key] = _sanitize_value(value)

    return cleaned


def get_chunk_id(doc: Document) -> str | None:
    metadata = doc.metadata or {}
    chunk_id = metadata.get("chunk_id") or getattr(doc, "id", None)
    if chunk_id:
        return str(chunk_id)

    document_id = metadata.get("document_id")
    chunk_index = metadata.get("chunk_index")
    if document_id is not None and chunk_index is not None:
        return f"{document_id}:{chunk_index}"

    return None


def get_retrieval_score(doc: Document) -> float | None:
    score = (doc.metadata or {}).get("_retrieval_score")
    if score is None:
        return None

    try:
        return float(score)
    except (TypeError, ValueError):
        return None


def get_retrieval_rank(doc: Document) -> int | None:
    rank = (doc.metadata or {}).get("_retrieval_rank")
    if rank is None:
        return None

    try:
        return int(rank)
    except (TypeError, ValueError):
        return None


def get_stage_rank(doc: Document) -> int | None:
    rerank_rank = get_numeric_metadata_value(doc, "_rerank_rank")
    if rerank_rank is not None:
        return int(rerank_rank)
    return get_retrieval_rank(doc)


def get_stage_score(doc: Document) -> float | None:
    rerank_score = get_numeric_metadata_value(doc, "_rerank_score")
    if rerank_score is not None:
        return float(rerank_score)
    return get_retrieval_score(doc)


def get_stage_score_type(doc: Document) -> str | None:
    rerank_score = get_numeric_metadata_value(doc, "_rerank_score")
    if rerank_score is not None:
        return "rerank"
    return (doc.metadata or {}).get("_retrieval_score_type")


def get_numeric_metadata_value(doc: Document, key: str) -> float | int | None:
    value = (doc.metadata or {}).get(key)
    if value is None:
        return None

    try:
        if isinstance(value, int):
            return value
        return float(value)
    except (TypeError, ValueError):
        return None


def build_chunk_debug(doc: Document) -> dict[str, Any]:
    metadata = clean_metadata(doc.metadata)
    score = get_stage_score(doc)
    rank = get_stage_rank(doc)
    retrieval_methods = list((doc.metadata or {}).get("_retrieval_methods") or [])
    retrieval_method = (doc.metadata or {}).get("_retrieval_method")
    score_type = get_stage_score_type(doc)

    return {
        "rank": rank,
        "chunk_id": get_chunk_id(doc),
        "document_id": metadata.get("document_id"),
        "source": metadata.get("source"),
        "page": metadata.get("page"),
        "chunk_index": metadata.get("chunk_index"),
        "section_title": metadata.get("section_title"),
        "section_path": metadata.get("section_path"),
        "score": score,
        "score_type": score_type,
        "retrieval_method": retrieval_method,
        "retrieval_methods": retrieval_methods,
        "retrieval_rank": get_retrieval_rank(doc),
        "retrieval_score": get_retrieval_score(doc),
        "retrieval_score_type": (doc.metadata or {}).get("_retrieval_score_type"),
        "rerank_rank": get_numeric_metadata_value(doc, "_rerank_rank"),
        "rerank_score": get_numeric_metadata_value(doc, "_rerank_score"),
        "dense_rank": get_numeric_metadata_value(doc, "_dense_rank"),
        "dense_score": get_numeric_metadata_value(doc, "_dense_score"),
        "lexical_rank": get_numeric_metadata_value(doc, "_lexical_rank"),
        "lexical_score": get_numeric_metadata_value(doc, "_lexical_score"),
        "fused_score": get_numeric_metadata_value(doc, "_hybrid_fused_score"),
        "metadata": metadata,
        "preview": doc.page_content[:280],
    }


def build_prompt_debug(
    prompt: str,
    context: str,
    used_docs: list[Document],
    latency_ms: float,
) -> dict[str, Any]:
    return {
        "latency_ms": latency_ms,
        "used_chunk_count": len(used_docs),
        "used_chunk_ids": [get_chunk_id(doc) for doc in used_docs if get_chunk_id(doc)],
        "context_length_chars": len(context),
        "context_token_estimate": estimate_token_count(context),
        "prompt_length_chars": len(prompt),
        "prompt_token_estimate": estimate_token_count(prompt),
    }


def build_generation_debug(
    model: str, output_text: str, latency_ms: float
) -> dict[str, Any]:
    return {
        "model": model,
        "latency_ms": latency_ms,
        "output_length_chars": len(output_text),
        "output_token_estimate": estimate_token_count(output_text),
    }


def log_structured(event: str, trace_id: str, payload: dict[str, Any]) -> None:
    logger.info(
        json.dumps(
            {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trace_id": trace_id,
                **payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
