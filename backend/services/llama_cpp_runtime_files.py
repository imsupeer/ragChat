from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ModelVerificationStatus = Literal[
    "missing",
    "present",
    "verified",
    "checksum_missing",
    "checksum_failed",
    "size_mismatch",
    "empty",
]

SETUP_COMMAND = "python scripts/download_demo_model.py"


class ModelManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ModelManifest:
    id: str
    display_name: str
    provider: str
    model_file: str
    recommended_repo: str = ""
    recommended_file: str = ""
    download_url: str = ""
    sha256: str = ""
    size_bytes: int | None = None
    context_size: int | None = None
    quantization: str = ""
    license_note: str = ""
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "provider": self.provider,
            "model_file": self.model_file,
            "recommended_repo": self.recommended_repo,
            "recommended_file": self.recommended_file,
            "download_url": self.download_url,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "context_size": self.context_size,
            "quantization": self.quantization,
            "license_note": self.license_note,
            "notes": list(self.notes),
        }

    @property
    def download_configured(self) -> bool:
        return bool(self.download_url or (self.recommended_repo and self.recommended_file))

    @property
    def checksum_configured(self) -> bool:
        return bool(self.sha256)


def _normalize_path(path: str | Path) -> Path:
    return Path(path)


def build_download_url(manifest: ModelManifest) -> str:
    if manifest.download_url:
        return manifest.download_url.strip()
    if manifest.recommended_repo and manifest.recommended_file:
        repo = manifest.recommended_repo.strip("/")
        file_name = manifest.recommended_file.lstrip("/")
        return f"https://huggingface.co/{repo}/resolve/main/{file_name}"
    raise ModelManifestError("No download URL configured in manifest.")


def compute_file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with _normalize_path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_file(
    model_path: str | Path,
    manifest: ModelManifest,
) -> tuple[ModelVerificationStatus, str]:
    path = _normalize_path(model_path)
    if not path.is_file():
        return "missing", "Demo model file is missing."

    size = path.stat().st_size
    if size <= 0:
        return "empty", "Demo model file is empty."

    if not path.name.lower().endswith(".gguf") and not manifest.model_file.lower().endswith(
        ".gguf"
    ):
        return "empty", "Expected a GGUF model file."

    if manifest.recommended_file and not manifest.recommended_file.lower().endswith(".gguf"):
        return "empty", "Manifest recommended file must be a GGUF file."

    if manifest.size_bytes is not None and size != manifest.size_bytes:
        return "size_mismatch", "Downloaded model size does not match manifest size_bytes."

    if manifest.sha256:
        actual = compute_file_sha256(path)
        if actual.lower() != manifest.sha256.lower():
            return "checksum_failed", "Downloaded model checksum does not match manifest sha256."
        return "verified", "Demo model file verified with SHA-256."

    return "checksum_missing", "Demo model file present; checksum not configured in manifest."


