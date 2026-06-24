import threading
from collections.abc import Callable
from typing import Optional

from langchain_core.documents import Document

from retrieval.bm25 import BM25Index


class LexicalSearchCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._revision = 0
        self._corpus_docs: Optional[list[Document]] = None
        self._corpus_revision: Optional[int] = None
        self._indexes: dict[str, tuple[int, BM25Index]] = {}
        self.last_stats: dict[str, object] = {}

    def invalidate(self) -> None:
        with self._lock:
            self._revision += 1
            self._corpus_docs = None
            self._corpus_revision = None
            self._indexes.clear()

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    @staticmethod
    def cache_key(document_ids: Optional[list[str]]) -> str:
        if not document_ids:
            return "all"
        return ",".join(sorted(document_ids))

    @staticmethod
    def filter_documents(
        corpus: list[Document],
        document_ids: Optional[list[str]],
    ) -> list[Document]:
        if not document_ids:
            return corpus

        allowed = set(document_ids)
        return [
            doc
            for doc in corpus
            if (doc.metadata or {}).get("document_id") in allowed
        ]

    def search(
        self,
        *,
        query: str,
        k: int,
        document_ids: Optional[list[str]],
        load_corpus: Callable[[], list[Document]],
    ) -> tuple[list[tuple[Document, float]], dict[str, object]]:
        cache_key = self.cache_key(document_ids)
        corpus_cache_hit = False
        index_cache_hit = False
        corpus_size = 0
        scoped_corpus_size = 0

        with self._lock:
            if self._corpus_docs is None or self._corpus_revision != self._revision:
                self._corpus_docs = load_corpus()
                self._corpus_revision = self._revision
                self._indexes.clear()
            else:
                corpus_cache_hit = True

            corpus_size = len(self._corpus_docs)
            filtered_docs = self.filter_documents(self._corpus_docs, document_ids)
            scoped_corpus_size = len(filtered_docs)

            if not filtered_docs:
                stats = {
                    "cache_hit": corpus_cache_hit,
                    "corpus_cache_hit": corpus_cache_hit,
                    "index_cache_hit": False,
                    "corpus_size": corpus_size,
                    "scoped_corpus_size": 0,
                    "cache_key": cache_key,
                    "revision": self._revision,
                }
                self.last_stats = stats
                return [], stats

            cached = self._indexes.get(cache_key)
            if cached is not None and cached[0] == self._revision:
                bm25 = cached[1]
                index_cache_hit = True
            else:
                bm25 = BM25Index(filtered_docs)
                self._indexes[cache_key] = (self._revision, bm25)

        results = bm25.search(query=query, k=k)
        stats = {
            "cache_hit": corpus_cache_hit and index_cache_hit,
            "corpus_cache_hit": corpus_cache_hit,
            "index_cache_hit": index_cache_hit,
            "corpus_size": corpus_size,
            "scoped_corpus_size": scoped_corpus_size,
            "cache_key": cache_key,
            "revision": self._revision,
        }
        self.last_stats = stats
        return results, stats
