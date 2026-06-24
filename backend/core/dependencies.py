from functools import lru_cache
from core.config import get_settings
from embeddings.embedding_provider import EmbeddingProvider
from services.chroma_service import ChromaService
from services.document_registry import DocumentRegistry
from services.document_delete import DocumentDeleteService
from services.ollama_service import OllamaService
from services.chat_service import ChatService
from services.sqlite_store import SQLiteStore
from services.upload_queue import UploadQueueService
from services.query_rewriter import QueryRewriter
from services.reconciliation import PersistenceReconciliationService
from services.metrics import LocalMetrics, get_local_metrics
from services.readiness import ReadinessService
from services.model_recommender import ModelRecommenderService
from services.model_settings import ModelSettingsService
from services.model_runtime import ModelRuntimeService
from services.hardware_telemetry import HardwareTelemetryService


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
def get_model_settings_service() -> ModelSettingsService:
    settings = get_settings()

    def installed_models_provider() -> list[str]:
        tags_service = OllamaService(
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            keep_alive=settings.ollama_keep_alive,
            tags_timeout_seconds=settings.ollama_tags_timeout_seconds,
            preload_timeout_seconds=settings.ollama_preload_timeout_seconds,
        )
        return tags_service.list_installed_models()

    return ModelSettingsService(
        settings_path=settings.model_settings_path,
        default_chat_model=settings.ollama_chat_model,
        query_rewrite_model=settings.query_rewrite_model,
        use_chat_model_for_query_rewrite=settings.use_chat_model_for_query_rewrite,
        installed_models_provider=installed_models_provider,
    )


@lru_cache
def get_ollama_service() -> OllamaService:
    settings = get_settings()

    def resolve_chat_model() -> str:
        return get_model_settings_service().get_active_chat_model()

    return OllamaService(
        base_url=settings.ollama_base_url,
        model=settings.ollama_chat_model,
        model_resolver=resolve_chat_model,
        keep_alive=settings.ollama_keep_alive,
        tags_timeout_seconds=settings.ollama_tags_timeout_seconds,
        ps_timeout_seconds=settings.ollama_ps_timeout_seconds,
        preload_timeout_seconds=settings.ollama_preload_timeout_seconds,
    )


@lru_cache
def get_query_rewriter() -> QueryRewriter:
    settings = get_settings()
    ollama_service = get_ollama_service() if settings.enable_query_rewriting else None

    if settings.use_chat_model_for_query_rewrite:
        return QueryRewriter(
            enabled=settings.enable_query_rewriting,
            history_turns=settings.query_rewrite_history_turns,
            ollama_service=ollama_service,
            rewrite_model_resolver=lambda: get_model_settings_service().get_rewrite_model(),
        )

    rewrite_model = settings.query_rewrite_model or settings.ollama_chat_model
    return QueryRewriter(
        enabled=settings.enable_query_rewriting,
        history_turns=settings.query_rewrite_history_turns,
        ollama_service=ollama_service,
        rewrite_model=rewrite_model,
    )


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    return ChatService(
        chroma_service=get_chroma_service(),
        ollama_service=get_ollama_service(),
        top_k=settings.top_k,
        max_context_chunks=settings.max_context_chunks,
        enable_hybrid=settings.enable_hybrid,
        enable_reranking=settings.enable_reranking,
        rerank_top_m=settings.rerank_top_m,
        rerank_top_k=settings.rerank_top_k,
        query_rewriter=get_query_rewriter(),
        answer_mode=settings.answer_mode,
    )


@lru_cache
def get_sqlite_store() -> SQLiteStore:
    settings = get_settings()
    return SQLiteStore(settings.sqlite_path)


@lru_cache
def get_document_delete_service() -> DocumentDeleteService:
    return DocumentDeleteService(
        chroma_service=get_chroma_service(),
        registry=get_document_registry(),
        sqlite_store=get_sqlite_store(),
    )


@lru_cache
def get_upload_queue_service() -> UploadQueueService:
    settings = get_settings()
    return UploadQueueService(
        chroma_service=get_chroma_service(),
        registry=get_document_registry(),
        sqlite_store=get_sqlite_store(),
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        cleanup_failed_upload_files=settings.cleanup_failed_upload_files,
    )


@lru_cache
def get_reconciliation_service() -> PersistenceReconciliationService:
    settings = get_settings()
    return PersistenceReconciliationService(
        registry=get_document_registry(),
        chroma_service=get_chroma_service(),
        sqlite_store=get_sqlite_store(),
        documents_directory=settings.documents_directory,
    )


@lru_cache
def get_local_metrics_service() -> LocalMetrics:
    return get_local_metrics()


@lru_cache
def get_model_runtime_service() -> ModelRuntimeService:
    settings = get_settings()
    return ModelRuntimeService(
        ollama_service=get_ollama_service(),
        model_settings=get_model_settings_service(),
        keep_alive=settings.ollama_keep_alive,
    )


@lru_cache
def get_hardware_telemetry_service() -> HardwareTelemetryService:
    settings = get_settings()
    return HardwareTelemetryService(
        enabled=settings.hardware_telemetry_enabled,
        timeout_seconds=settings.hardware_telemetry_timeout_seconds,
        poll_seconds=settings.hardware_telemetry_poll_seconds,
        gpu_provider=settings.hardware_telemetry_gpu_provider,
    )


@lru_cache
def get_readiness_service() -> ReadinessService:
    settings = get_settings()
    return ReadinessService(
        settings=settings,
        sqlite_store=get_sqlite_store(),
        chroma_service=get_chroma_service(),
        upload_queue=get_upload_queue_service(),
        metrics=get_local_metrics_service(),
        model_runtime=get_model_runtime_service(),
    )


@lru_cache
def get_model_recommender_service() -> ModelRecommenderService:
    ollama_service = get_ollama_service()

    def installed_models_provider() -> list[str]:
        return ollama_service.list_installed_models()

    return ModelRecommenderService(installed_models_provider=installed_models_provider)


_CACHED_GETTERS = (
    get_embedding_provider,
    get_chroma_service,
    get_document_registry,
    get_ollama_service,
    get_query_rewriter,
    get_chat_service,
    get_sqlite_store,
    get_document_delete_service,
    get_upload_queue_service,
    get_reconciliation_service,
    get_local_metrics_service,
    get_readiness_service,
    get_model_recommender_service,
    get_model_settings_service,
    get_model_runtime_service,
    get_hardware_telemetry_service,
)


def clear_dependency_caches() -> None:
    """Reset in-memory dependency singletons. Test/dev helper; does not delete user data."""
    from services.metrics import reset_local_metrics

    for getter in _CACHED_GETTERS:
        getter.cache_clear()

    get_settings.cache_clear()
    reset_local_metrics()