def load_model_manifest(path: str | Path) -> ModelManifest:
    manifest_path = _normalize_path(path)
    if not manifest_path.is_file():
        raise ModelManifestError(f"Model manifest not found: {manifest_path.name}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelManifestError("Model manifest is invalid or unreadable.") from exc

    if not isinstance(raw, dict):
        raise ModelManifestError("Model manifest must be a JSON object.")

    return parse_model_manifest(raw)


def parse_model_manifest(raw: dict[str, Any]) -> ModelManifest:
    required = ("id", "display_name", "provider", "model_file")
    missing = [field for field in required if not str(raw.get(field, "")).strip()]
    if missing:
        joined = ", ".join(missing)
        raise ModelManifestError(f"Model manifest is missing required fields: {joined}")

    recommended_file = str(raw.get("recommended_file") or "").strip()
    if recommended_file and not recommended_file.lower().endswith(".gguf"):
        raise ModelManifestError("Manifest recommended_file must be a GGUF file.")

    notes = raw.get("notes")
    note_items: tuple[str, ...]
    if isinstance(notes, list):
        note_items = tuple(str(item) for item in notes if str(item).strip())
    else:
        note_items = ()

    size_bytes = raw.get("size_bytes")
    parsed_size = size_bytes if isinstance(size_bytes, int) else None
    context_size = raw.get("context_size")
    parsed_context = context_size if isinstance(context_size, int) else None

    return ModelManifest(
        id=str(raw["id"]).strip(),
        display_name=str(raw["display_name"]).strip(),
        provider=str(raw["provider"]).strip(),
        model_file=str(raw["model_file"]).strip(),
        recommended_repo=str(raw.get("recommended_repo") or "").strip(),
        recommended_file=recommended_file,
        download_url=str(raw.get("download_url") or "").strip(),
        sha256=str(raw.get("sha256") or "").strip(),
        size_bytes=parsed_size,
        context_size=parsed_context,
        quantization=str(raw.get("quantization") or "").strip(),
        license_note=str(raw.get("license_note") or "").strip(),
        notes=note_items,
    )


def resolve_llama_server_binary(
    binary_dir: str | Path,
    *,
    explicit_binary: str | Path | None = None,
) -> Path | None:
    if explicit_binary:
        candidate = _normalize_path(explicit_binary)
        if candidate.is_file():
            return candidate
        return None

    directory = _normalize_path(binary_dir)
    if not directory.is_dir():
        return None

    candidates = (
        "llama-server.exe",
        "llama-server",
        "llama-server-linux",
        "llama-server-macos",
        "server.exe",
        "server",
    )
    for name in candidates:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def binary_missing_message() -> str:
    return (
        "llama-server binary not found. Place it under runtime/bin/ or set "
        "LLAMA_CPP_SERVER_BIN to the executable path."
    )


def _runtime_message(
    *,
    manifest: ModelManifest,
    model_file_found: bool,
    runtime_binary_found: bool,
    model_verification: ModelVerificationStatus,
) -> str:
    if model_file_found and runtime_binary_found and model_verification in {
        "verified",
        "checksum_missing",
        "present",
    }:
        return "Local llama.cpp runtime files are present."

    if not model_file_found and manifest.download_configured:
        return f"Run {SETUP_COMMAND} to fetch the demo GGUF model."

    model_name = manifest.model_file
    if not model_file_found and runtime_binary_found:
        return f"Place a GGUF model at models/demo/{model_name}."
    if model_file_found and not runtime_binary_found:
        return "Place llama-server in runtime/bin/."
    return (
        f"Place llama-server in runtime/bin/ and a GGUF model at "
        f"models/demo/{model_name}."
    )


def get_local_runtime_status(
    *,
    manifest_path: str | Path,
    models_dir: str | Path,
    binary_dir: str | Path,
    explicit_binary: str | Path | None = None,
) -> dict[str, Any]:
    try:
        manifest = load_model_manifest(manifest_path)
    except ModelManifestError as exc:
        return {
            "manifest_found": False,
            "model_file_found": False,
            "runtime_binary_found": False,
            "model_file_name": "",
            "model_verification": "missing",
            "download_configured": False,
            "checksum_configured": False,
            "recommended_repo": "",
            "recommended_file": "",
            "setup_command": SETUP_COMMAND,
            "message": str(exc),
        }

    models_directory = _normalize_path(models_dir)
    model_path = models_directory / manifest.model_file
    model_file_found = model_path.is_file()
    model_verification, verification_message = verify_model_file(model_path, manifest)
    if not model_file_found:
        model_verification = "missing"

    runtime_binary_found = (
        resolve_llama_server_binary(binary_dir, explicit_binary=explicit_binary) is not None
    )

    message = _runtime_message(
        manifest=manifest,
        model_file_found=model_file_found,
        runtime_binary_found=runtime_binary_found,
        model_verification=model_verification,
    )
    if model_verification == "checksum_failed":
        message = verification_message
    elif model_verification == "size_mismatch":
        message = verification_message
    elif model_verification == "empty":
        message = verification_message

    return {
        "manifest_found": True,
        "model_file_found": model_file_found,
        "runtime_binary_found": runtime_binary_found,
        "model_file_name": manifest.model_file,
        "model_verification": model_verification,
        "download_configured": manifest.download_configured,
        "checksum_configured": manifest.checksum_configured,
        "recommended_repo": manifest.recommended_repo,
        "recommended_file": manifest.recommended_file,
        "setup_command": SETUP_COMMAND,
        "message": message,
    }
