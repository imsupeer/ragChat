import pytest

from core.config import Settings
from core.dependencies import clear_dependency_caches, get_llm_provider
from services.llm_provider import LLMProviderConfigError
from services.provider_resolver import resolve_llm_provider
from services.providers.ollama_provider import OllamaProvider


def test_default_llm_provider_is_ollama():
    provider = resolve_llm_provider(Settings())
    assert isinstance(provider, OllamaProvider)
    assert provider.provider_name == "ollama"


def test_invalid_llm_provider_fails_safely():
    with pytest.raises(ValueError, match="not implemented yet"):
        Settings(llm_provider="embedded_llamacpp")


def test_unknown_llm_provider_fails_safely():
    with pytest.raises(ValueError, match="must be one of"):
        Settings(llm_provider="unknown-provider")


def test_resolver_rejects_unimplemented_provider():
    settings = Settings.model_construct(llm_provider="embedded_llamacpp")
    with pytest.raises(LLMProviderConfigError, match="not implemented yet"):
        resolve_llm_provider(settings)


def test_ollama_provider_capabilities():
    provider = resolve_llm_provider(Settings())
    capabilities = provider.capabilities
    assert capabilities.chat is True
    assert capabilities.streaming is True
    assert capabilities.list_installed_models is True
    assert capabilities.list_running_models is True
    assert capabilities.preload is True
    assert capabilities.unload is True
    assert capabilities.keep_alive is True
    assert capabilities.openai_compatible is False


def test_dependency_cache_reset_clears_provider():
    first = get_llm_provider()
    second = get_llm_provider()
    assert first is second

    clear_dependency_caches()
    third = get_llm_provider()
    assert third is not first
