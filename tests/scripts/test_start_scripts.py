import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
BACKEND_DIR = ROOT_DIR / "backend"
for path in (str(SCRIPTS_DIR), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import workspace_startup as startup
from core.config import Settings
from services.llama_cpp_runtime_files import binary_missing_message, resolve_llama_server_binary


def sample_manifest() -> dict:
    return {
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


@pytest.fixture
def workspace_root(tmp_path, monkeypatch):
    (tmp_path / "models" / "demo").mkdir(parents=True)
    (tmp_path / "runtime" / "bin").mkdir(parents=True)
    (tmp_path / "runtime" / "llama.cpp").mkdir(parents=True)
    (tmp_path / "runtime" / "logs").mkdir(parents=True)
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    manifest_path = tmp_path / "models" / "demo" / "model-manifest.json"
    manifest_path.write_text(json.dumps(sample_manifest()), encoding="utf-8")

    monkeypatch.setattr(startup, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(startup, "BACKEND_DIR", tmp_path / "backend")
    monkeypatch.setattr(startup, "SCRIPTS_DIR", tmp_path / "scripts")
    monkeypatch.setattr(startup, "LLAMA_SERVER_PID", tmp_path / "runtime" / "llama.cpp" / "llama-server.pid")
    monkeypatch.setattr(startup, "BACKEND_PID", tmp_path / "runtime" / "backend.pid")
    monkeypatch.setattr(startup, "FRONTEND_PID", tmp_path / "runtime" / "frontend.pid")
    return tmp_path


def test_default_ollama_plan_does_not_request_download():
    plan = startup.build_startup_plan(startup.StartupOptions(provider="ollama"))
    assert plan.provider == "ollama"
    assert not any("download" in action.lower() for action in plan.actions)


def test_llama_cpp_download_flag_plans_download_when_model_missing(workspace_root):
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    plan = startup.build_startup_plan(
        startup.StartupOptions(provider="llama_cpp", download_model=True),
        settings,
    )
    assert any("download_demo_model.py" in action for action in plan.actions)


def test_check_only_does_not_download(workspace_root, monkeypatch):
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    called = {"download": False}

    def fake_download(options, settings_obj):
        called["download"] = True

    monkeypatch.setattr(startup, "maybe_download_model", fake_download)
    code = startup.execute_startup(
        startup.StartupOptions(provider="llama_cpp", check_only=True),
    )
    assert code == 1
    assert called["download"] is False


def test_dry_run_prints_plan_without_download(workspace_root, monkeypatch, capsys):
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    (workspace_root / "models" / "demo" / "model.gguf").write_bytes(b"gguf")

    called = {"download": False}

    def fake_download(options, settings_obj):
        called["download"] = True

    monkeypatch.setattr(startup, "maybe_download_model", fake_download)
    code = startup.execute_startup(
        startup.StartupOptions(provider="llama_cpp", dry_run=True, download_model=True),
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "Dry run" in output
    assert called["download"] is False


def test_pid_and_log_paths_are_stable():
    paths = startup.pid_paths()
    logs = startup.log_paths()
    assert paths["backend"].name == "backend.pid"
    assert paths["frontend"].name == "frontend.pid"
    assert logs["backend"].name == "backend.log"
    assert logs["frontend"].name == "frontend.log"


def test_missing_binary_produces_guidance(workspace_root):
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    (workspace_root / "models" / "demo" / "model.gguf").write_bytes(b"gguf")
    plan = startup.build_startup_plan(
        startup.StartupOptions(provider="llama_cpp"),
        settings,
    )
    assert any(binary_missing_message() in error for error in plan.errors)


def test_missing_model_produces_download_instruction(workspace_root):
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    plan = startup.build_startup_plan(
        startup.StartupOptions(provider="llama_cpp"),
        settings,
    )
    assert any("--download-model" in error or "download_demo_model.py" in error for error in plan.errors)


def test_reachable_server_plan_skips_start(workspace_root):
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
        llama_cpp_base_url="http://localhost:11435",
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    (workspace_root / "models" / "demo" / "model.gguf").write_bytes(b"gguf")
    with patch.object(startup, "is_url_reachable", return_value=True):
        plan = startup.build_startup_plan(
            startup.StartupOptions(provider="llama_cpp"),
            settings,
        )
    assert any("Reuse reachable llama-server" in action for action in plan.actions)
    assert not any(action.startswith("Start llama-server on port") for action in plan.actions)


def test_stop_removes_stale_pid(workspace_root):
    pid_file = workspace_root / "runtime" / "backend.pid"
    pid_file.write_text("999999", encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(startup, "BACKEND_PID", pid_file)
    monkeypatch.setattr(startup, "FRONTEND_PID", workspace_root / "runtime" / "frontend.pid")
    monkeypatch.setattr(startup, "LLAMA_SERVER_PID", workspace_root / "runtime" / "llama.cpp" / "llama-server.pid")
    with patch.object(startup, "is_process_running", return_value=False):
        stopped = startup.stop_process_by_pid_file(pid_file, "backend")
    assert stopped is False
    assert not pid_file.exists()
    monkeypatch.undo()


def test_llama_cpp_env_override_uses_manifest_model_file(workspace_root):
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_base_url="http://localhost:11435",
    )
    env = startup.build_llama_cpp_env(settings, "model.gguf", "local_hash")
    assert env["LLM_PROVIDER"] == "llama_cpp"
    assert env["EMBEDDINGS_PROVIDER"] == "local_hash"
    assert env["LLAMA_CPP_BASE_URL"] == "http://localhost:11435"
    assert env["LLAMA_CPP_CHAT_MODEL"] == "model.gguf"


def test_llama_cpp_env_can_select_sentence_transformers(workspace_root):
    settings = Settings(llm_provider="llama_cpp")
    env = startup.build_llama_cpp_env(settings, "model.gguf", "sentence_transformers")
    assert env["EMBEDDINGS_PROVIDER"] == "sentence_transformers"


def test_llama_cpp_defaults_to_local_hash_embeddings(workspace_root, monkeypatch):
    monkeypatch.setattr(
        startup,
        "inspect_sentence_transformers_for_startup",
        lambda settings: {"status": "ok"},
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    (workspace_root / "models" / "demo" / "model.gguf").write_bytes(b"gguf")
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    plan = startup.build_startup_plan(
        startup.StartupOptions(provider="llama_cpp"),
        settings,
    )
    assert plan.env_overrides.get("EMBEDDINGS_PROVIDER") == "local_hash"


def test_llama_cpp_sentence_transformers_flag_sets_env(workspace_root, monkeypatch):
    monkeypatch.setattr(
        startup,
        "inspect_sentence_transformers_for_startup",
        lambda settings: {"status": "ok"},
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    (workspace_root / "models" / "demo" / "model.gguf").write_bytes(b"gguf")
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    plan = startup.build_startup_plan(
        startup.StartupOptions(
            provider="llama_cpp",
            embeddings="sentence_transformers",
        ),
        settings,
    )
    assert plan.env_overrides.get("EMBEDDINGS_PROVIDER") == "sentence_transformers"


def test_dry_run_prints_runtime_configuration(workspace_root, monkeypatch, capsys):
    monkeypatch.setattr(
        startup,
        "inspect_sentence_transformers_for_startup",
        lambda settings: {"status": "ok"},
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    (workspace_root / "models" / "demo" / "model.gguf").write_bytes(b"gguf")
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    options = startup.StartupOptions(provider="llama_cpp", dry_run=True)
    startup.execute_startup(options)
    output = capsys.readouterr().out
    assert "Runtime configuration:" in output
    assert "Chat provider: llama_cpp" in output
    assert "Embeddings provider: local_hash" in output
    assert "Chroma collection strategy: per_embedding_provider" in output
    assert "Active Chroma collection:" in output
    assert "Reindex helper: python scripts/reindex_documents.py --dry-run" in output


def test_invalid_embeddings_choice_adds_error(workspace_root):
    settings = Settings(
        llm_provider="llama_cpp",
        llama_cpp_manifest_path="./models/demo/model-manifest.json",
        llama_cpp_models_dir="./models/demo",
        llama_cpp_binary_dir="./runtime/bin",
    )
    (workspace_root / "runtime" / "bin" / "llama-server").write_bytes(b"bin")
    (workspace_root / "models" / "demo" / "model.gguf").write_bytes(b"gguf")
    plan = startup.build_startup_plan(
        startup.StartupOptions(provider="llama_cpp", embeddings="openai"),
        settings,
    )
    assert any("Invalid embeddings provider" in error for error in plan.errors)


def test_default_mode_does_not_set_embeddings_override():
    plan = startup.build_startup_plan(startup.StartupOptions(provider="ollama"))
    assert "EMBEDDINGS_PROVIDER" not in plan.env_overrides


def test_resolve_binary_supports_explicit_path(workspace_root):
    custom = workspace_root / "custom" / "llama-server"
    custom.parent.mkdir(parents=True)
    custom.write_bytes(b"bin")
    found = resolve_llama_server_binary(
        workspace_root / "runtime" / "bin",
        explicit_binary=custom,
    )
    assert found == custom


def test_resolve_binary_supports_platform_names(workspace_root):
    linux_bin = workspace_root / "runtime" / "bin" / "llama-server-linux"
    linux_bin.write_bytes(b"bin")
    found = resolve_llama_server_binary(workspace_root / "runtime" / "bin")
    assert found == linux_bin
