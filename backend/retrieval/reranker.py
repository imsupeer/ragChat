import re
from typing import List

from langchain_core.documents import Document

from retrieval.bm25 import tokenize


WHITESPACE_RE = re.compile(r"\s+")
GENERIC_QUERY_TERMS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "chunk",
    "chunks",
    "contains",
    "contain",
    "describe",
    "document",
    "documents",
    "entries",
    "entry",
    "explain",
    "file",
    "find",
    "for",
    "how",
    "in",
    "is",
    "list",
    "me",
    "of",
    "page",
    "pages",
    "section",
    "sections",
    "show",
    "store",
    "stores",
    "tell",
    "that",
    "the",
    "these",
    "this",
    "what",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text.lower()).strip()


def build_bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return {(tokens[index], tokens[index + 1]) for index in range(len(tokens) - 1)}


class HeuristicReranker:
    def rerank(
        self,
        query: str,
        docs: List[Document],
        *,
        top_m: int,
        top_k: int,
    ) -> List[Document]:
        candidates = list(docs[:top_m])
        if not candidates:
            return []

        if not query.strip() or len(candidates) == 1:
            return self._annotate(
                candidates, scores=[0.0] * len(candidates), top_k=top_k
            )

        scored = []
        for index, doc in enumerate(candidates):
            score = self._score(query=query, doc=doc)
            retrieval_rank = self._retrieval_rank(doc)
            scored.append((score, retrieval_rank, index, doc))

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        reranked_docs = [doc for _, _, _, doc in scored]
        rerank_scores = [score for score, _, _, _ in scored]

        return self._annotate(reranked_docs, scores=rerank_scores, top_k=top_k)

    def _annotate(
        self,
        docs: List[Document],
        *,
        scores: list[float],
        top_k: int,
    ) -> List[Document]:
        annotated: List[Document] = []

        for rerank_rank, (doc, score) in enumerate(
            zip(docs[:top_k], scores[:top_k]), start=1
        ):
            metadata = dict(doc.metadata or {})
            metadata["_rerank_score"] = round(float(score), 8)
            metadata["_rerank_rank"] = rerank_rank
            annotated.append(
                Document(
                    page_content=doc.page_content,
                    metadata=metadata,
                )
            )

        return annotated

    def _score(self, query: str, doc: Document) -> float:
        query_tokens = tokenize(query)
        if not query_tokens:
            return 0.0

        query_terms = list(dict.fromkeys(query_tokens))
        query_term_set = set(query_terms)
        query_bigrams = build_bigrams(query_tokens)
        query_norm = normalize_text(query)

        doc_text = doc.page_content or ""
        doc_norm = normalize_text(doc_text)
        doc_tokens = tokenize(doc_text)
        doc_term_set = set(doc_tokens)
        doc_bigrams = build_bigrams(doc_tokens)

        metadata = doc.metadata or {}
        metadata_text = " ".join(
            str(value)
            for value in (
                metadata.get("source"),
                metadata.get("document_id"),
                metadata.get("page"),
                metadata.get("chunk_index"),
            )
            if value is not None
        )
        metadata_norm = normalize_text(metadata_text)
        metadata_term_set = set(tokenize(metadata_text))

        matched_doc_terms = query_term_set & doc_term_set
        matched_metadata_terms = (
            query_term_set - matched_doc_terms
        ) & metadata_term_set
        matched_terms = matched_doc_terms | matched_metadata_terms

        coverage_score = len(matched_terms) / len(query_term_set)
        doc_match_score = len(matched_doc_terms) / len(query_term_set)
        metadata_match_score = len(matched_metadata_terms) / len(query_term_set)

        bigram_score = (
            len(query_bigrams & doc_bigrams) / len(query_bigrams)
            if query_bigrams
            else 0.0
        )

        exact_phrase_bonus = 1.0 if query_norm and query_norm in doc_norm else 0.0
        metadata_phrase_bonus = (
            0.5 if query_norm and query_norm in metadata_norm else 0.0
        )

        retrieval_prior = 1.0 / (60 + self._retrieval_rank(doc))
        important_terms = [
            term
            for term in query_term_set
            if (
                term not in GENERIC_QUERY_TERMS
                and (
                    len(term) >= 6
                    or any(char.isdigit() for char in term)
                    or any(char in "._-/:#" for char in term)
                )
            )
        ]
        important_matches = [term for term in important_terms if term in matched_terms]
        important_match_score = (
            len(important_matches) / len(important_terms) if important_terms else 0.0
        )
        has_strong_match = (
            len(matched_terms) >= 2
            or bool(important_matches)
            or bigram_score > 0.0
            or exact_phrase_bonus > 0.0
            or metadata_phrase_bonus > 0.0
        )

        if not has_strong_match:
            return retrieval_prior

        return (
            coverage_score * 3.0
            + doc_match_score * 2.0
            + metadata_match_score * 0.75
            + bigram_score * 2.0
            + exact_phrase_bonus * 2.0
            + metadata_phrase_bonus
            + important_match_score * 1.5
            + retrieval_prior
        )

    def _retrieval_rank(self, doc: Document) -> int:
        value = (doc.metadata or {}).get("_retrieval_rank")
        try:
            return int(value)
        except (TypeError, ValueError):
            return 9999
