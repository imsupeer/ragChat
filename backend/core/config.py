from functools import lru_cache
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from prompts.rag_prompt import ANSWER_MODES
from services.llm_provider import IMPLEMENTED_LLM_PROVIDERS, PLANNED_LLM_PROVIDERS
from services.embeddings_provider import IMPLEMENTED_EMBEDDINGS_PROVIDERS

DEFAULT_MAX_UPLOAD_BYTES = 52_428_800
DEFAULT_UPLOAD_READ_CHUNK_BYTES = 1_048_576


class Settings(BaseSettings):
    app_name: str = "RAG Chat"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    llm_provider: str = "ollama"

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.1:8b"
    ollama_embed_model: str = "mxbai-embed-large"
    ollama_embed_dimension: int = 1024

    embeddings_provider: str = "ollama"
    local_hash_embeddings_dimension: int = 384
    local_hash_embeddings_normalize: bool = True

    sentence_transformers_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    sentence_transformers_dimension: int = 384
    sentence_transformers_device: str = "cpu"
    sentence_transformers_cache_dir: str = ""
    sentence_transformers_local_files_only: bool = True

    ollama_keep_alive: str = "5m"
    ollama_preload_timeout_seconds: float = 30.0
    ollama_tags_timeout_seconds: float = 2.0
    ollama_ps_timeout_seconds: float = 2.0

    llama_cpp_base_url: str = "http://localhost:11435"
    llama_cpp_model_path: str = ""
    llama_cpp_chat_model: str = "demo-model.gguf"
    llama_cpp_timeout_seconds: float = 60.0
    llama_cpp_stream_timeout_seconds: float = 120.0
    llama_cpp_runtime_timeout_seconds: float = 2.0
    llama_cpp_manifest_path: str = "./models/demo/model-manifest.json"
    llama_cpp_models_dir: str = "./models/demo"
    llama_cpp_binary_dir: str = "./runtime/bin"
    llama_cpp_server_bin: str = ""
    llama_cpp_pid_file: str = "./runtime/llama.cpp/llama-server.pid"
    llama_cpp_log_file: str = "./runtime/logs/llama-server.log"

    hardware_telemetry_enabled: bool = True
    hardware_telemetry_timeout_seconds: float = 2.0
    hardware_telemetry_poll_seconds: float = 5.0
    hardware_telemetry_gpu_provider: str = "auto"

    chroma_persist_directory: str = "./vector_db"
    chroma_collection_strategy: str = "per_embedding_provider"
    chroma_default_collection: str = "rag_chat"
    chroma_collection_prefix: str = "rag"

    documents_directory: str = "./storage/docs"
    registry_path: str = "./storage/registry.json"
    sqlite_path: str = "./storage/app.db"
    model_settings_path: str = "./storage/model_settings.json"

    chunk_size: int = 800
    chunk_overlap: int = 200
    top_k: int = 5
    max_context_chunks: int = 5
    enable_hybrid: bool = False
    enable_reranking: bool = False
    rerank_top_m: int = 10
    rerank_top_k: int = 5
    enable_query_rewriting: bool = False
    query_rewrite_history_turns: int = 4
    query_rewrite_model: str | None = None
    use_chat_model_for_query_rewrite: bool = False
    answer_mode: str = "strict_rag"

    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    upload_read_chunk_bytes: int = DEFAULT_UPLOAD_READ_CHUNK_BYTES
    cleanup_failed_upload_files: bool = True

    reconcile_on_startup: bool = True
    reconcile_repair_on_startup: bool = False
    reconcile_allow_stale_registry_repair: bool = False

    otel_enabled: bool = False
    otel_service_name: str = "local-rag-workspace"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        normalized = (value or "ollama").strip().lower()
        allowed = IMPLEMENTED_LLM_PROVIDERS | PLANNED_LLM_PROVIDERS
        if normalized not in allowed:
            implemented = ", ".join(sorted(IMPLEMENTED_LLM_PROVIDERS))
            raise ValueError(
                f"LLM_PROVIDER must be one of the known provider keys. "
                f"Implemented: {implemented}"
            )
        if normalized not in IMPLEMENTED_LLM_PROVIDERS:
            raise ValueError(
                f"LLM provider '{normalized}' is not implemented yet. "
                f"Implemented providers: {', '.join(sorted(IMPLEMENTED_LLM_PROVIDERS))}"
            )
        return normalized

    @field_validator("embeddings_provider")
    @classmethod
    def validate_embeddings_provider(cls, value: str) -> str:
        normalized = (value or "ollama").strip().lower()
        if normalized not in IMPLEMENTED_EMBEDDINGS_PROVIDERS:
            allowed = ", ".join(sorted(IMPLEMENTED_EMBEDDINGS_PROVIDERS))
            raise ValueError(
                f"EMBEDDINGS_PROVIDER must be one of the implemented providers: {allowed}"
            )
        return normalized

    @field_validator("chroma_collection_strategy")
    @classmethod
    def validate_chroma_collection_strategy(cls, value: str) -> str:
        from retrieval.collection_identity import CHROMA_COLLECTION_STRATEGIES

        normalized = (value or "per_embedding_provider").strip().lower()
        if normalized not in CHROMA_COLLECTION_STRATEGIES:
            allowed = ", ".join(sorted(CHROMA_COLLECTION_STRATEGIES))
            raise ValueError(
                f"CHROMA_COLLECTION_STRATEGY must be one of: {allowed}"
            )
        return normalized

    @field_validator("local_hash_embeddings_dimension", "ollama_embed_dimension", "sentence_transformers_dimension")
    @classmethod
    def validate_positive_embedding_dimension(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Embedding dimension settings must be positive.")
        return value

    @field_validator(
        "llama_cpp_timeout_seconds",
        "llama_cpp_stream_timeout_seconds",
        "llama_cpp_runtime_timeout_seconds",
    )
    @classmethod
    def validate_positive_llama_cpp_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("llama.cpp timeout settings must be positive.")
        return value

    @field_validator("answer_mode")
    @classmethod
    def validate_answer_mode(cls, value: str) -> str:
        normalized = (value or "strict_rag").strip().lower()
        if normalized not in ANSWER_MODES:
            allowed = ", ".join(sorted(ANSWER_MODES))
            raise ValueError(f"ANSWER_MODE must be one of: {allowed}")
        return normalized

    @field_validator("max_upload_bytes", "upload_read_chunk_bytes")
    @classmethod
    def validate_positive_byte_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Byte size settings must be positive.")
        return value

    @field_validator("ollama_preload_timeout_seconds", "ollama_tags_timeout_seconds", "ollama_ps_timeout_seconds", "hardware_telemetry_timeout_seconds")
    @classmethod
    def validate_positive_ollama_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Ollama timeout settings must be positive.")
        return value

    @field_validator("ollama_keep_alive")
    @classmethod
    def validate_keep_alive(cls, value: str) -> str:
        normalized = (value or "5m").strip()
        if not normalized:
            raise ValueError("OLLAMA_KEEP_ALIVE must not be empty.")
        return normalized

    @field_validator("hardware_telemetry_poll_seconds")
    @classmethod
    def validate_positive_poll_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Hardware telemetry poll interval must be positive.")
        return value

    @field_validator("hardware_telemetry_gpu_provider")
    @classmethod
    def validate_gpu_provider(cls, value: str) -> str:
        normalized = (value or "auto").strip().lower()
        allowed = {"auto", "nvidia", "amd", "disabled"}
        if normalized not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            raise ValueError(f"HARDWARE_TELEMETRY_GPU_PROVIDER must be one of: {allowed_list}")
        return normalized

    @property
    def cors_origins_list(self) -> List[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
