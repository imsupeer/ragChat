from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.dependencies import get_sqlite_store
from services.sqlite_store import SQLiteStore

router = APIRouter(prefix="/chats", tags=["chats"])


class CreateChatRequest(BaseModel):
    title: str | None = None


class UpdateChatRequest(BaseModel):
    title: str


@router.get("")
def list_chats(sqlite_store: SQLiteStore = Depends(get_sqlite_store)):
    return {"chats": sqlite_store.list_chats()}


@router.post("")
def create_chat(
    payload: CreateChatRequest,
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
    chat = sqlite_store.create_chat(title=payload.title)
    return {"chat": chat}


@router.patch("/{chat_id}")
def update_chat(
    chat_id: str,
    payload: UpdateChatRequest,
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
    chat = sqlite_store.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Chat title cannot be empty.")

    updated_chat = sqlite_store.update_chat_title(chat_id, title)
    return {"chat": updated_chat}


@router.delete("/{chat_id}")
def delete_chat(
    chat_id: str,
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
    chat = sqlite_store.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    sqlite_store.delete_chat(chat_id)
    return {"message": "Chat deleted successfully.", "chat_id": chat_id}


@router.get("/{chat_id}/messages")
def list_chat_messages(
    chat_id: str,
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
):
    chat = sqlite_store.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    return {
        "chat": chat,
        "messages": sqlite_store.list_messages(chat_id),
    }
