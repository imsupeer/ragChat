import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

for path in (ROOT_DIR, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from core.config import Settings
from core.dependencies import clear_dependency_caches
from embeddings.fake_embeddings import FakeEmbeddings
from services.metrics import reset_local_metrics


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: requires running local backend/services (set RUN_LIVE_TESTS=true)",
    )
    config.addinivalue_line("markers", "slow: slower tests")


def pytest_collection_modifyitems(config, items):
    run_live = os.getenv("RUN_LIVE_TESTS", "").lower() in {"1", "true", "yes"}
    if run_live:
        return

    skip_live = pytest.mark.skip(
        reason="Set RUN_LIVE_TESTS=true to run live tests",
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def _reset_backend_singletons():
    clear_dependency_caches()
    yield
    clear_dependency_caches()


@pytest.fixture
def clear_caches():
    clear_dependency_caches()
    return clear_dependency_caches


@pytest.fixture
def metrics_snapshot_reset():
    reset_local_metrics()
    yield
    reset_local_metrics()


@pytest.fixture
def fake_embeddings():
    return FakeEmbeddings()


@pytest.fixture
def sample_text_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "sample.txt"
    file_path.write_text(
        "Registry entries are tracked in registry.json.\n"
        "A background queue handles indexing.",
        encoding="utf-8",
    )
    return file_path


@pytest.fixture
def temp_workspace(tmp_path: Path) -> dict[str, Path]:
    docs_dir = tmp_path / "docs"
    vector_dir = tmp_path / "vector_db"
    docs_dir.mkdir()
    vector_dir.mkdir()
    return {
        "root": tmp_path,
        "docs_dir": docs_dir,
        "vector_dir": vector_dir,
        "sqlite_path": tmp_path / "app.db",
        "registry_path": tmp_path / "registry.json",
    }


@pytest.fixture
def test_settings(temp_workspace: dict[str, Path]) -> Settings:
    return Settings(
        sqlite_path=str(temp_workspace["sqlite_path"]),
        registry_path=str(temp_workspace["registry_path"]),
        documents_directory=str(temp_workspace["docs_dir"]),
        chroma_persist_directory=str(temp_workspace["vector_dir"]),
        max_upload_bytes=1024 * 1024,
        upload_read_chunk_bytes=4096,
    )
