from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}

TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "latin-1")


def load_text_with_encoding_fallback(file_path: str):
    last_error: Exception | None = None

    for encoding in TEXT_ENCODINGS:
        try:
            loader = TextLoader(file_path, encoding=encoding)
            documents = loader.load()
            for document in documents:
                document.metadata["encoding"] = encoding
            return documents
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error

    raise ValueError("Text file could not be decoded.")


def load_document(file_path: str):
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")

    if suffix == ".pdf":
        loader = PyPDFLoader(file_path)
        return loader.load()

    return load_text_with_encoding_fallback(file_path)
