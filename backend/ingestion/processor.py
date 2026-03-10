import os
import uuid
from pathlib import Path
from typing import Dict, Any, List
from langchain_core.documents import Document
from ingestion.loaders import load_document
from ingestion.chunker import build_text_splitter


def save_uploaded_file(file_bytes: bytes, filename: str, target_dir: str) -> str:
    os.makedirs(target_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4()}_{filename}"
    file_path = Path(target_dir) / safe_name
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return str(file_path)


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
    splitter = build_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(docs)

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
