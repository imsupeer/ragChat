from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_chat import router as chat_router
from core.dependencies import get_chat_service, get_sqlite_store


class FakeChatService:
    async def ask(self, question: str, document_ids=None):
        return {
            "answer": f"Echo: {question}",
            "sources": [
                {
                    "source": "sample.md",
                    "chunk_id": "chunk-1",
                    "preview": "sample preview",
                }
            ],
            "debug": {
                "trace_id": "trace-1",
                "retrieval": {
                    "latency_ms": 1.0,
                    "top_k": 5,
                    "max_context_chunks": 5,
                    "hybrid_enabled": False,
                    "retrieval_mode": "dense",
                    "document_ids": document_ids or [],
                    "retrieved_count": 1,
                    "used_count": 1,
                    "results": [],
                },
                "prompt": {
                    "latency_ms": 1.0,
                    "used_chunk_count": 1,
                    "used_chunk_ids": ["chunk-1"],
                    "context_length_chars": 10,
                    "context_token_estimate": 2,
                    "prompt_length_chars": 20,
                    "prompt_token_estimate": 4,
                },
            },
        }


class FakeSQLiteStore:
    def __init__(self) -> None:
        self.messages = []

    def add_message(self, chat_id: str, role: str, content: str, sources=None):
        record = {
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "sources": sources or [],
        }
        self.messages.append(record)
        return record


def test_chat_endpoint_returns_valid_response_and_persists_messages():
    app = FastAPI()
    app.include_router(chat_router)

    fake_chat_service = FakeChatService()
    fake_sqlite_store = FakeSQLiteStore()

    app.dependency_overrides[get_chat_service] = lambda: fake_chat_service
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={
                "question": "What stores document registry entries?",
                "chat_id": "chat-1",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Echo: What stores document registry entries?"
    assert payload["sources"][0]["chunk_id"] == "chunk-1"
    assert payload["debug"]["trace_id"] == "trace-1"
    assert [message["role"] for message in fake_sqlite_store.messages] == [
        "user",
        "assistant",
    ]
