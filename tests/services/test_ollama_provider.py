import asyncio
from unittest.mock import MagicMock

import pytest

from services.ollama_service import OllamaService
from services.providers.ollama_provider import OllamaProvider


@pytest.fixture
def ollama_service() -> OllamaService:
    return OllamaService(
        base_url="http://127.0.0.1:11434",
        model="llama3.1:8b",
        keep_alive="5m",
    )


@pytest.fixture
def provider(ollama_service: OllamaService) -> OllamaProvider:
    return OllamaProvider(ollama_service)


def test_chat_delegates_to_generate(provider: OllamaProvider, monkeypatch):
    async def fake_generate(prompt: str, model: str | None = None) -> str:
        del model
        assert prompt == "hello"
        return "answer"

    monkeypatch.setattr(provider._ollama, "generate", fake_generate)
    result = asyncio.run(
        provider.chat(
            model="llama3.1:8b",
            messages=[{"role": "user", "content": "hello"}],
        )
    )
    assert result["message"]["content"] == "answer"


def test_stream_chat_delegates_to_stream(provider: OllamaProvider, monkeypatch):
    async def fake_stream(prompt: str, model: str | None = None):
        del prompt, model
        for token in ["a", "b"]:
            yield token

    monkeypatch.setattr(provider._ollama, "stream", fake_stream)
    tokens = asyncio.run(_collect_stream_chat(provider))
    assert tokens == ["a", "b"]


async def _collect_stream_chat(provider: OllamaProvider) -> list[str]:
    tokens: list[str] = []
    async for event in provider.stream_chat(
        model="llama3.1:8b",
        messages=[{"role": "user", "content": "hello"}],
    ):
        tokens.append(event["message"]["content"])
    return tokens


def test_list_installed_models_delegates(provider: OllamaProvider, monkeypatch):
    monkeypatch.setattr(
        provider._ollama,
        "list_installed_model_details",
        lambda timeout=None: [{"name": "llama3.1:8b"}],
    )
    result = asyncio.run(provider.list_installed_models())
    assert result == [{"name": "llama3.1:8b"}]


def test_list_running_models_delegates(provider: OllamaProvider, monkeypatch):
    monkeypatch.setattr(
        provider._ollama,
        "list_running_models",
        lambda timeout=None: {
            "detection": "available",
            "models": [{"name": "llama3.1:8b"}],
        },
    )
    result = asyncio.run(provider.list_running_models())
    assert result == [{"name": "llama3.1:8b"}]


def test_preload_delegates(provider: OllamaProvider, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        provider._ollama,
        "preload_model",
        lambda model: calls.append(model),
    )
    result = asyncio.run(provider.preload_model(model="llama3.1:8b"))
    assert calls == ["llama3.1:8b"]
    assert result["status"] == "ok"


def test_unload_delegates(provider: OllamaProvider, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        provider._ollama,
        "unload_model",
        lambda model: calls.append(model),
    )
    result = asyncio.run(provider.unload_model(model="llama3.1:8b"))
    assert calls == ["llama3.1:8b"]
    assert result["status"] == "ok"


def test_generate_preserves_safe_errors(provider: OllamaProvider, monkeypatch):
    async def fail_generate(prompt: str, model: str | None = None) -> str:
        del prompt, model
        raise RuntimeError("Ollama unavailable")

    monkeypatch.setattr(provider._ollama, "generate", fail_generate)
    with pytest.raises(RuntimeError, match="Ollama unavailable"):
        asyncio.run(provider.generate("prompt"))


def test_provider_info_shape(provider: OllamaProvider):
    info = provider.provider_info()
    assert info["name"] == "ollama"
    assert info["display_name"] == "Ollama"
    assert info["capabilities"]["preload"] is True
