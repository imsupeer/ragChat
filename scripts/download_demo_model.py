#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
DEFAULT_MANIFEST = ROOT_DIR / "models" / "demo" / "model-manifest.json"
DEFAULT_MODELS_DIR = ROOT_DIR / "models" / "demo"

from model_file_utils import (  # noqa: E402
    ModelManifestError,
    build_download_url,
    load_model_manifest,
    verify_model_file,
)


class DownloadError(RuntimeError):
    pass


def resolve_paths(manifest_path: Path) -> tuple[Path, Path]:
    manifest = load_model_manifest(manifest_path)
    models_dir = manifest_path.parent
    target = models_dir / manifest.model_file
    return models_dir, target


def download_url_to_temp(url: str, *, timeout_seconds: float = 120.0) -> Path:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "ragChat-demo-model-downloader/1.0"},
    )
    temp_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".gguf.part")
    temp_path = Path(temp_handle.name)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status and response.status >= 400:
                raise DownloadError(f"Download failed with HTTP status {response.status}.")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                temp_handle.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        temp_handle.close()
        temp_path.unlink(missing_ok=True)
        raise DownloadError(
            "Could not download demo model. Check your internet connection and try again."
        ) from exc
    finally:
        temp_handle.close()

    if temp_path.stat().st_size <= 0:
        temp_path.unlink(missing_ok=True)
        raise DownloadError("Downloaded file is empty.")

    return temp_path


def atomic_replace(temp_path: Path, final_path: Path) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_path, final_path)


def build_status(
    *,
    manifest_path: Path,
    model_path: Path,
    downloaded: bool = False,
    dry_run: bool = False,
    message: str = "",
) -> dict[str, object]:
    manifest = load_model_manifest(manifest_path)
    verification, verification_message = verify_model_file(model_path, manifest)
    if not model_path.is_file():
        verification = "missing"
    return {
        "manifest_path": "models/demo/model-manifest.json",
        "model_path": f"models/demo/{manifest.model_file}",
        "download_configured": manifest.download_configured,
        "checksum_configured": manifest.checksum_configured,
        "recommended_repo": manifest.recommended_repo,
        "recommended_file": manifest.recommended_file,
        "download_url": build_download_url(manifest) if manifest.download_configured else "",
        "model_verification": verification,
        "downloaded": downloaded,
        "dry_run": dry_run,
        "message": message or verification_message,
    }


def run_download(
    *,
    manifest_path: Path,
    force: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    timeout_seconds: float = 120.0,
) -> dict[str, object]:
    models_dir, model_path = resolve_paths(manifest_path)
    models_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_model_manifest(manifest_path)
    if not manifest.download_configured:
        raise DownloadError("Manifest does not configure a downloadable demo model.")

    if verify_only:
        status = build_status(manifest_path=manifest_path, model_path=model_path)
        if status["model_verification"] in {"missing", "empty", "checksum_failed", "size_mismatch"}:
            raise DownloadError(str(status["message"]))
        return status

    if model_path.is_file() and not force:
        status = build_status(
            manifest_path=manifest_path,
            model_path=model_path,
            message="Demo model already exists. Use --force to replace it.",
        )
        return status

    download_url = build_download_url(manifest)
    if dry_run:
        return build_status(
            manifest_path=manifest_path,
            model_path=model_path,
            dry_run=True,
            message=f"Dry run: would download {manifest.recommended_file} to models/demo/{manifest.model_file}.",
        )

    temp_path = download_url_to_temp(download_url, timeout_seconds=timeout_seconds)
    try:
        verification, verification_message = verify_model_file(temp_path, manifest)
        if verification in {"empty", "checksum_failed", "size_mismatch"}:
            raise DownloadError(verification_message)
        atomic_replace(temp_path, model_path)
        temp_path = model_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    final_verification, final_message = verify_model_file(model_path, manifest)
    return build_status(
        manifest_path=manifest_path,
        model_path=model_path,
        downloaded=True,
        message=final_message if final_verification != "missing" else "Demo model downloaded.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly download the demo GGUF model for local llama.cpp runtime.",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to model manifest JSON.",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing model file.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned download only.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify local model file only; do not download.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Download timeout in seconds.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    try:
        status = run_download(
            manifest_path=manifest_path,
            force=args.force,
            dry_run=args.dry_run,
            verify_only=args.verify_only,
            timeout_seconds=args.timeout,
        )
    except (DownloadError, ModelManifestError) as exc:
        if args.json:
            print(json.dumps({"status": "error", "message": str(exc)}))
        else:
            print(f"Error: {exc}")
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps({"status": "ok", **status}, indent=2))
    else:
        print(status.get("message", "Done."))
        if status.get("dry_run"):
            print(f"URL: {status.get('download_url')}")

    verification = status.get("model_verification")
    if args.verify_only and verification == "checksum_missing":
        print("Warning: checksum not configured; verified size/name only.")


if __name__ == "__main__":
    main()
