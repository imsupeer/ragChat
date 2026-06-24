from functools import lru_cache
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from prompts.rag_prompt import ANSWER_MODES

DEFAULT_MAX_UPLOAD_BYTES = 52_428_800
DEFAULT_UPLOAD_READ_CHUNK_BYTES = 1_048_576


class Settings(BaseSettings):
    app_name: str = "RAG Chat"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.1:8b"
    ollama_embed_model: str = "mxbai-embed-large"
    ollama_keep_alive: str = "5m"
    ollama_preload_timeout_seconds: float = 30.0
    ollama_tags_timeout_seconds: float = 2.0
    ollama_ps_timeout_seconds: float = 2.0

    hardware_telemetry_enabled: bool = True
    hardware_telemetry_timeout_seconds: float = 2.0
    hardware_telemetry_poll_seconds: float = 5.0
    hardware_telemetry_gpu_provider: str = "auto"

    chroma_persist_directory: str = "./vector_db"
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
