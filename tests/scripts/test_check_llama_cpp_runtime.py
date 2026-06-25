import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT = ROOT_DIR / "scripts" / "check_llama_cpp_runtime.py"


def run_check_script(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), *args]
    return subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_script_help_works():
    result = run_check_script("--help")
    assert result.returncode == 0
    assert "strict" in result.stdout.lower()


def test_check_script_returns_success_in_non_strict_missing_state(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLAMA_CPP_MANIFEST_PATH", str(tmp_path / "missing.json"))
    result = run_check_script()
    assert result.returncode == 0


def test_check_script_strict_missing_state_fails(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLAMA_CPP_MANIFEST_PATH", str(tmp_path / "missing.json"))
    result = run_check_script("--strict")
    assert result.returncode != 0


def test_check_script_json_output(monkeypatch, tmp_path: Path):
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

    monkeypatch.setenv("LLAMA_CPP_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("LLAMA_CPP_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("LLAMA_CPP_BINARY_DIR", str(binary_dir))

    result = run_check_script("--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["manifest_valid"] is True
    assert payload["local_runtime"]["manifest_found"] is True


def test_check_script_embeddings_section_local_hash(monkeypatch, tmp_path: Path):
    import check_llama_cpp_runtime as check_script

    report = check_script.build_report(
        check_script.Settings(),
        embeddings_provider="local_hash",
    )
    assert report["embeddings"]["provider"] == "local_hash"
    assert report["embeddings"]["quality"] == "demo"


def test_check_script_strict_ready_with_files(monkeypatch, tmp_path: Path):
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

    monkeypatch.setenv("LLAMA_CPP_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("LLAMA_CPP_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("LLAMA_CPP_BINARY_DIR", str(binary_dir))

    result = run_check_script("--strict")
    assert result.returncode == 0


def test_check_script_reports_download_configured(monkeypatch, tmp_path: Path):
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

    monkeypatch.setenv("LLAMA_CPP_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("LLAMA_CPP_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("LLAMA_CPP_BINARY_DIR", str(binary_dir))

    result = run_check_script("--json")
    payload = json.loads(result.stdout)
    assert payload["download_configured"] is True
    assert payload["model_verification"] == "missing"


def test_check_script_require_checksum_fails_when_missing(monkeypatch, tmp_path: Path):
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
                "download_url": "https://example.test/model.gguf",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("LLAMA_CPP_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("LLAMA_CPP_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("LLAMA_CPP_BINARY_DIR", str(binary_dir))

    result = run_check_script("--require-checksum")
    assert result.returncode != 0

