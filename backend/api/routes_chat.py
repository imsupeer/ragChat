import json
from typing import Optional, List
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from core.dependencies import get_chat_service, get_sqlite_store
from services.chat_service import ChatService
from services.sqlite_store import SQLiteStore

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    document_ids: Optional[List[str]] = None
    chat_id: Optional[str] = None


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
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
    prepared = chat_service.prepare(
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

        yield f"data: {json.dumps({'type': 'sources', 'sources': prepared['sources']}, ensure_ascii=False)}\n\n"

        full_answer = ""

        async for token in chat_service.ollama_service.stream(prepared["prompt"]):
            full_answer += token
            yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"

        if payload.chat_id:
            sqlite_store.add_message(
                chat_id=payload.chat_id,
                role="assistant",
                content=full_answer,
                sources=prepared["sources"],
            )

        yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(generator(), media_type="text/event-stream")
