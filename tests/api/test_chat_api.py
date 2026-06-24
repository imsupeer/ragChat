import asyncio
import json
from time import perf_counter

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_chat import ChatRequest, iter_chat_stream_events, router as chat_router
from core.dependencies import get_chat_service, get_sqlite_store


class FakeOllamaService:
    def __init__(self, tokens=None, fail=False):
        self.model = "test-model"
        self.keep_alive = "5m"
        self.tokens = tokens or ["Hello", " world"]
        self.fail = fail

    async def stream(self, prompt: str):
        if self.fail:
            raise RuntimeError("Ollama unavailable")
        for token in self.tokens:
            yield token


class FakeChatService:
    def __init__(self, ollama_service=None) -> None:
        self.ask_calls = []
        self.prepare_calls = []
        self.ollama_service = ollama_service or FakeOllamaService()

    async def ask(self, question: str, document_ids=None, chat_history=None, retrieval_question=None, query_rewriting_debug=None):
        self.ask_calls.append(
            {
                "question": question,
                "document_ids": document_ids,
                "chat_history": chat_history,
                "retrieval_question": retrieval_question,
            }
        )
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
                "query_rewriting": query_rewriting_debug
                or {
                    "enabled": False,
                    "used": False,
                    "original_question": question,
                    "rewritten_query": retrieval_question or question,
                    "history_turns_used": 0,
                    "latency_ms": 0.0,
                },
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

    def prepare(
        self,
        user_question: str,
        document_ids=None,
        retrieval_question=None,
        query_rewriting_debug=None,
    ):
        self.prepare_calls.append(
            {
                "user_question": user_question,
                "document_ids": document_ids,
                "retrieval_question": retrieval_question,
            }
        )
        return {
            "trace_id": "trace-stream",
            "prompt": f"Prompt for {user_question}",
            "docs": [],
            "sources": [
                {
                    "source": "sample.md",
                    "chunk_id": "chunk-1",
                    "preview": "sample preview",
                }
            ],
            "debug": {
                "trace_id": "trace-stream",
                "query_rewriting": query_rewriting_debug
                or {
                    "enabled": False,
                    "used": False,
                    "original_question": user_question,
                    "rewritten_query": retrieval_question or user_question,
                    "history_turns_used": 0,
                    "latency_ms": 0.0,
                },
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

    async def prepare_request(
        self,
        question: str,
        document_ids=None,
        chat_history=None,
        retrieval_question=None,
        query_rewriting_debug=None,
    ):
        return self.prepare(
            user_question=question,
            document_ids=document_ids,
            retrieval_question=retrieval_question,
            query_rewriting_debug=query_rewriting_debug,
        )


class FakeSQLiteStore:
    def __init__(self) -> None:
        self.messages = []
        self.chats = {"chat-1": {"id": "chat-1", "title": "Existing Chat"}}

    def get_chat(self, chat_id: str):
        return self.chats.get(chat_id)

    def list_messages(self, chat_id: str):
        return [
            message
            for message in self.messages
            if message.get("chat_id") == chat_id
        ]

    def add_message(self, chat_id: str, role: str, content: str, sources=None, debug=None):
        record = {
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "sources": sources or [],
        }
        if debug is not None:
            record["debug"] = debug
        self.messages.append(record)
        return record

    def delete_last_assistant_message(self, chat_id: str) -> None:
        for index in range(len(self.messages) - 1, -1, -1):
            message = self.messages[index]
            if message["chat_id"] == chat_id and message["role"] == "assistant":
                del self.messages[index]
                return


def parse_sse_events(response):
    events = []
    for chunk in response.text.split("\n\n"):
        if not chunk.startswith("data: "):
            continue
        import json

        events.append(json.loads(chunk.replace("data: ", "", 1)))
    return events


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
    assert fake_sqlite_store.messages[-1]["debug"]["trace_id"] == "trace-1"


def test_chat_endpoint_rejects_missing_chat_id_before_generation():
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
                "question": "Will this be generated?",
                "chat_id": "missing-chat",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat not found."
    assert fake_chat_service.ask_calls == []
    assert fake_sqlite_store.messages == []


def test_chat_stream_emits_sources_tokens_and_done():
    app = FastAPI()
    app.include_router(chat_router)

    fake_chat_service = FakeChatService()
    fake_sqlite_store = FakeSQLiteStore()

    app.dependency_overrides[get_chat_service] = lambda: fake_chat_service
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={"question": "Stream this", "chat_id": "chat-1"},
        )

    assert response.status_code == 200
    events = parse_sse_events(response)
    assert events[0]["type"] == "sources"
    assert events[1]["type"] == "token"
    assert events[2]["type"] == "token"
    assert events[-1]["type"] == "done"
    assert fake_sqlite_store.messages[-1]["content"] == "Hello world"
    assert [message["role"] for message in fake_sqlite_store.messages] == [
        "user",
        "assistant",
    ]


def test_chat_stream_persists_user_message_only_after_prepare():
    fake_sqlite_store = FakeSQLiteStore()

    class FailingPrepareService(FakeChatService):
        async def prepare_request(self, **kwargs):
            raise RuntimeError("Retrieval failed")

    app = FastAPI()
    app.include_router(chat_router)
    app.dependency_overrides[get_chat_service] = lambda: FailingPrepareService()
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={"question": "Should not persist", "chat_id": "chat-1"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Retrieval failed"
    assert fake_sqlite_store.messages == []


def test_chat_stream_emits_structured_error_on_generation_failure():
    app = FastAPI()
    app.include_router(chat_router)

    fake_chat_service = FakeChatService(
        ollama_service=FakeOllamaService(fail=True),
    )
    fake_sqlite_store = FakeSQLiteStore()

    app.dependency_overrides[get_chat_service] = lambda: fake_chat_service
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={"question": "Fail please", "chat_id": "chat-1"},
        )

    assert response.status_code == 200
    events = parse_sse_events(response)
    assert events[0]["type"] == "sources"
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "generation_failed"
    assert events[-1]["recoverable"] is True
    assert events[-1]["message"] == "Ollama unavailable"
    assert fake_sqlite_store.messages[0]["role"] == "user"
    assert fake_sqlite_store.messages[1]["role"] == "assistant"
    assert fake_sqlite_store.messages[1]["content"] == "Ollama unavailable"
    assistant_debug = fake_sqlite_store.messages[1]["debug"]
    assert assistant_debug["trace_id"] == "trace-stream"
    assert assistant_debug["retrieval"]["retrieved_count"] == 1
    assert assistant_debug["prompt"]["used_chunk_ids"] == ["chunk-1"]
    assert assistant_debug["generation"]["status"] == "failed"
    assert assistant_debug["generation"]["error_code"] == "generation_failed"
    assert assistant_debug["generation"]["error_message"] == "Ollama unavailable"
    assert assistant_debug["generation"]["partial_answer"] is False
    assert fake_sqlite_store.messages[1]["sources"][0]["chunk_id"] == "chunk-1"


def test_chat_stream_regenerate_skips_duplicate_user_message():
    app = FastAPI()
    app.include_router(chat_router)

    fake_chat_service = FakeChatService()
    fake_sqlite_store = FakeSQLiteStore()
    fake_sqlite_store.add_message("chat-1", "user", "Original question")
    fake_sqlite_store.add_message("chat-1", "assistant", "Old answer")

    app.dependency_overrides[get_chat_service] = lambda: fake_chat_service
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={
                "question": "Original question",
                "chat_id": "chat-1",
                "regenerate": True,
            },
        )

    assert response.status_code == 200
    events = parse_sse_events(response)
    assert events[-1]["type"] == "done"
    assert [message["role"] for message in fake_sqlite_store.messages] == [
        "user",
        "assistant",
    ]
    assert fake_sqlite_store.messages[-1]["content"] == "Hello world"
    assert fake_sqlite_store.messages[-1]["debug"]["trace_id"] == "trace-stream"
    assert "generation" in fake_sqlite_store.messages[-1]["debug"]


