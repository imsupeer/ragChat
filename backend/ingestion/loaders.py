from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader, TextLoader


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}


def load_document(file_path: str):
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")

    if suffix == ".pdf":
        loader = PyPDFLoader(file_path)
        return loader.load()

    loader = TextLoader(file_path, encoding="utf-8")
    return loader.load()
