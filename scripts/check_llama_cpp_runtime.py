#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.config import Settings
from services.runtime_configuration_summary import build_embeddings_runtime_section
from services.llama_cpp_runtime_files import (
    ModelManifestError,
    get_local_runtime_status,
    load_model_manifest,
    resolve_llama_server_binary,
)


def check_server_reachable(base_url: str, timeout_seconds: float) -> bool:
    base = base_url.rstrip("/")
    for path in ("/health", "/v1/models", ""):
        url = f"{base}{path}"
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False


def build_report(
    settings: Settings,
    *,
    include_backend: bool = False,
    include_frontend: bool = False,
    embeddings_provider: str | None = None,
) -> dict[str, object]:
    manifest_path = ROOT_DIR / settings.llama_cpp_manifest_path
    explicit_binary = (settings.llama_cpp_server_bin or "").strip() or None
    local_status = get_local_runtime_status(
        manifest_path=manifest_path,
        models_dir=ROOT_DIR / settings.llama_cpp_models_dir,
        binary_dir=ROOT_DIR / settings.llama_cpp_binary_dir,
        explicit_binary=explicit_binary,
    )

    binary = resolve_llama_server_binary(
        ROOT_DIR / settings.llama_cpp_binary_dir,
        explicit_binary=explicit_binary,
    )
    server_reachable = check_server_reachable(
        settings.llama_cpp_base_url,
        settings.llama_cpp_runtime_timeout_seconds,
    )

    backend_url = f"http://127.0.0.1:{settings.api_port}"
    frontend_url = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:3000"
    backend_reachable = (
        check_server_reachable(f"{backend_url}/health", settings.llama_cpp_runtime_timeout_seconds)
        if include_backend
        else None
    )
    frontend_reachable = (
        check_server_reachable(frontend_url, settings.llama_cpp_runtime_timeout_seconds)
        if include_frontend
        else None
    )

    manifest_valid = False
    manifest_error = None
    manifest = None
    try:
        manifest = load_model_manifest(manifest_path)
        manifest_valid = True
    except ModelManifestError as exc:
        manifest_error = str(exc)

    report: dict[str, object] = {
        "provider": settings.llm_provider,
        "base_url": settings.llama_cpp_base_url,
        "server_reachable": server_reachable,
        "backend_reachable": backend_reachable,
        "frontend_reachable": frontend_reachable,
        "manifest_valid": manifest_valid,
        "manifest_error": manifest_error,
        "download_configured": manifest.download_configured if manifest else False,
        "checksum_configured": manifest.checksum_configured if manifest else False,
        "recommended_repo": manifest.recommended_repo if manifest else "",
        "recommended_file": manifest.recommended_file if manifest else "",
        "model_verification": local_status.get("model_verification", "missing"),
        "local_runtime": local_status,
        "binary_detected": binary is not None,
    }
    if embeddings_provider:
        report["embeddings"] = build_embeddings_runtime_section(embeddings_provider, settings)
    return report


def print_report(report: dict[str, object]) -> None:
    print("llama.cpp runtime check")
    print("=======================")
    print(f"Configured provider: {report['provider']}")
    print(f"Base URL: {report['base_url']}")
    print(f"Server reachable: {'yes' if report['server_reachable'] else 'no'}")
    print(f"Download configured: {'yes' if report['download_configured'] else 'no'}")
    print(f"Checksum configured: {'yes' if report['checksum_configured'] else 'no'}")
    if report.get("recommended_repo"):
        print(f"Recommended repo: {report['recommended_repo']}")
    if report.get("recommended_file"):
        print(f"Recommended file: {report['recommended_file']}")
    print(f"Model verification: {report.get('model_verification')}")

    local = report["local_runtime"]
    assert isinstance(local, dict)
    print(f"Manifest found: {'yes' if local.get('manifest_found') else 'no'}")
    print(f"Manifest valid: {'yes' if report['manifest_valid'] else 'no'}")
    if report["manifest_error"]:
        print(f"Manifest error: {report['manifest_error']}")
    print(f"Model file found: {'yes' if local.get('model_file_found') else 'no'}")
    print(f"Runtime binary found: {'yes' if local.get('runtime_binary_found') else 'no'}")
    print(f"Model file name: {local.get('model_file_name') or '-'}")
    if report.get("backend_reachable") is not None:
        print(f"Backend reachable: {'yes' if report['backend_reachable'] else 'no'}")
    if report.get("frontend_reachable") is not None:
        print(f"Frontend reachable: {'yes' if report['frontend_reachable'] else 'no'}")
    embeddings = report.get("embeddings")
    if isinstance(embeddings, dict):
        print(f"Embeddings provider: {embeddings.get('provider')}")
        print(f"Embeddings status: {embeddings.get('status')}")
        if embeddings.get("quality"):
            print(f"Embeddings quality: {embeddings.get('quality')}")
        if embeddings.get("message"):
            print(f"Embeddings message: {embeddings.get('message')}")
    print(f"Message: {local.get('message')}")


def is_strict_ready(report: dict[str, object], *, require_checksum: bool) -> bool:
    local = report["local_runtime"]
    assert isinstance(local, dict)
    verification = str(report.get("model_verification", "missing"))
    if verification in {"missing", "empty", "checksum_failed", "size_mismatch"}:
        return False
    if require_checksum and not report.get("checksum_configured"):
        return False
    if require_checksum and verification != "verified":
        return False
    return bool(
        report["manifest_valid"]
        and local.get("manifest_found")
        and local.get("model_file_found")
        and local.get("runtime_binary_found")
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Check local llama.cpp runtime prerequisites without downloading "
            "binaries or models."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when manifest, model file, or runtime binary is missing.",
    )
    parser.add_argument(
        "--require-checksum",
        action="store_true",
        help="Exit non-zero in strict mode when manifest checksum is not configured or verified.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON report.",
    )
    parser.add_argument(
        "--include-backend",
        action="store_true",
        help="Also check whether the backend /health endpoint is reachable.",
    )
    parser.add_argument(
        "--include-frontend",
        action="store_true",
        help="Also check whether the frontend dev server is reachable.",
    )
    parser.add_argument(
        "--embeddings",
        choices=["local_hash", "sentence_transformers", "ollama"],
        default=None,
        help="Include embeddings provider readiness in the report.",
    )
    args = parser.parse_args()

    settings = Settings()
    report = build_report(
        settings,
        include_backend=args.include_backend,
        include_frontend=args.include_frontend,
        embeddings_provider=args.embeddings,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    if args.strict and not is_strict_ready(report, require_checksum=args.require_checksum):
        raise SystemExit(1)
    if args.require_checksum and not args.strict:
        if not report.get("checksum_configured"):
            print("Warning: checksum is not configured in manifest.")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
