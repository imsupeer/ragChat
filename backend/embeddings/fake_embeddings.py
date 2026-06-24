import re


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
        "retrieval",
        "reranking",
        "hybrid",
        "dense",
        "limitation",
        "document",
        "chunk",
        "context",
        "ollama",
        "sqlite",
    )

    TOKEN_RE = re.compile(r"[a-z0-9_./:-]+", re.IGNORECASE)

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        tokens = [token.lower() for token in self.TOKEN_RE.findall(text)]
        return [float(tokens.count(term)) for term in self.VOCAB]
