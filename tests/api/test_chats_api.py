from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_chats import router as chats_router
from core.dependencies import get_sqlite_store
from services.sqlite_store import SQLiteStore


class FakeSQLiteStore:
    def __init__(self) -> None:
        self.chats = {
            "chat-1": {
                "id": "chat-1",
                "title": "Original Title",
                "created_at": "2026-01-01T00:00:00",
            }
        }

    def list_chats(self):
        return list(self.chats.values())

    def create_chat(self, title=None):
        chat = {
            "id": "chat-2",
            "title": title or "New Chat",
            "created_at": "2026-01-02T00:00:00",
        }
        self.chats[chat["id"]] = chat
        return chat

    def get_chat(self, chat_id: str):
        return self.chats.get(chat_id)

    def update_chat_title(self, chat_id: str, title: str):
        self.chats[chat_id]["title"] = title
        return self.chats[chat_id]

    def delete_chat(self, chat_id: str):
        self.chats.pop(chat_id, None)

    def list_messages(self, chat_id: str):
        return []


def test_chats_can_be_renamed():
    app = FastAPI()
    app.include_router(chats_router)

    fake_sqlite_store = FakeSQLiteStore()
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.patch(
            "/chats/chat-1",
            json={"title": "Renamed Chat"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat"]["id"] == "chat-1"
    assert payload["chat"]["title"] == "Renamed Chat"


def test_chat_rename_rejects_empty_titles():
    app = FastAPI()
    app.include_router(chats_router)

    fake_sqlite_store = FakeSQLiteStore()
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.patch(
            "/chats/chat-1",
            json={"title": "   "},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Chat title cannot be empty."


def test_list_chat_messages_returns_persisted_debug_metadata(tmp_path):
    db_path = tmp_path / "app.db"
    store = SQLiteStore(str(db_path))
    chat = store.create_chat()
    store.add_message(chat_id=chat["id"], role="user", content="Question?")
    store.add_message(
        chat_id=chat["id"],
        role="assistant",
        content="Answer.",
        sources=[{"chunk_id": "chunk-1"}],
        debug={
            "trace_id": "trace-persisted",
            "prompt": {"used_chunk_count": 1, "used_chunk_ids": ["chunk-1"], "used_chunks": []},
        },
    )

    app = FastAPI()
    app.include_router(chats_router)
    app.dependency_overrides[get_sqlite_store] = lambda: store

    with TestClient(app) as client:
        response = client.get(f"/chats/{chat['id']}/messages")

    assert response.status_code == 200
    payload = response.json()
    assistant = payload["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["debug"]["trace_id"] == "trace-persisted"
