import json
import threading
from pathlib import Path

import pytest

from services.document_registry import DocumentRegistry


def test_document_registry_add_and_remove(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    registry = DocumentRegistry(str(registry_path))

    registry.add(
        {
            "id": "doc-1",
            "filename": "sample.txt",
            "stored_path": str(tmp_path / "sample.txt"),
            "total_chunks": 2,
        }
    )

    assert registry.get("doc-1")["filename"] == "sample.txt"
    removed = registry.remove("doc-1")
    assert removed["id"] == "doc-1"
    assert registry.get("doc-1") is None
    assert json.loads(registry_path.read_text(encoding="utf-8")) == []


def test_document_registry_update(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    registry = DocumentRegistry(str(registry_path))
    registry.add(
        {
            "id": "doc-1",
            "filename": "sample.txt",
            "stored_path": "sample.txt",
            "total_chunks": 1,
        }
    )

    updated = registry.update("doc-1", {"total_chunks": 4})

    assert updated["total_chunks"] == 4
    assert registry.get("doc-1")["total_chunks"] == 4


def test_document_registry_atomic_write_preserves_prior_file_on_replace_failure(
    tmp_path: Path, monkeypatch
):
    registry_path = tmp_path / "registry.json"
    registry = DocumentRegistry(str(registry_path))
    registry.add(
        {
            "id": "doc-1",
            "filename": "first.txt",
            "stored_path": "first.txt",
            "total_chunks": 1,
        }
    )

    def failing_replace(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("services.document_registry.os.replace", failing_replace)

    with pytest.raises(OSError, match="replace failed"):
        registry.add(
            {
                "id": "doc-2",
                "filename": "second.txt",
                "stored_path": "second.txt",
                "total_chunks": 1,
            }
        )

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["id"] == "doc-1"


def test_document_registry_concurrent_adds_produce_valid_json(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    registry = DocumentRegistry(str(registry_path))
    errors: list[Exception] = []

    def add_entry(index: int) -> None:
        try:
            registry.add(
                {
                    "id": f"doc-{index}",
                    "filename": f"file-{index}.txt",
                    "stored_path": f"file-{index}.txt",
                    "total_chunks": 1,
                }
            )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=add_entry, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert len(data) == 8
    assert {item["id"] for item in data} == {f"doc-{index}" for index in range(8)}
