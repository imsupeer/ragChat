import os
import uuid
from pathlib import Path
from typing import Dict, Any, List

from fastapi import UploadFile
from langchain_core.documents import Document

from ingestion.loaders import load_document
from ingestion.chunker import chunk_documents


class UploadTooLargeError(Exception):
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"Upload exceeds maximum size of {max_bytes} bytes.")


def _build_stored_path(filename: str, target_dir: str) -> Path:
    os.makedirs(target_dir, exist_ok=True)
    basename = Path(filename.replace("\\", "/")).name.strip() or "upload"
    safe_name = f"{uuid.uuid4()}_{basename}"
    return Path(target_dir) / safe_name


def remove_stored_file(stored_path: str | None) -> bool:
    if not stored_path:
        return False

    path = Path(stored_path)
    if not path.exists():
        return False

    try:
        path.unlink()
        return True
    except OSError:
        return False


def save_uploaded_file(file_bytes: bytes, filename: str, target_dir: str) -> str:
    file_path = _build_stored_path(filename, target_dir)
    with open(file_path, "wb") as output:
        output.write(file_bytes)
    return str(file_path)


async def stream_upload_to_disk(
    upload_file: UploadFile,
    *,
    filename: str,
    target_dir: str,
    max_bytes: int,
    chunk_bytes: int,
) -> tuple[str, int]:
    file_path = _build_stored_path(filename, target_dir)
    total_bytes = 0

    try:
        with open(file_path, "wb") as output:
            while True:
                chunk = await upload_file.read(chunk_bytes)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise UploadTooLargeError(max_bytes)

                output.write(chunk)
    except Exception:
        remove_stored_file(str(file_path))
        raise

    if total_bytes == 0:
        remove_stored_file(str(file_path))
        raise ValueError("Uploaded file is empty.")

    return str(file_path), total_bytes


def sanitize_metadata(metadata: dict) -> dict:
    cleaned = {}

    for key, value in metadata.items():
        if value is None:
            continue

        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)

    return cleaned


def process_document(
    file_path: str,
    original_filename: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Document]:
    docs = load_document(file_path)
    chunks = chunk_documents(
        docs=docs,
        source_path=file_path,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    for index, chunk in enumerate(chunks):
        chunk.metadata["source"] = original_filename
        chunk.metadata["file_path"] = file_path
        chunk.metadata["chunk_index"] = index

        chunk.metadata = sanitize_metadata(chunk.metadata)

    return chunks


def build_registry_entry(
    document_id: str,
    original_filename: str,
    stored_path: str,
    total_chunks: int,
) -> Dict[str, Any]:
    return {
        "id": document_id,
        "filename": original_filename,
        "stored_path": stored_path,
        "total_chunks": total_chunks,
    }
