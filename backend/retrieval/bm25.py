import math
import re
from collections import Counter

from langchain_core.documents import Document


TOKEN_PATTERN = re.compile(r"[a-z0-9_./:-]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


class BM25Index:
    def __init__(
        self,
        documents: list[Document],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self._tokenized_docs = [tokenize(doc.page_content) for doc in documents]
        self._doc_term_freqs = [Counter(tokens) for tokens in self._tokenized_docs]
        self._doc_lengths = [len(tokens) for tokens in self._tokenized_docs]
        self._avg_doc_length = (
            sum(self._doc_lengths) / len(self._doc_lengths)
            if self._doc_lengths
            else 0.0
        )
        self._idf = self._build_idf()

    def _build_idf(self) -> dict[str, float]:
        total_docs = len(self._doc_term_freqs)
        document_frequencies: Counter[str] = Counter()

        for term_freqs in self._doc_term_freqs:
            for term in term_freqs:
                document_frequencies[term] += 1

        idf: dict[str, float] = {}
        for term, frequency in document_frequencies.items():
            idf[term] = math.log(1 + (total_docs - frequency + 0.5) / (frequency + 0.5))

        return idf

    def search(self, query: str, k: int = 5) -> list[tuple[Document, float]]:
        query_terms = tokenize(query)
        if not query_terms or not self.documents:
            return []

        unique_terms = list(dict.fromkeys(query_terms))
        scored_documents: list[tuple[int, Document, float]] = []

        for index, (doc, term_freqs) in enumerate(
            zip(self.documents, self._doc_term_freqs)
        ):
            document_length = self._doc_lengths[index]
            normalization = self.k1 * (
                1 - self.b + self.b * document_length / max(self._avg_doc_length, 1.0)
            )
            score = 0.0

            for term in unique_terms:
                frequency = term_freqs.get(term, 0)
                if frequency == 0:
                    continue

                idf = self._idf.get(term)
                if idf is None:
                    continue

                score += idf * (frequency * (self.k1 + 1) / (frequency + normalization))

            if score > 0:
                scored_documents.append((index, doc, score))

        scored_documents.sort(key=lambda item: (-item[2], item[0]))
        return [(doc, score) for _, doc, score in scored_documents[:k]]
