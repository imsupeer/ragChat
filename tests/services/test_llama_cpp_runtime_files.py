import json
from pathlib import Path

import pytest

from services.llama_cpp_runtime_files import (
    ModelManifestError,
    compute_file_sha256,
    get_local_runtime_status,
    load_model_manifest,
    parse_model_manifest,
    resolve_llama_server_binary,
    verify_model_file,
)


def test_valid_manifest_loads():
    manifest = parse_model_manifest(
        {
            "id": "demo-gguf",
            "display_name": "Demo GGUF Model",
            "provider": "llama_cpp",
            "model_file": "model.gguf",
            "notes": ["Place model manually."],
        }
    )
    assert manifest.id == "demo-gguf"
    assert manifest.model_file == "model.gguf"


def test_load_model_manifest_from_file(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "demo-gguf",
                "display_name": "Demo",
                "provider": "llama_cpp",
                "model_file": "model.gguf",
            }
        ),
        encoding="utf-8",
    )
    manifest = load_model_manifest(manifest_path)
    assert manifest.model_file == "model.gguf"


def test_missing_manifest_handled_safely(tmp_path: Path):
    with pytest.raises(ModelManifestError, match="not found"):
        load_model_manifest(tmp_path / "missing.json")


def test_invalid_manifest_handled_safely(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ModelManifestError, match="invalid"):
        load_model_manifest(manifest_path)


def test_invalid_manifest_missing_required_fields():
    with pytest.raises(ModelManifestError, match="missing required fields"):
        parse_model_manifest({"id": "demo"})


def test_model_file_missing_returns_false(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    models_dir = tmp_path / "demo"
    binary_dir = tmp_path / "bin"
    models_dir.mkdir()
    binary_dir.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "id": "demo-gguf",
                "display_name": "Demo",
                "provider": "llama_cpp",
                "model_file": "model.gguf",
            }
        ),
        encoding="utf-8",
    )

    status = get_local_runtime_status(
        manifest_path=manifest_path,
        models_dir=models_dir,
        binary_dir=binary_dir,
    )

    assert status["manifest_found"] is True
    assert status["model_file_found"] is False
    assert status["runtime_binary_found"] is False
    assert status["model_file_name"] == "model.gguf"
    assert status["model_verification"] == "missing"
    assert status["download_configured"] is False
    assert "models/demo/model.gguf" in status["message"] or "download_demo_model" in status["message"]


def test_model_file_present_returns_true(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    models_dir = tmp_path / "demo"
    binary_dir = tmp_path / "bin"
    models_dir.mkdir()
    binary_dir.mkdir()
    (models_dir / "model.gguf").write_bytes(b"fake")
    (binary_dir / "llama-server").write_text("", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "id": "demo-gguf",
                "display_name": "Demo",
                "provider": "llama_cpp",
                "model_file": "model.gguf",
            }
        ),
        encoding="utf-8",
    )

    status = get_local_runtime_status(
        manifest_path=manifest_path,
        models_dir=models_dir,
        binary_dir=binary_dir,
    )

    assert status["model_file_found"] is True
    assert status["runtime_binary_found"] is True
    assert status["model_verification"] == "checksum_missing"
    assert status["setup_command"] == "python scripts/download_demo_model.py"
    assert status["message"] == "Local llama.cpp runtime files are present."


def test_binary_missing_returns_false(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    models_dir = tmp_path / "demo"
    binary_dir = tmp_path / "bin"
    models_dir.mkdir()
    binary_dir.mkdir()
    (models_dir / "model.gguf").write_bytes(b"fake")
    manifest_path.write_text(
        json.dumps(
            {
                "id": "demo-gguf",
                "display_name": "Demo",
                "provider": "llama_cpp",
                "model_file": "model.gguf",
            }
        ),
        encoding="utf-8",
    )

    status = get_local_runtime_status(
        manifest_path=manifest_path,
        models_dir=models_dir,
        binary_dir=binary_dir,
    )

    assert status["model_file_found"] is True
    assert status["runtime_binary_found"] is False


def test_no_absolute_paths_exposed(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    models_dir = tmp_path / "demo"
    binary_dir = tmp_path / "bin"
    models_dir.mkdir()
    binary_dir.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "id": "demo-gguf",
                "display_name": "Demo",
                "provider": "llama_cpp",
                "model_file": "model.gguf",
            }
        ),
        encoding="utf-8",
    )

    status = get_local_runtime_status(
        manifest_path=manifest_path,
        models_dir=models_dir,
        binary_dir=binary_dir,
    )

    serialized = json.dumps(status)
    assert str(tmp_path) not in serialized
    assert "model_file_name" in status


def test_resolve_llama_server_binary_finds_server(tmp_path: Path):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    (binary_dir / "llama-server").write_text("", encoding="utf-8")
    resolved = resolve_llama_server_binary(binary_dir)
    assert resolved is not None
    assert resolved.name == "llama-server"


def test_local_runtime_includes_download_metadata(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    models_dir = tmp_path / "demo"
    binary_dir = tmp_path / "bin"
    models_dir.mkdir()
    binary_dir.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "id": "demo-gguf",
                "display_name": "Demo",
                "provider": "llama_cpp",
                "model_file": "model.gguf",
                "recommended_repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
                "recommended_file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
                "download_url": "https://example.test/model.gguf",
            }
        ),
        encoding="utf-8",
    )

    status = get_local_runtime_status(
        manifest_path=manifest_path,
        models_dir=models_dir,
        binary_dir=binary_dir,
    )

    assert status["download_configured"] is True
    assert status["recommended_repo"] == "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
    assert status["setup_command"] == "python scripts/download_demo_model.py"
    assert str(tmp_path) not in json.dumps(status)


def test_checksum_mismatch_status(tmp_path: Path):
    manifest_path = tmp_path / "model-manifest.json"
    models_dir = tmp_path / "demo"
    models_dir.mkdir()
    model_path = models_dir / "model.gguf"
    model_path.write_bytes(b"data")
    digest = compute_file_sha256(model_path)
    manifest_path.write_text(
        json.dumps(
            {
                "id": "demo-gguf",
                "display_name": "Demo",
                "provider": "llama_cpp",
                "model_file": "model.gguf",
                "sha256": "0" * len(digest),
            }
        ),
        encoding="utf-8",
    )

    status = get_local_runtime_status(
        manifest_path=manifest_path,
        models_dir=models_dir,
        binary_dir=tmp_path / "bin",
    )

    assert status["model_verification"] == "checksum_failed"

