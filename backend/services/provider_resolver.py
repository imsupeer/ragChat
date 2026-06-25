from __future__ import annotations

from core.config import Settings
from services.llm_provider import (
    IMPLEMENTED_LLM_PROVIDERS,
    LLMProvider,
    LLMProviderConfigError,
    PLANNED_LLM_PROVIDERS,
)
from services.ollama_service import OllamaService
from services.providers.llama_cpp_provider import LlamaCppProvider
from services.providers.ollama_provider import OllamaProvider


def resolve_llm_provider(
    settings: Settings,
    *,
    model_resolver=None,
) -> LLMProvider:
    provider_key = (settings.llm_provider or "ollama").strip().lower()

    if provider_key not in IMPLEMENTED_LLM_PROVIDERS:
        if provider_key in PLANNED_LLM_PROVIDERS:
            raise LLMProviderConfigError(
                f"LLM provider '{provider_key}' is not implemented yet. "
                f"Implemented providers: {', '.join(sorted(IMPLEMENTED_LLM_PROVIDERS))}"
            )
        allowed = ", ".join(sorted(IMPLEMENTED_LLM_PROVIDERS))
        raise LLMProviderConfigError(
            f"Invalid LLM_PROVIDER value: '{provider_key}'. "
            f"Implemented providers: {allowed}"
        )

    if provider_key == "ollama":
        ollama_service = OllamaService(
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            model_resolver=model_resolver,
            keep_alive=settings.ollama_keep_alive,
            tags_timeout_seconds=settings.ollama_tags_timeout_seconds,
            ps_timeout_seconds=settings.ollama_ps_timeout_seconds,
            preload_timeout_seconds=settings.ollama_preload_timeout_seconds,
        )
        return OllamaProvider(ollama_service)

    if provider_key == "llama_cpp":
        return LlamaCppProvider(
            base_url=settings.llama_cpp_base_url,
            chat_model=settings.llama_cpp_chat_model,
            model_path=settings.llama_cpp_model_path,
            model_resolver=model_resolver,
            timeout_seconds=settings.llama_cpp_timeout_seconds,
            stream_timeout_seconds=settings.llama_cpp_stream_timeout_seconds,
            runtime_timeout_seconds=settings.llama_cpp_runtime_timeout_seconds,
        )

    raise LLMProviderConfigError(f"Unsupported LLM provider: {provider_key}")
