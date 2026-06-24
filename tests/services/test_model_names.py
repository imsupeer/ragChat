import pytest

from services.model_catalog import load_model_catalog
from services.model_names import (
    KNOWN_ALIASES,
    build_install_command,
    build_run_command,
    is_catalog_known,
    model_matches_installed,
    normalize_model_name,
    resolve_canonical_name,
    resolve_installed_match,
)


@pytest.fixture
def catalog_names() -> set[str]:
    return {entry["ollama_name"] for entry in load_model_catalog()}


def test_default_chat_model_is_catalog_known(catalog_names: set[str]):
    assert is_catalog_known("llama3.1:8b", catalog_names)


def test_llama3_1_alias_resolves_to_catalog_name():
    assert resolve_canonical_name("llama3.1") == "llama3.1:8b"


def test_normalize_model_name_is_case_insensitive():
    assert normalize_model_name("Llama3.1:8B") == "llama3.1:8b"


def test_exact_match_wins_over_alias(catalog_names: set[str]):
    match = resolve_installed_match("llama3.1:8b", ["llama3.1:8b"], catalog_names)
    assert match["installed"] is True
    assert match["match_type"] == "exact"
    assert match["installed_match"] == "llama3.1:8b"


def test_alias_installed_match(catalog_names: set[str]):
    match = resolve_installed_match("llama3.1", ["llama3.1:8b"], catalog_names)
    assert match["installed"] is True
    assert match["match_type"] == "alias"
    assert match["installed_match"] == "llama3.1:8b"


def test_custom_installed_model_accepted(catalog_names: set[str]):
    match = resolve_installed_match("my-custom:latest", ["my-custom:latest"], catalog_names)
    assert match["installed"] is True
    assert match["match_type"] == "custom"
    assert match["catalog_known"] is False


def test_not_installed_returns_none_match(catalog_names: set[str]):
    match = resolve_installed_match("mistral:7b", ["llama3.1:8b"], catalog_names)
    assert match["installed"] is False
    assert match["match_type"] == "none"
    assert match["installed_match"] is None


def test_install_and_run_commands_are_safe_strings():
    assert build_install_command("qwen3:8b") == "ollama pull qwen3:8b"
    assert build_run_command("qwen3:8b") == "ollama run qwen3:8b"


def test_model_matches_installed_preserves_custom_tags():
    assert model_matches_installed("my-model:v2", "my-model:v2")
    assert not model_matches_installed("my-model:v2", "my-model:v3")


def test_known_aliases_are_conservative():
    assert "llama3.1" in KNOWN_ALIASES
    assert "llama3.2" in KNOWN_ALIASES
    assert "mistral" not in KNOWN_ALIASES