def test_chat_stream_persists_assistant_debug_metadata():
    app = FastAPI()
    app.include_router(chat_router)

    fake_chat_service = FakeChatService()
    fake_sqlite_store = FakeSQLiteStore()

    app.dependency_overrides[get_chat_service] = lambda: fake_chat_service
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={"question": "Stream debug", "chat_id": "chat-1"},
        )

    assert response.status_code == 200
    assert fake_sqlite_store.messages[-1]["debug"]["trace_id"] == "trace-stream"
    assert "generation" in fake_sqlite_store.messages[-1]["debug"]


def test_chat_stream_regenerate_persists_replacement_debug_metadata():
    app = FastAPI()
    app.include_router(chat_router)

    fake_chat_service = FakeChatService()
    fake_sqlite_store = FakeSQLiteStore()
    fake_sqlite_store.add_message("chat-1", "user", "Original question")
    fake_sqlite_store.add_message(
        "chat-1",
        "assistant",
        "Old answer",
        debug={"trace_id": "old-trace"},
    )

    app.dependency_overrides[get_chat_service] = lambda: fake_chat_service
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={
                "question": "Original question",
                "chat_id": "chat-1",
                "regenerate": True,
            },
        )

    assert response.status_code == 200
    assert len([message for message in fake_sqlite_store.messages if message["role"] == "assistant"]) == 1
    assert fake_sqlite_store.messages[-1]["debug"]["trace_id"] == "trace-stream"
    assert "generation" in fake_sqlite_store.messages[-1]["debug"]


def test_chat_stream_passes_existing_history_to_prepare_request():
    app = FastAPI()
    app.include_router(chat_router)

    fake_chat_service = FakeChatService()
    fake_sqlite_store = FakeSQLiteStore()
    fake_sqlite_store.add_message("chat-1", "user", "Does the system use reranking?")
    fake_sqlite_store.add_message("chat-1", "assistant", "Optional reranking is available.")

    app.dependency_overrides[get_chat_service] = lambda: fake_chat_service
    app.dependency_overrides[get_sqlite_store] = lambda: fake_sqlite_store

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={"question": "Is it enabled by default?", "chat_id": "chat-1"},
        )

    assert response.status_code == 200
    assert fake_chat_service.prepare_calls[-1]["user_question"] == (
        "Is it enabled by default?"
    )


