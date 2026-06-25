import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from services.llm_provider import LLMProviderUnsupportedOperationError
from services.providers.llama_cpp_provider import (
    LlamaCppProvider,
    LlamaCppProviderError,
    LlamaCppServerUnavailableError,
)


@pytest.fixture
def provider() -> LlamaCppProvider:
    return LlamaCppProvider(
        base_url="http://127.0.0.1:11435",
        chat_model="demo-model.gguf",
    )


def test_capabilities(provider: LlamaCppProvider):
    caps = provider.capabilities
    assert caps.chat is True
    assert caps.streaming is True
    assert caps.preload is True
    assert caps.unload is False
    assert caps.keep_alive is False
    assert caps.openai_compatible is True


def test_chat_sends_openai_compatible_payload(provider: LlamaCppProvider, monkeypatch):
    captured: dict[str, Any] = {}

    class MockResponse:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"role": "assistant", "content": "hello"}}]
            }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return MockResponse()

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.AsyncClient",
        MockAsyncClient,
    )

    result = asyncio.run(
        provider.chat(
            model="demo-model.gguf",
            messages=[{"role": "user", "content": "hi"}],
        )
    )

    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["json"]["model"] == "demo-model.gguf"
    assert captured["json"]["stream"] is False
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert result["message"]["content"] == "hello"


def test_chat_parses_openai_compatible_response(provider: LlamaCppProvider, monkeypatch):
    class MockResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "parsed answer"}}]}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None):
            del url, json
            return MockResponse()

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.AsyncClient",
        MockAsyncClient,
    )

    result = asyncio.run(
        provider.chat(
            model="demo-model.gguf",
            messages=[{"role": "user", "content": "question"}],
        )
    )
    assert result["message"]["content"] == "parsed answer"


def test_stream_chat_parses_sse_chunks(provider: LlamaCppProvider, monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "data: [DONE]",
    ]

    class MockStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            for line in lines:
                yield line

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url, json=None):
            del method, url, json
            return MockStreamResponse()

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.AsyncClient",
        MockAsyncClient,
    )

    tokens = asyncio.run(_collect_stream_chat(provider))
    assert tokens == ["Hel", "lo"]


async def _collect_stream_chat(provider: LlamaCppProvider) -> list[str]:
    tokens: list[str] = []
    async for event in provider.stream_chat(
        model="demo-model.gguf",
        messages=[{"role": "user", "content": "hi"}],
    ):
        tokens.append(event["message"]["content"])
    return tokens


def test_stream_chat_handles_done(provider: LlamaCppProvider, monkeypatch):
    class MockStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"x"}}]}'
            yield "data: [DONE]"
            yield 'data: {"choices":[{"delta":{"content":"y"}}]}'

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url, json=None):
            del method, url, json
            return MockStreamResponse()

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.AsyncClient",
        MockAsyncClient,
    )

    tokens = asyncio.run(_collect_stream_chat(provider))
    assert tokens == ["x"]


def test_stream_chat_handles_malformed_chunks_safely(
    provider: LlamaCppProvider, monkeypatch
):
    class MockStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            yield "data: not-json"
            yield 'data: {"choices":[{"delta":{"content":"ok"}}]}'
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url, json=None):
            del method, url, json
            return MockStreamResponse()

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.AsyncClient",
        MockAsyncClient,
    )

    tokens = asyncio.run(_collect_stream_chat(provider))
    assert tokens == ["ok"]


def _mock_sync_client_factory(responses: dict[str, Any]):
    class MockSyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            class Response:
                status_code = responses.get("status_code", 200)

                def json(self):
                    return responses.get("json", {})

            return Response()

    return MockSyncClient


def test_list_installed_models_uses_v1_models(provider: LlamaCppProvider, monkeypatch):
    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.Client",
        _mock_sync_client_factory(
            {
                "json": {
                    "data": [{"id": "demo-model.gguf", "owned_by": "local"}],
                }
            }
        ),
    )

    models = provider.list_installed_model_details()
    assert models == [
        {
            "name": "demo-model.gguf",
            "family": "local",
            "size": None,
            "modified_at": None,
            "status": "server",
        }
    ]


def test_list_installed_models_fallback_to_configured_model(
    provider: LlamaCppProvider, monkeypatch
):
    class MockSyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            class HealthResponse:
                status_code = 200

                def json(self):
                    return {}

            if url.endswith("/health"):
                return HealthResponse()

            class ModelsResponse:
                status_code = 404

                def json(self):
                    return {}

            return ModelsResponse()

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.Client",
        MockSyncClient,
    )

    models = provider.list_installed_model_details()
    assert models == [
        {
            "name": "demo-model.gguf",
            "family": None,
            "size": None,
            "modified_at": None,
            "status": "configured",
        }
    ]


def test_list_running_models_reflects_single_model_server(
    provider: LlamaCppProvider, monkeypatch
):
    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.Client",
        _mock_sync_client_factory(
            {
                "json": {
                    "data": [{"id": "demo-model.gguf"}],
                }
            }
        ),
    )

    result = provider.list_running_models_status()
    assert result["detection"] == "available"
    assert result["detection_method"] == "single_model_server"
    assert result["models"] == [{"name": "demo-model.gguf", "status": "loaded"}]


def test_list_running_models_unavailable_when_server_down(
    provider: LlamaCppProvider, monkeypatch
):
    def raise_error(*args, **kwargs):
        raise httpx.ConnectError("down", request=MagicMock())

    class MockSyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        get = raise_error

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.Client",
        MockSyncClient,
    )

    result = provider.list_running_models_status()
    assert result["detection"] == "unavailable"
    assert result["models"] == []


def test_preload_returns_reachable_noop_success(provider: LlamaCppProvider, monkeypatch):
    monkeypatch.setattr(provider, "is_reachable", lambda timeout=None: True)
    provider.preload_model_sync("demo-model.gguf")
    result = asyncio.run(provider.preload_model(model="demo-model.gguf"))
    assert result["status"] == "ok"
    assert "managed by the server process" in result["message"]


def test_unload_returns_unsupported(provider: LlamaCppProvider):
    with pytest.raises(LLMProviderUnsupportedOperationError):
        provider.unload_model_sync("demo-model.gguf")

    with pytest.raises(LLMProviderUnsupportedOperationError):
        asyncio.run(provider.unload_model(model="demo-model.gguf"))


def test_server_unavailable_errors_are_safe(provider: LlamaCppProvider, monkeypatch):
    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None):
            del url, json
            raise httpx.ConnectError("down", request=MagicMock())

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.AsyncClient",
        MockAsyncClient,
    )

    with pytest.raises(LlamaCppServerUnavailableError):
        asyncio.run(provider.generate("hello"))

    with pytest.raises(LlamaCppServerUnavailableError):
        provider.preload_model_sync("demo-model.gguf")


def test_chat_non_200_is_safe(provider: LlamaCppProvider, monkeypatch):
    class MockResponse:
        status_code = 500

        def json(self):
            return {}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None):
            del url, json
            return MockResponse()

    monkeypatch.setattr(
        "services.providers.llama_cpp_provider.httpx.AsyncClient",
        MockAsyncClient,
    )

    with pytest.raises(LlamaCppProviderError):
        asyncio.run(provider.generate("hello"))
