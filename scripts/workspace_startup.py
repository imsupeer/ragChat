from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.config import Settings
from services.sentence_transformers_runtime import inspect_sentence_transformers_setup
from services.runtime_configuration_summary import runtime_configuration_lines
from services.llama_cpp_runtime_files import (
    ModelManifestError,
    binary_missing_message,
    get_local_runtime_status,
    load_model_manifest,
    resolve_llama_server_binary,
    verify_model_file,
)

LLAMA_SERVER_PID = ROOT_DIR / "runtime" / "llama.cpp" / "llama-server.pid"
BACKEND_PID = ROOT_DIR / "runtime" / "backend.pid"
FRONTEND_PID = ROOT_DIR / "runtime" / "frontend.pid"
LLAMA_SERVER_LOG = ROOT_DIR / "runtime" / "logs" / "llama-server.log"
BACKEND_LOG = ROOT_DIR / "runtime" / "logs" / "backend.log"
FRONTEND_LOG = ROOT_DIR / "runtime" / "logs" / "frontend.log"

LLAMA_CPP_EMBEDDINGS_CHOICES = frozenset({"local_hash", "sentence_transformers"})


@dataclass
class StartupOptions:
    provider: str = "ollama"
    check_only: bool = False
    dry_run: bool = False
    download_model: bool = False
    start_server: bool = True
    backend_only: bool = False
    frontend_only: bool = False
    embeddings: str | None = None


@dataclass
class StartupPlan:
    provider: str
    actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    env_overrides: dict[str, str] = field(default_factory=dict)
    runtime_url: str = ""
    backend_url: str = ""
    frontend_url: str = ""
    model_path: str = ""
    ready: bool = False


def pid_paths() -> dict[str, Path]:
    return {
        "llama_server": LLAMA_SERVER_PID,
        "backend": BACKEND_PID,
        "frontend": FRONTEND_PID,
    }


def log_paths() -> dict[str, Path]:
    return {
        "llama_server": LLAMA_SERVER_LOG,
        "backend": BACKEND_LOG,
        "frontend": FRONTEND_LOG,
    }


