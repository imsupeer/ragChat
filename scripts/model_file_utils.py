from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.llama_cpp_runtime_files import (  # noqa: E402
    ModelManifest,
    ModelManifestError,
    build_download_url,
    compute_file_sha256,
    load_model_manifest,
    parse_model_manifest,
    verify_model_file,
)

__all__ = [
    "ModelManifest",
    "ModelManifestError",
    "build_download_url",
    "compute_file_sha256",
    "load_model_manifest",
    "parse_model_manifest",
    "verify_model_file",
]
