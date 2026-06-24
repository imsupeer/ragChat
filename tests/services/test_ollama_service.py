import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
import urllib.error

from services.ollama_service import OllamaService


@pytest.fixture
def ollama_service() -> OllamaService:
    return OllamaService(
        base_url="http://127.0.0.1:11434",
        model="llama3.1:8b",
        ps_timeout_seconds=1.0,
        tags_timeout_seconds=1.0,
    )


def _mock_response(payload: dict, *, status: int = 200):
    body = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.status = status
    response.read.return_value = body
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_list_running_models_parses_ps_success(ollama_service: OllamaService):
    tags_response = _mock_response({"models": [{"name": "llama3.1:8b"}]})
    ps_response = _mock_response(
        {
            "models": [
                {
                    "name": "llama3.1:8b",
                    "model": "llama3.1:8b",
                    "size": 100,
                    "size_vram": 90,
                    "expires_at": "2026-06-24T12:00:00Z",
                    "digest": "abc",
                }
            ]
        }
    )

    with patch("urllib.request.urlopen", side_effect=[tags_response, ps_response]):
        result = ollama_service.list_running_models()

    assert result["detection"] == "available"
    assert len(result["models"]) == 1
    assert result["models"][0]["name"] == "llama3.1:8b"
    assert result["models"][0]["size"] == 100
    assert "digest" not in result["models"][0]


def test_list_running_models_handles_ps_404_as_unsupported(ollama_service: OllamaService):
    tags_response = _mock_response({"models": [{"name": "llama3.1:8b"}]})

    def urlopen_side_effect(request, *args, **kwargs):
        if str(request.full_url).endswith("/api/tags"):
            return tags_response
        raise urllib.error.HTTPError(
            url="http://127.0.0.1:11434/api/ps",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(b""),
        )

    with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
        result = ollama_service.list_running_models()

    assert result["detection"] == "unsupported"
    assert result["models"] == []


def test_list_running_models_unavailable_when_ollama_unreachable(ollama_service: OllamaService):
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        result = ollama_service.list_running_models()

    assert result["detection"] == "unavailable"
    assert result["models"] == []
