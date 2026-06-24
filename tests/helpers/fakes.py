from collections.abc import AsyncIterator


class FakeOllamaService:
    def __init__(self, tokens=None, fail: bool = False) -> None:
        self.model = "test-model"
        self.tokens = tokens or ["Hello", " world"]
        self.fail = fail

    async def generate(self, prompt: str) -> str:
        if self.fail:
            raise RuntimeError("Ollama unavailable")
        return "".join(self.tokens)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        if self.fail:
            raise RuntimeError("Ollama unavailable")
        for token in self.tokens:
            yield token


class FakeChromaService:
    def __init__(
        self,
        counts: dict[str, int] | None = None,
        *,
        should_fail: bool = False,
    ) -> None:
        self.counts = dict(counts or {})
        self.should_fail = should_fail
        self.added: list[tuple[str, int]] = []
        self.deleted: list[str] = []

    def list_document_ids_with_vector_counts(self) -> dict[str, int]:
        if self.should_fail:
            raise RuntimeError("Chroma unavailable")
        return dict(self.counts)

    def add_documents(self, document_id: str, docs) -> None:
        self.added.append((document_id, len(docs)))

    def delete_document(self, document_id: str) -> None:
        self.deleted.append(document_id)

    def get_last_lexical_cache_stats(self) -> dict[str, object]:
        return {"cache_hit": False}
