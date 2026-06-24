import json
from pathlib import Path

import pytest

from services.model_catalog import load_model_catalog
from services.model_settings import ModelSettingsConflictError, ModelSettingsService


@pytest.fixture
def catalog_names() -> set[str]:
    return {entry["ollama_name"] for entry in load_model_catalog()}


@pytest.fixture
def settings_service(tmp_path: Path, catalog_names: set[str]) -> ModelSettingsService:
    installed = ["llama3.1:8b", "qwen3:8b"]

    return ModelSettingsService(
      settings_path=str(tmp_path / "model_settings.json"),
      default_chat_model="llama3.1:8b",
      query_rewrite_model=None,
      use_chat_model_for_query_rewrite=False,
      installed_models_provider=lambda: installed,
      catalog_loader=load_model_catalog,
  )


def test_model_settings_loads_default_when_file_missing(tmp_path: Path):
    path = tmp_path / "model_settings.json"
    service = ModelSettingsService(
        settings_path=str(path),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: [],
        catalog_loader=load_model_catalog,
    )

    state = service.get_state()
    assert state["chat_model"] == "llama3.1:8b"
    assert state["source"] == "default"
    assert path.exists()


def test_model_settings_persists_selected_chat_model_atomically(
    settings_service: ModelSettingsService,
    tmp_path: Path,
):
    updated = settings_service.update_chat_model("qwen3:8b", require_installed=True)

    assert updated["chat_model"] == "qwen3:8b"
    assert updated["source"] == "user"
    assert settings_service.get_active_chat_model() == "qwen3:8b"

    raw = json.loads((tmp_path / "model_settings.json").read_text(encoding="utf-8"))
    assert raw["chat_model"] == "qwen3:8b"
    assert not (tmp_path / "model_settings.json.tmp").exists()


def test_model_settings_reset_returns_default(settings_service: ModelSettingsService):
    settings_service.update_chat_model("qwen3:8b", require_installed=True)

    reset = settings_service.reset()

    assert reset["chat_model"] == "llama3.1:8b"
    assert reset["source"] == "default"
    assert settings_service.get_active_chat_model() == "llama3.1:8b"


def test_model_settings_rejects_invalid_model_name(settings_service: ModelSettingsService):
    with pytest.raises(ValueError, match="catalog"):
        settings_service.update_chat_model("not-a-real-model:99b", require_installed=False)


def test_model_settings_require_installed_rejects_missing_model(settings_service: ModelSettingsService):
    with pytest.raises(ModelSettingsConflictError, match="not installed"):
        settings_service.update_chat_model("mistral:7b", require_installed=True)


def test_model_settings_require_installed_accepts_installed_model(
    settings_service: ModelSettingsService,
):
    state = settings_service.update_chat_model("qwen3:8b", require_installed=True)
    assert state["installed_status"] == "installed"


def test_model_settings_ollama_unavailable_blocks_require_installed(tmp_path: Path):
    service = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: (_ for _ in ()).throw(RuntimeError("down")),
        catalog_loader=load_model_catalog,
    )

    with pytest.raises(ModelSettingsConflictError, match="Ollama is unavailable"):
        service.update_chat_model("qwen3:8b", require_installed=True)


def test_model_settings_allows_unverified_model_when_require_installed_false(
    tmp_path: Path,
):
    service = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: [],
        catalog_loader=load_model_catalog,
    )

    state = service.update_chat_model("mistral:7b", require_installed=False)
    assert state["chat_model"] == "mistral:7b"
    assert "warning" in state


def test_model_settings_repeated_writes_remain_consistent(settings_service: ModelSettingsService):
    settings_service.update_chat_model("qwen3:8b", require_installed=True)
    settings_service.update_chat_model("llama3.1:8b", require_installed=True)

    state = settings_service.get_state()
    assert state["chat_model"] == "llama3.1:8b"
    assert state["source"] == "user"


def test_get_rewrite_model_uses_config_default_when_chat_model_selected(
    settings_service: ModelSettingsService,
):
    settings_service.update_chat_model("qwen3:8b", require_installed=True)
    assert settings_service.get_rewrite_model() == "llama3.1:8b"


def test_get_rewrite_model_can_follow_active_chat_model(tmp_path: Path):
    service = ModelSettingsService(
        settings_path=str(tmp_path / "model_settings.json"),
        default_chat_model="llama3.1:8b",
        use_chat_model_for_query_rewrite=True,
        installed_models_provider=lambda: ["qwen3:8b", "llama3.1:8b"],
        catalog_loader=load_model_catalog,
    )
    service.update_chat_model("qwen3:8b", require_installed=True)
    assert service.get_rewrite_model() == "qwen3:8b"


def test_existing_user_selected_model_is_not_overwritten(tmp_path: Path):
    path = tmp_path / "model_settings.json"
    path.write_text(
        json.dumps(
            {
                "chat_model": "llama3.1",
                "default_chat_model": "llama3.1:8b",
                "source": "user",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    service = ModelSettingsService(
        settings_path=str(path),
        default_chat_model="llama3.1:8b",
        installed_models_provider=lambda: ["llama3.1:8b"],
        catalog_loader=load_model_catalog,
    )

    assert service.get_active_chat_model() == "llama3.1"
    state = service.get_state()
    assert state["source"] == "user"
    assert state["chat_model"] == "llama3.1"
    assert state["match_type"] == "alias"


def test_require_installed_accepts_alias_installed_match(settings_service: ModelSettingsService):
    state = settings_service.update_chat_model("llama3.1", require_installed=True)
    assert state["chat_model"] == "llama3.1"
    assert state["installed"] is True
    assert state["match_type"] == "alias"
    assert state["installed_match"] == "llama3.1:8b"
