import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
BACKEND_DIR = ROOT_DIR / "backend"
for path in (str(SCRIPTS_DIR), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import download_demo_model as downloader
from model_file_utils import ModelManifestError, compute_file_sha256, verify_model_file
from services.llama_cpp_runtime_files import parse_model_manifest


def sample_manifest_dict(**overrides) -> dict:
    payload = {
        "id": "demo-gguf",
        "display_name": "Demo",
        "provider": "llama_cpp",
        "model_file": "model.gguf",
        "recommended_repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "recommended_file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "download_url": "https://example.test/model.gguf",
        "sha256": "",
        "size_bytes": None,
    }
    payload.update(overrides)
    return payload


def write_manifest(tmp_path: Path, **overrides) -> Path:
    manifest_path = tmp_path / "model-manifest.json"
    manifest_path.write_text(json.dumps(sample_manifest_dict(**overrides)), encoding="utf-8")
    return manifest_path


def test_dry_run_does_not_download(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)
    status = downloader.run_download(manifest_path=manifest_path, dry_run=True)
    assert status["dry_run"] is True
    assert not (tmp_path / "model.gguf").exists()


def test_existing_model_not_overwritten_without_force(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"existing")

    status = downloader.run_download(manifest_path=manifest_path)

    assert status["downloaded"] is False
    assert model_path.read_bytes() == b"existing"


def test_invalid_manifest_fails_safely(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    manifest_path.write_text("{bad", encoding="utf-8")
    with pytest.raises(ModelManifestError):
        downloader.run_download(manifest_path=manifest_path)


def test_non_gguf_recommended_file_fails_validation():
    with pytest.raises(ModelManifestError, match="GGUF"):
        parse_model_manifest(
            {
                "id": "demo",
                "display_name": "Demo",
                "provider": "llama_cpp",
                "model_file": "model.gguf",
                "recommended_file": "weights.bin",
            }
        )


def test_successful_mocked_download_writes_final_model(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)
    model_path = tmp_path / "model.gguf"

    def fake_download(url: str, *, timeout_seconds: float = 120.0) -> Path:
        del url, timeout_seconds
        temp = tmp_path / "temp.gguf"
        temp.write_bytes(b"GGUF-demo")
        return temp

    with patch.object(downloader, "download_url_to_temp", side_effect=fake_download):
        status = downloader.run_download(manifest_path=manifest_path)

    assert status["downloaded"] is True
    assert model_path.is_file()
    assert model_path.read_bytes() == b"GGUF-demo"


def test_sha256_success(tmp_path: Path):
    content = b"GGUF-demo"
    digest = hashlib.sha256(content).hexdigest()
    manifest_path = write_manifest(tmp_path, sha256=digest)
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(content)

    manifest = parse_model_manifest(sample_manifest_dict(sha256=digest))
    verification, _ = verify_model_file(model_path, manifest)
    assert verification == "verified"


def test_sha256_failure_does_not_replace_existing(tmp_path: Path):
    manifest_path = write_manifest(tmp_path, sha256="deadbeef")
    existing = tmp_path / "model.gguf"
    existing.write_bytes(b"keep-me")

    def fake_download(url: str, *, timeout_seconds: float = 120.0) -> Path:
        del url, timeout_seconds
        temp = tmp_path / "temp.gguf"
        temp.write_bytes(b"new-data")
        return temp

    with patch.object(downloader, "download_url_to_temp", side_effect=fake_download):
        with pytest.raises(downloader.DownloadError):
            downloader.run_download(manifest_path=manifest_path, force=True)

    assert existing.read_bytes() == b"keep-me"


def test_verify_only_passes_for_valid_local_file(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)
    (tmp_path / "model.gguf").write_bytes(b"GGUF-demo")
    status = downloader.run_download(manifest_path=manifest_path, verify_only=True)
    assert status["model_verification"] in {"checksum_missing", "verified", "present"}


def test_verify_only_fails_when_missing(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)
    with pytest.raises(downloader.DownloadError):
        downloader.run_download(manifest_path=manifest_path, verify_only=True)


def test_json_output(monkeypatch, tmp_path: Path):
    manifest_path = write_manifest(tmp_path)
    script = ROOT_DIR / "scripts" / "download_demo_model.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--manifest",
            str(manifest_path),
            "--dry-run",
            "--json",
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["dry_run"] is True


def test_compute_file_sha256_matches_hashlib(tmp_path: Path):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"abc")
    assert compute_file_sha256(path) == hashlib.sha256(b"abc").hexdigest()