def is_url_reachable(url: str, timeout_seconds: float = 2.0) -> bool:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def wait_for_url(url: str, *, timeout_seconds: float = 30.0, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_url_reachable(url, timeout_seconds=min(2.0, interval)):
            return True
        time.sleep(interval)
    return False


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in result.stdout
        except OSError:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def clear_stale_pid(path: Path) -> None:
    pid = read_pid(path)
    if pid is None:
        if path.exists():
            path.unlink(missing_ok=True)
        return
    if not is_process_running(pid):
        path.unlink(missing_ok=True)


def parse_port_from_base_url(base_url: str, default: int = 11435) -> int:
    parsed = urlparse(base_url)
    if parsed.port:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return default


def resolve_server_binary(settings: Settings) -> Path | None:
    explicit = (settings.llama_cpp_server_bin or os.getenv("LLAMA_CPP_SERVER_BIN", "")).strip()
    return resolve_llama_server_binary(
        ROOT_DIR / settings.llama_cpp_binary_dir,
        explicit_binary=explicit or None,
    )


def resolve_llama_cpp_embeddings(options: StartupOptions) -> str:
    if options.embeddings:
        return options.embeddings.strip().lower()
    return "local_hash"


def validate_llama_cpp_embeddings_choice(embeddings_provider: str) -> str | None:
    if embeddings_provider not in LLAMA_CPP_EMBEDDINGS_CHOICES:
        allowed = ", ".join(sorted(LLAMA_CPP_EMBEDDINGS_CHOICES))
        return f"Invalid embeddings provider '{embeddings_provider}'. Allowed: {allowed}"
    return None


def build_llama_cpp_env(
    settings: Settings,
    manifest_model_file: str,
    embeddings_provider: str,
) -> dict[str, str]:
    return {
        "LLM_PROVIDER": "llama_cpp",
        "EMBEDDINGS_PROVIDER": embeddings_provider,
        "LLAMA_CPP_BASE_URL": settings.llama_cpp_base_url,
        "LLAMA_CPP_CHAT_MODEL": manifest_model_file,
    }


def inspect_sentence_transformers_for_startup(settings: Settings) -> dict[str, object]:
    return inspect_sentence_transformers_setup(
        model_name=settings.sentence_transformers_model,
        dimension=settings.sentence_transformers_dimension,
        device=settings.sentence_transformers_device,
        cache_dir=settings.sentence_transformers_cache_dir,
        local_files_only=settings.sentence_transformers_local_files_only,
    )


def model_path(settings: Settings) -> Path:
    manifest = load_model_manifest(ROOT_DIR / settings.llama_cpp_manifest_path)
    return ROOT_DIR / settings.llama_cpp_models_dir / manifest.model_file


def ensure_frontend_dependencies() -> str | None:
    if not (ROOT_DIR / "frontend" / "node_modules").is_dir():
        return "Run npm install in frontend/ first."
    if shutil.which("npm") is None and shutil.which("npm.cmd") is None:
        return "npm was not found on PATH."
    return None


def build_startup_plan(options: StartupOptions, settings: Settings | None = None) -> StartupPlan:
    settings = settings or Settings()
    plan = StartupPlan(
        provider=options.provider,
        backend_url=f"http://127.0.0.1:{settings.api_port}",
        frontend_url=settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:3000",
        runtime_url=settings.llama_cpp_base_url,
    )

    if options.provider == "ollama":
        plan.actions.append("Use default provider: ollama")
        if options.check_only or options.dry_run:
            plan.actions.append("Validate Ollama-oriented manual startup guidance only")
            plan.ready = True
            return plan
        plan.actions.append("Print manual backend/frontend startup commands")
        plan.ready = True
        return plan

    manifest_path = ROOT_DIR / settings.llama_cpp_manifest_path
    try:
        manifest = load_model_manifest(manifest_path)
    except ModelManifestError as exc:
        plan.errors.append(str(exc))
        return plan

    plan.model_path = f"models/demo/{manifest.model_file}"
    target_model = ROOT_DIR / settings.llama_cpp_models_dir / manifest.model_file
    verification, verification_message = verify_model_file(target_model, manifest)
    if not target_model.is_file():
        verification = "missing"

    binary = resolve_server_binary(settings)
    if binary is None:
        plan.errors.append(binary_missing_message())

    if verification == "missing":
        if options.download_model:
            plan.actions.append("Run python scripts/download_demo_model.py")
        else:
            plan.errors.append(
                "Demo model is missing. Run python scripts/download_demo_model.py "
                "or rerun with --download-model."
            )
    elif verification in {"empty", "checksum_failed", "size_mismatch"}:
        plan.errors.append(verification_message)
    else:
        plan.actions.append(f"Use demo model at {plan.model_path}")

    embeddings_provider = resolve_llama_cpp_embeddings(options)
    embeddings_error = validate_llama_cpp_embeddings_choice(embeddings_provider)
    if embeddings_error:
        plan.errors.append(embeddings_error)
    else:
        plan.actions.append(f"Use embeddings provider: {embeddings_provider}")
        if embeddings_provider == "sentence_transformers":
            st_report = inspect_sentence_transformers_for_startup(settings)
            plan.actions.append("Run python scripts/check_sentence_transformers_embeddings.py --strict")
            if st_report.get("status") != "ok":
                plan.errors.append(str(st_report.get("message") or "Sentence-transformers embeddings are not ready."))
        elif embeddings_provider == "local_hash":
            plan.actions.append("Embeddings: local_hash demo quality (dependency-free)")

    plan.env_overrides = build_llama_cpp_env(
        settings,
        manifest.model_file,
        embeddings_provider,
    )
    plan.actions.append(
        "Launch backend with process env LLM_PROVIDER=llama_cpp and "
        f"EMBEDDINGS_PROVIDER={embeddings_provider} (overrides .env for child process)"
    )

    server_reachable = is_url_reachable(settings.llama_cpp_base_url, settings.llama_cpp_runtime_timeout_seconds)
    if server_reachable:
        plan.actions.append(f"Reuse reachable llama-server at {settings.llama_cpp_base_url}")
    elif options.start_server and binary is not None and target_model.is_file():
        port = parse_port_from_base_url(settings.llama_cpp_base_url)
        plan.actions.append(
            f"Start llama-server on port {port} with model {plan.model_path}"
        )
        plan.actions.append(f"Write PID to {LLAMA_SERVER_PID.relative_to(ROOT_DIR).as_posix()}")
    elif options.start_server:
        plan.actions.append("Start llama-server when binary and model are available")

    if not options.frontend_only:
        plan.actions.append(f"Start backend at {plan.backend_url}")
        plan.actions.append(f"Write backend PID to {BACKEND_PID.relative_to(ROOT_DIR).as_posix()}")
    if not options.backend_only:
        frontend_issue = ensure_frontend_dependencies()
        if frontend_issue:
            plan.errors.append(frontend_issue)
        else:
            plan.actions.append(f"Start frontend at {plan.frontend_url}")
            plan.actions.append(f"Write frontend PID to {FRONTEND_PID.relative_to(ROOT_DIR).as_posix()}")

    plan.ready = not plan.errors
    return plan


def print_runtime_configuration_summary(
    options: StartupOptions,
    settings: Settings,
    *,
    plan: StartupPlan | None = None,
) -> None:
    print("")
    print("Runtime configuration:")
    if options.provider == "ollama":
        for line in runtime_configuration_lines(
            chat_provider="ollama",
            embeddings_provider="ollama",
            settings=settings,
        ):
            print(line)
        return

    embeddings_provider = resolve_llama_cpp_embeddings(options)
    chat_model = plan.model_path.split("/")[-1] if plan and plan.model_path else "model.gguf"
    for line in runtime_configuration_lines(
        chat_provider="llama_cpp",
        embeddings_provider=embeddings_provider,
        settings=settings,
        chat_model=chat_model,
    ):
        print(line)


def print_ollama_guidance(settings: Settings) -> None:
    print("RAG workspace start")
    print(f"Provider: ollama (default)")
    print_runtime_configuration_summary(StartupOptions(provider="ollama"), settings)
    print("Start backend manually, for example:")
    print(f"  cd backend && {sys.executable} -m uvicorn main:app --host {settings.api_host} --port {settings.api_port}")
    print("Start frontend manually, for example:")
    print("  cd frontend && npm run dev")


def print_success_banner(plan: StartupPlan, options: StartupOptions, settings: Settings) -> None:
    print("")
    print("Local RAG Workspace started")
    print("")
    print(f"Provider: {plan.provider}")
    print(f"Runtime: {plan.runtime_url}")
    print(f"Backend: {plan.backend_url}")
    print(f"Frontend: {plan.frontend_url}")
    if plan.model_path:
        print(f"Model: {plan.model_path}")
    print_runtime_configuration_summary(options, settings, plan=plan)
    print("")
    print("Useful checks:")
    print("- python scripts/check_llama_cpp_runtime.py --strict")
    print(f"- GET {plan.backend_url}/models/runtime")
    print(f"- GET {plan.backend_url}/health/ready")


def print_dry_run(plan: StartupPlan, options: StartupOptions, settings: Settings) -> None:
    print("Dry run: planned actions")
    print(f"Provider: {plan.provider}")
    for action in plan.actions:
        print(f"- {action}")
    if plan.env_overrides:
        print("Environment overrides for backend:")
        for key, value in plan.env_overrides.items():
            print(f"  {key}={value}")
    if plan.errors:
        print("Blocking issues:")
        for error in plan.errors:
            print(f"- {error}")
    print_runtime_configuration_summary(options, settings, plan=plan)


def start_background_process(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    env: dict[str, str] | None = None,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab")
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=merged_env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    log_handle.close()
    return process.pid


def maybe_download_model(options: StartupOptions, settings: Settings) -> None:
    if not options.download_model or options.check_only or options.dry_run:
        return
    target = model_path(settings)
    if target.is_file():
        return
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "download_demo_model.py")],
        cwd=str(ROOT_DIR),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Demo model download failed.")


