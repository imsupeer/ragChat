import json
import asyncio
from collections.abc import AsyncIterator
from typing import Optional, List
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from core.observability import (
    build_cancelled_generation_debug,
    build_failed_generation_debug,
    build_generation_debug,
    elapsed_ms,
    log_api_exception,
    log_structured,
    safe_chat_error_message,
    safe_generation_error_message,
)
from core.dependencies import get_chat_service, get_sqlite_store
from services.chat_service import ChatService
from services.metrics import get_local_metrics
from services.sqlite_store import SQLiteStore

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    document_ids: Optional[List[str]] = None
    chat_id: Optional[str] = None
    regenerate: bool = False


def ensure_chat_exists(sqlite_store: SQLiteStore, chat_id: Optional[str]) -> None:
    if chat_id and not sqlite_store.get_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found.")


def format_sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def chat_history_for_rewrite(
    sqlite_store: SQLiteStore,
    chat_id: Optional[str],
    regenerate: bool,
) -> list[dict]:
    if not chat_id:
        return []

    history = sqlite_store.list_messages(chat_id)
    if regenerate:
        while history and history[-1].get("role") == "assistant":
            history = history[:-1]

    return history


async def _persist_assistant_message(
    sqlite_store: SQLiteStore,
    *,
    chat_id: str,
    content: str,
    sources: list,
    debug: dict,
    regenerate: bool,
) -> None:
    if regenerate:
        await asyncio.to_thread(sqlite_store.delete_last_assistant_message, chat_id)
    await asyncio.to_thread(
        sqlite_store.add_message,
        chat_id,
        "assistant",
        content,
        sources,
        debug,
    )