class FakeDisconnectRequest:
    def __init__(self, disconnect_after_checks: int = 999) -> None:
        self._checks = 0
        self.disconnect_after_checks = disconnect_after_checks

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > self.disconnect_after_checks


class TrackingOllamaService(FakeOllamaService):
    def __init__(self, tokens=None) -> None:
        super().__init__(tokens=tokens or ["One", " Two", " Three"])
        self.yield_count = 0

    async def stream(self, prompt: str):
        for token in self.tokens:
            self.yield_count += 1
            yield token


def _stream_prepared():
    return {
        "trace_id": "trace-stream",
        "prompt": "Prompt",
        "docs": [],
        "sources": [
            {
                "source": "sample.md",
                "chunk_id": "chunk-1",
                "preview": "sample preview",
            }
        ],
        "debug": {
            "trace_id": "trace-stream",
            "retrieval": {"retrieved_count": 1},
            "prompt": {"used_chunk_ids": ["chunk-1"]},
        },
    }


async def _collect_stream_events(**kwargs):
    events = []
    async for event in iter_chat_stream_events(**kwargs):
        events.append(event)
    return events


def test_stream_disconnect_before_tokens_skips_done_and_assistant():
    fake_sqlite_store = FakeSQLiteStore()
    tracking_ollama = TrackingOllamaService()
    fake_chat_service = FakeChatService(ollama_service=tracking_ollama)
    payload = ChatRequest(question="Disconnect early", chat_id="chat-1")
    prepared = _stream_prepared()

    events = asyncio.run(
        _collect_stream_events(
            request=FakeDisconnectRequest(disconnect_after_checks=0),
            payload=payload,
            prepared=prepared,
            chat_service=fake_chat_service,
            sqlite_store=fake_sqlite_store,
            request_started=perf_counter(),
        )
    )

    parsed = [json.loads(event.replace("data: ", "", 1)) for event in events if event]
    assert [event["type"] for event in parsed] == ["sources"]
    assert fake_sqlite_store.messages == []
    assert tracking_ollama.yield_count == 0


def test_stream_disconnect_after_token_stops_generation_and_persists_partial():
    fake_sqlite_store = FakeSQLiteStore()
    tracking_ollama = TrackingOllamaService()
    fake_chat_service = FakeChatService(ollama_service=tracking_ollama)
    payload = ChatRequest(question="Disconnect mid stream", chat_id="chat-1")
    prepared = _stream_prepared()

    events = asyncio.run(
        _collect_stream_events(
            request=FakeDisconnectRequest(disconnect_after_checks=3),
            payload=payload,
            prepared=prepared,
            chat_service=fake_chat_service,
            sqlite_store=fake_sqlite_store,
            request_started=perf_counter(),
        )
    )

    parsed = [json.loads(event.replace("data: ", "", 1)) for event in events if event]
    assert parsed[0]["type"] == "sources"
    assert [event["type"] for event in parsed[1:]] == ["token", "token"]
    assert "done" not in [event["type"] for event in parsed]
    assert "error" not in [event["type"] for event in parsed]
    assert tracking_ollama.yield_count == 2
    assert fake_sqlite_store.messages[-1]["role"] == "assistant"
    assert fake_sqlite_store.messages[-1]["content"] == "One Two"
    assert (
        fake_sqlite_store.messages[-1]["debug"]["generation"]["status"]
        == "client_disconnected"
    )


def test_stream_disconnect_after_user_persist_without_tokens_persists_cancelled_assistant():
    fake_sqlite_store = FakeSQLiteStore()
    tracking_ollama = TrackingOllamaService()
    fake_chat_service = FakeChatService(ollama_service=tracking_ollama)
    payload = ChatRequest(question="Disconnect before first token", chat_id="chat-1")
    prepared = _stream_prepared()

    events = asyncio.run(
        _collect_stream_events(
            request=FakeDisconnectRequest(disconnect_after_checks=1),
            payload=payload,
            prepared=prepared,
            chat_service=fake_chat_service,
            sqlite_store=fake_sqlite_store,
            request_started=perf_counter(),
        )
    )

    parsed = [json.loads(event.replace("data: ", "", 1)) for event in events if event]
    assert [event["type"] for event in parsed] == ["sources"]
    assert tracking_ollama.yield_count == 0
    assert fake_sqlite_store.messages[0]["role"] == "user"
    assert fake_sqlite_store.messages[1]["role"] == "assistant"
    assert fake_sqlite_store.messages[1]["content"] == ""
    assert (
        fake_sqlite_store.messages[1]["debug"]["generation"]["status"]
        == "client_disconnected"
    )