def ensure_llama_server(options: StartupOptions, settings: Settings, plan: StartupPlan) -> None:
    if options.check_only or options.dry_run or not options.start_server:
        return
    if is_url_reachable(settings.llama_cpp_base_url, settings.llama_cpp_runtime_timeout_seconds):
        print(f"llama-server already reachable at {settings.llama_cpp_base_url}")
        return

    binary = resolve_server_binary(settings)
    if binary is None:
        raise RuntimeError(binary_missing_message())

    target_model = model_path(settings)
    if not target_model.is_file():
        raise RuntimeError(f"Model file not found at {plan.model_path}")

    clear_stale_pid(LLAMA_SERVER_PID)
    port = parse_port_from_base_url(settings.llama_cpp_base_url)
    pid = start_background_process(
        [str(binary), "--model", str(target_model), "--port", str(port)],
        cwd=ROOT_DIR,
        log_path=LLAMA_SERVER_LOG,
    )
    write_pid(LLAMA_SERVER_PID, pid)
    if not wait_for_url(settings.llama_cpp_base_url, timeout_seconds=45.0):
        raise RuntimeError("llama-server did not become reachable in time.")
    print(f"llama-server started (PID {pid}). Logs: {LLAMA_SERVER_LOG.relative_to(ROOT_DIR).as_posix()}")


