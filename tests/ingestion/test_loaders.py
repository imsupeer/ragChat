from pathlib import Path

import asyncio
import pytest

from ingestion.loaders import load_document, load_text_with_encoding_fallback
from ingestion.processor import (
    UploadTooLargeError,
    remove_stored_file,
    save_uploaded_file,
    stream_upload_to_disk,
)


class ChunkedUploadFile:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self._index = 0

    async def read(self, size: int = -1) -> bytes:
        if self._index >= len(self._chunks):
            return b""
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


def test_stream_upload_writes_file_from_multiple_chunks(tmp_path: Path):
    upload = ChunkedUploadFile([b"hel", b"lo", b" world"])

    stored_path, file_size = asyncio.run(
        stream_upload_to_disk(
            upload,
            filename="sample.txt",
            target_dir=str(tmp_path),
            max_bytes=1024,
            chunk_bytes=3,
        )
    )

    assert file_size == 11
    assert Path(stored_path).read_bytes() == b"hello world"


def test_stream_upload_rejects_oversized_upload_and_cleans_partial_file(
    tmp_path: Path,
):
    upload = ChunkedUploadFile([b"a" * 8, b"b" * 8])

    with pytest.raises(UploadTooLargeError):
        asyncio.run(
            stream_upload_to_disk(
                upload,
                filename="large.txt",
                target_dir=str(tmp_path),
                max_bytes=10,
                chunk_bytes=8,
            )
        )

    assert list(tmp_path.glob("*")) == []


def test_stream_upload_rejects_empty_file(tmp_path: Path):
    upload = ChunkedUploadFile([])

    with pytest.raises(ValueError, match="empty"):
        asyncio.run(
            stream_upload_to_disk(
                upload,
                filename="empty.txt",
                target_dir=str(tmp_path),
                max_bytes=1024,
                chunk_bytes=64,
            )
        )

    assert list(tmp_path.glob("*")) == []


def test_remove_stored_file_deletes_existing_file(tmp_path: Path):
    stored_path = save_uploaded_file(b"content", "sample.txt", str(tmp_path))

    assert remove_stored_file(stored_path) is True
    assert not Path(stored_path).exists()


def test_load_utf8_text_file(tmp_path: Path):
    file_path = tmp_path / "utf8.txt"
    file_path.write_text("Registry entries live in registry.json", encoding="utf-8")

    documents = load_text_with_encoding_fallback(str(file_path))

    assert documents[0].page_content.startswith("Registry entries")
    assert documents[0].metadata["encoding"] == "utf-8"


def test_load_utf8_bom_text_file(tmp_path: Path):
    file_path = tmp_path / "bom.txt"
    file_path.write_bytes(
        "\ufeffRegistry entries live in registry.json".encode("utf-8-sig")
    )

    documents = load_text_with_encoding_fallback(str(file_path))

    assert "Registry entries" in documents[0].page_content
    assert documents[0].metadata["encoding"] in {"utf-8", "utf-8-sig"}


def test_load_latin1_text_file(tmp_path: Path):
    file_path = tmp_path / "latin1.txt"
    file_path.write_bytes("Caf\xe9 r\xe9sum\xe9".encode("latin-1"))

    documents = load_text_with_encoding_fallback(str(file_path))

    assert documents[0].page_content == "Café résumé"
    assert documents[0].metadata["encoding"] == "latin-1"


def test_load_document_records_encoding_for_markdown(tmp_path: Path):
    file_path = tmp_path / "notes.md"
    file_path.write_bytes("Caf\xe9 notes".encode("latin-1"))

    documents = load_document(str(file_path))

    assert documents[0].metadata["encoding"] == "latin-1"
