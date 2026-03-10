from functools import lru_cache
from core.config import get_settings
from embeddings.embedding_provider import EmbeddingProvider
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.ollama_service import OllamaService
from services.chat_service import ChatService


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    return EmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
    )


@lru_cache
def get_chroma_service() -> ChromaService:
    settings = get_settings()
    embedding_provider = get_embedding_provider()
    return ChromaService(
        persist_directory=settings.chroma_persist_directory,
        embedding_function=embedding_provider.get_embeddings(),
    )


@lru_cache
def get_document_registry() -> DocumentRegistry:
    settings = get_settings()
    return DocumentRegistry(settings.registry_path)


@lru_cache
def get_ollama_service() -> OllamaService:
    settings = get_settings()
    return OllamaService(
        base_url=settings.ollama_base_url,
        model=settings.ollama_chat_model,
    )


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    return ChatService(
        chroma_service=get_chroma_service(),
        ollama_service=get_ollama_service(),
        top_k=settings.top_k,
        max_context_chunks=settings.max_context_chunks,
    )
