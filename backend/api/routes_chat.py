from typing import Optional, List
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from core.dependencies import get_chat_service
from services.chat_service import ChatService

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    document_ids: Optional[List[str]] = None


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
    result = await chat_service.ask(
        question=payload.question,
        document_ids=payload.document_ids,
    )
    return result


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
    generator = chat_service.stream_answer(
        question=payload.question,
        document_ids=payload.document_ids,
    )
    return StreamingResponse(generator, media_type="text/event-stream")
