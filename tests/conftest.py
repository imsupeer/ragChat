import re
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

for path in (ROOT_DIR, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


class FakeEmbeddings:
    VOCAB = (
        "alpha",
        "beta",
        "gamma",
        "delta",
        "registry",
        "json",
        "queue",
        "chroma",
        "prompt",
    )

    TOKEN_RE = re.compile(r"[a-z0-9_./:-]+", re.IGNORECASE)

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        tokens = [token.lower() for token in self.TOKEN_RE.findall(text)]
        return [float(tokens.count(term)) for term in self.VOCAB]


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
