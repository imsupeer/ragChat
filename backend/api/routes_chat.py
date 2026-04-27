import json
import asyncio
from typing import Optional, List
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from core.observability import build_generation_debug, elapsed_ms, log_structured
from core.dependencies import get_chat_service, get_sqlite_store
from services.chat_service import ChatService
from services.sqlite_store import SQLiteStore

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    document_ids: Optional[List[str]] = None
    chat_id: Optional[str] = None


def ensure_chat_exists(sqlite_store: SQLiteStore, chat_id: Optional[str]) -> None:
    if chat_id and not sqlite_store.get_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found.")


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
    ensure_chat_exists(sqlite_store, payload.chat_id)

    if payload.chat_id:
        sqlite_store.add_message(
            chat_id=payload.chat_id,
            role="user",
            content=payload.question,
        )

    result = await chat_service.ask(
        question=payload.question,
        document_ids=payload.document_ids,
    )

    if payload.chat_id:
        sqlite_store.add_message(
            chat_id=payload.chat_id,
            role="assistant",
            content=result["answer"],
            sources=result["sources"],
        )

    return result


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
    ensure_chat_exists(sqlite_store, payload.chat_id)

    request_started = perf_counter()
    prepared = await asyncio.to_thread(
        chat_service.prepare,
        question=payload.question,
        document_ids=payload.document_ids,
    )

    async def generator():
        if payload.chat_id:
            sqlite_store.add_message(
                chat_id=payload.chat_id,
                role="user",
                content=payload.question,
            )

        yield f"data: {json.dumps({'type': 'sources', 'sources': prepared['sources'], 'debug': prepared['debug']}, ensure_ascii=False)}\n\n"

        full_answer = ""
        generation_started = perf_counter()

        async for token in chat_service.ollama_service.stream(prepared["prompt"]):
            full_answer += token
            yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"

        generation_finished = perf_counter()
        generation_debug = build_generation_debug(
            model=chat_service.ollama_service.model,
            output_text=full_answer,
            latency_ms=elapsed_ms(generation_started, generation_finished),
        )
        log_structured("rag.generation", prepared["trace_id"], generation_debug)

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
            sqlite_store.add_message(
                chat_id=payload.chat_id,
                role="assistant",
                content=full_answer,
                sources=prepared["sources"],
            )

        yield f"data: {json.dumps({'type': 'done', 'debug': debug}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")