def ensure_backend(options: StartupOptions, settings: Settings, plan: StartupPlan) -> None:
    if options.check_only or options.dry_run or options.frontend_only:
        return
    health_url = f"{plan.backend_url}/health"
    if is_url_reachable(health_url):
        print(f"Backend already reachable at {plan.backend_url}")
        return

    clear_stale_pid(BACKEND_PID)
    env = plan.env_overrides if options.provider == "llama_cpp" else None
    pid = start_background_process(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            settings.api_host,
            "--port",
            str(settings.api_port),
        ],
        cwd=BACKEND_DIR,
        log_path=BACKEND_LOG,
        env=env,
    )
    write_pid(BACKEND_PID, pid)
    if not wait_for_url(health_url, timeout_seconds=60.0):
        raise RuntimeError("Backend did not become reachable in time.")
    print(f"Backend started (PID {pid}). Logs: {BACKEND_LOG.relative_to(ROOT_DIR).as_posix()}")


def ensure_frontend(options: StartupOptions, plan: StartupPlan) -> None:
    if options.check_only or options.dry_run or options.backend_only:
        return
    if is_url_reachable(plan.frontend_url):
        print(f"Frontend already reachable at {plan.frontend_url}")
        return

    issue = ensure_frontend_dependencies()
    if issue:
        raise RuntimeError(issue)

    npm = "npm.cmd" if os.name == "nt" else "npm"
    clear_stale_pid(FRONTEND_PID)
    pid = start_background_process(
        [npm, "run", "dev"],
        cwd=ROOT_DIR / "frontend",
        log_path=FRONTEND_LOG,
    )
    write_pid(FRONTEND_PID, pid)
    if not wait_for_url(plan.frontend_url, timeout_seconds=90.0):
        raise RuntimeError("Frontend did not become reachable in time.")
    print(f"Frontend started (PID {pid}). Logs: {FRONTEND_LOG.relative_to(ROOT_DIR).as_posix()}")


def execute_startup(options: StartupOptions) -> int:
    settings = Settings()
    plan = build_startup_plan(options, settings)

    if options.provider == "ollama":
        if options.dry_run:
            print_dry_run(plan, options, settings)
            return 0
        print_ollama_guidance(settings)
        return 0

    if options.dry_run:
        print_dry_run(plan, options, settings)
        return 0 if plan.ready else 1

    if options.check_only:
        if not plan.ready:
            for error in plan.errors:
                print(error)
            return 1
        print("Check-only mode: llama.cpp prerequisites satisfied.")
        for action in plan.actions:
            print(f"- {action}")
        print_runtime_configuration_summary(options, settings, plan=plan)
        return 0

    if not plan.ready:
        for error in plan.errors:
            print(error)
        return 1

    maybe_download_model(options, settings)
    plan = build_startup_plan(options, settings)
    if not plan.ready:
        for error in plan.errors:
            print(error)
        return 1

    ensure_llama_server(options, settings, plan)
    ensure_backend(options, settings, plan)
    ensure_frontend(options, plan)
    print_success_banner(plan, options, settings)
    return 0


def stop_process_by_pid_file(path: Path, label: str) -> bool:
    pid = read_pid(path)
    if pid is None:
        if path.exists():
            path.unlink(missing_ok=True)
        return False

    if not is_process_running(pid):
        print(f"{label} PID {pid} is not running (stale PID file removed).")
        path.unlink(missing_ok=True)
        return False

    print(f"Stopping {label} (PID {pid})")
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    else:
        try:
            os.kill(pid, 15)
            time.sleep(1)
            if is_process_running(pid):
                os.kill(pid, 9)
        except OSError:
            pass
    path.unlink(missing_ok=True)
    return True


def stop_all() -> int:
    stopped_any = False
    for label, path in (
        ("frontend", FRONTEND_PID),
        ("backend", BACKEND_PID),
        ("llama-server", LLAMA_SERVER_PID),
    ):
        if stop_process_by_pid_file(path, label):
            stopped_any = True
    if not stopped_any:
        print("No managed workspace processes were running.")
    else:
        print("Stopped managed workspace processes.")
    return 0