async def iter_chat_stream_events(
    *,
    request: Request,
    payload: ChatRequest,
    prepared: dict,
    chat_service: ChatService,
    sqlite_store: SQLiteStore,
    request_started: float,
) -> AsyncIterator[str]:
    user_persisted = False
    full_answer = ""
    generation_started = None
    client_disconnected = False

    try:
        yield format_sse(
            {
                "type": "sources",
                "sources": prepared["sources"],
                "debug": prepared["debug"],
            }
        )

        if await request.is_disconnected():
            client_disconnected = True
            log_structured(
                "rag.generation.cancelled",
                prepared["trace_id"],
                {"reason": "client_disconnected", "stage": "before_generation"},
            )
            return

        if payload.chat_id and not payload.regenerate:
            await asyncio.to_thread(
                sqlite_store.add_message,
                payload.chat_id,
                "user",
                payload.question,
            )
            user_persisted = True

        generation_started = perf_counter()

        stream_iter = chat_service.llm_provider.stream(prepared["prompt"]).__aiter__()
        while True:
            if await request.is_disconnected():
                client_disconnected = True
                break

            try:
                token = await stream_iter.__anext__()
            except StopAsyncIteration:
                break

            full_answer += token
            yield format_sse({"type": "token", "token": token})

        if client_disconnected:
            generation_finished = perf_counter()
            generation_debug = build_cancelled_generation_debug(
                model=chat_service.llm_provider.model,
                output_text=full_answer,
                latency_ms=elapsed_ms(generation_started, generation_finished),
                keep_alive=chat_service.llm_provider.keep_alive,
            )
            log_structured(
                "rag.generation.cancelled",
                prepared["trace_id"],
                {
                    "reason": "client_disconnected",
                    "partial_answer": bool(full_answer),
                    "streaming": True,
                },
            )
            get_local_metrics().increment("chat.stream.client_disconnected")

            if payload.chat_id and (full_answer or user_persisted):
                debug = {
                    **prepared["debug"],
                    "generation": generation_debug,
                    "total_latency_ms": elapsed_ms(request_started, perf_counter()),
                }
                await _persist_assistant_message(
                    sqlite_store,
                    chat_id=payload.chat_id,
                    content=full_answer,
                    sources=prepared["sources"],
                    debug=debug,
                    regenerate=payload.regenerate,
                )
            return

        generation_finished = perf_counter()
        generation_debug = build_generation_debug(
            model=chat_service.llm_provider.model,
            output_text=full_answer,
            latency_ms=elapsed_ms(generation_started, generation_finished),
            keep_alive=chat_service.llm_provider.keep_alive,
        )
        generation_debug["status"] = "completed"
        log_structured("rag.generation", prepared["trace_id"], generation_debug)
        get_local_metrics().increment("chat.stream.completed")
        if payload.regenerate:
            get_local_metrics().increment("chat.regenerate")

        total_latency_ms = elapsed_ms(request_started, perf_counter())
        debug = {
            **prepared["debug"],
            "generation": generation_debug,
            "total_latency_ms": total_latency_ms,
        }
        log_structured(
            "rag.request.completed",
            prepared["trace_id"],
            {
                "total_latency_ms": total_latency_ms,
                "source_count": len(prepared["sources"]),
                "streaming": True,
            },
        )

        if payload.chat_id:
            await _persist_assistant_message(
                sqlite_store,
                chat_id=payload.chat_id,
                content=full_answer,
                sources=prepared["sources"],
                debug=debug,
                regenerate=payload.regenerate,
            )

        yield format_sse({"type": "done", "debug": debug})

    except Exception as exc:
        if await request.is_disconnected():
            log_structured(
                "rag.generation.cancelled",
                prepared["trace_id"],
                {
                    "reason": "client_disconnected",
                    "stage": "generation_error",
                    "error": str(exc) or "Generation failed.",
                },
            )
            return

        error_code = "generation_failed"
        safe_message = safe_generation_error_message(exc)
        log_api_exception("chat.stream.generation", exc)
        get_local_metrics().increment("chat.stream.failed")
        log_structured(
            "rag.generation.failed",
            prepared["trace_id"],
            {"error": safe_message, "streaming": True},
        )

        generation_latency_ms = (
            elapsed_ms(generation_started, perf_counter())
            if generation_started is not None
            else 0.0
        )
        generation_debug = build_failed_generation_debug(
            model=chat_service.llm_provider.model,
            output_text=full_answer,
            latency_ms=generation_latency_ms,
            error_code=error_code,
            error_message=safe_message,
            keep_alive=chat_service.llm_provider.keep_alive,
        )
        debug = {
            **prepared["debug"],
            "generation": generation_debug,
            "total_latency_ms": elapsed_ms(request_started, perf_counter()),
        }

        if payload.chat_id and (user_persisted or payload.regenerate):
            await _persist_assistant_message(
                sqlite_store,
                chat_id=payload.chat_id,
                content=full_answer or safe_message,
                sources=prepared["sources"],
                debug=debug,
                regenerate=payload.regenerate,
            )

        yield format_sse(
            {
                "type": "error",
                "message": safe_message,
                "code": error_code,
                "recoverable": True,
            }
        )


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
    ensure_chat_exists(sqlite_store, payload.chat_id)
    history = chat_history_for_rewrite(
        sqlite_store, payload.chat_id, payload.regenerate
    )

    try:
        result = await chat_service.ask(
            question=payload.question,
            document_ids=payload.document_ids,
            chat_history=history if payload.chat_id else None,
        )
    except Exception as exc:
        log_api_exception("chat.ask", exc)
        raise HTTPException(
            status_code=500,
            detail=safe_chat_error_message(exc),
        ) from exc

    if payload.chat_id:
        sqlite_store.add_message(
            chat_id=payload.chat_id,
            role="user",
            content=payload.question,
        )
        sqlite_store.add_message(
            chat_id=payload.chat_id,
            role="assistant",
            content=result["answer"],
            sources=result["sources"],
            debug=result.get("debug"),
        )

    return result


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
    ensure_chat_exists(sqlite_store, payload.chat_id)
    history = chat_history_for_rewrite(
        sqlite_store, payload.chat_id, payload.regenerate
    )

    if payload.regenerate:
        get_local_metrics().increment("chat.regenerate")

    request_started = perf_counter()

    try:
        prepared = await chat_service.prepare_request(
            question=payload.question,
            document_ids=payload.document_ids,
            chat_history=history if payload.chat_id else None,
        )
        get_local_metrics().increment("chat.prepare.attempt")
    except Exception as exc:
        log_api_exception("chat.stream.prepare", exc)
        raise HTTPException(
            status_code=500,
            detail=safe_chat_error_message(exc),
        ) from exc

    async def generator():
        async for event in iter_chat_stream_events(
            request=request,
            payload=payload,
            prepared=prepared,
            chat_service=chat_service,
            sqlite_store=sqlite_store,
            request_started=request_started,
        ):
            yield event

    return StreamingResponse(generator(), media_type="text/event-stream")
