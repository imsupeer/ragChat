from __future__ import annotations

from typing import Any, Callable

DEFAULT_SENTENCE_TRANSFORMERS_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SETUP_COMMAND = "pip install -r backend/requirements-embeddings.txt"
CHECK_COMMAND = "python scripts/check_sentence_transformers_embeddings.py --strict"


def import_sentence_transformer_class() -> type[Any] | None:
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer
    except ImportError:
        return None


def inspect_sentence_transformers_setup(
    *,
    model_name: str,
    dimension: int,
    device: str,
    cache_dir: str,
    local_files_only: bool,
    model_loader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    sentence_transformer_cls = import_sentence_transformer_class()
    if sentence_transformer_cls is None:
        return {
            "status": "missing_dependency",
            "message": (
                "sentence-transformers is not installed. "
                f"Run: {SETUP_COMMAND}"
            ),
            "dependency_installed": False,
            "model_available": False,
            "model_name": model_name,
            "dimension": dimension,
            "device": device,
            "local_files_only": local_files_only,
            "setup_command": SETUP_COMMAND,
            "check_command": CHECK_COMMAND,
        }

    loader = model_loader or sentence_transformer_cls
    load_kwargs: dict[str, Any] = {
        "device": device,
        "local_files_only": local_files_only,
    }
    if cache_dir:
        load_kwargs["cache_folder"] = cache_dir

    try:
        model = loader(model_name, **load_kwargs)
    except OSError as exc:
        return {
            "status": "model_missing",
            "message": (
                "Sentence-transformers model is not available locally. "
                f"Run: {CHECK_COMMAND}"
            ),
            "dependency_installed": True,
            "model_available": False,
            "model_name": model_name,
            "dimension": dimension,
            "device": device,
            "local_files_only": local_files_only,
            "setup_command": SETUP_COMMAND,
            "check_command": CHECK_COMMAND,
            "detail": str(exc),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": "Sentence-transformers model check failed.",
            "dependency_installed": True,
            "model_available": False,
            "model_name": model_name,
            "dimension": dimension,
            "device": device,
            "local_files_only": local_files_only,
            "setup_command": SETUP_COMMAND,
            "check_command": CHECK_COMMAND,
            "detail": str(exc),
        }

    try:
        vector = model.encode("healthcheck", convert_to_numpy=True)
        actual_dimension = int(vector.shape[-1])
    except Exception as exc:
        return {
            "status": "error",
            "message": "Sentence-transformers model encode check failed.",
            "dependency_installed": True,
            "model_available": True,
            "model_name": model_name,
            "dimension": dimension,
            "device": device,
            "local_files_only": local_files_only,
            "setup_command": SETUP_COMMAND,
            "check_command": CHECK_COMMAND,
            "detail": str(exc),
        }

    if actual_dimension != dimension:
        return {
            "status": "error",
            "message": (
                f"Configured dimension {dimension} does not match model output "
                f"{actual_dimension}."
            ),
            "dependency_installed": True,
            "model_available": True,
            "model_name": model_name,
            "dimension": dimension,
            "actual_dimension": actual_dimension,
            "device": device,
            "local_files_only": local_files_only,
            "setup_command": SETUP_COMMAND,
            "check_command": CHECK_COMMAND,
        }

    return {
        "status": "ok",
        "message": "Sentence-transformers embeddings are ready.",
        "dependency_installed": True,
        "model_available": True,
        "model_name": model_name,
        "dimension": dimension,
        "device": device,
        "local_files_only": local_files_only,
        "setup_command": SETUP_COMMAND,
        "check_command": CHECK_COMMAND,
    }
