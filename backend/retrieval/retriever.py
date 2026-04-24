from hashlib import sha1
from typing import List, Optional

from langchain_core.documents import Document

from services.chroma_service import ChromaService


class Retriever:
    def __init__(
        self,
        chroma_service: ChromaService,
        top_k: int = 5,
        enable_hybrid: bool = False,
        rrf_k: int = 60,
    ) -> None:
        self.chroma_service = chroma_service
        self.top_k = top_k
        self.enable_hybrid = enable_hybrid
        self.rrf_k = rrf_k

    def search(
        self, question: str, document_ids: Optional[List[str]] = None
    ) -> List[Document]:
        dense_docs = self.chroma_service.similarity_search(
            query=question,
            k=self.top_k,
            document_ids=document_ids,
        )
        if not self.enable_hybrid:
            return dense_docs

        lexical_docs = self.chroma_service.lexical_search(
            query=question,
            k=self.top_k,
            document_ids=document_ids,
        )

        if not lexical_docs:
            return dense_docs
        if not dense_docs:
            return lexical_docs

        return self._fuse_ranked_results(
            dense_docs=dense_docs, lexical_docs=lexical_docs
        )

    def _fuse_ranked_results(
        self,
        *,
        dense_docs: List[Document],
        lexical_docs: List[Document],
    ) -> List[Document]:
        entries: dict[str, dict] = {}

        for docs, method in ((dense_docs, "dense"), (lexical_docs, "lexical")):
            for fallback_rank, doc in enumerate(docs, start=1):
                key = self._doc_key(doc=doc, fallback_rank=fallback_rank)
                entry = entries.setdefault(
                    key,
                    {
                        "dense_doc": None,
                        "lexical_doc": None,
                        "dense_rank": None,
                        "dense_score": None,
                        "lexical_rank": None,
                        "lexical_score": None,
                        "rrf_score": 0.0,
                    },
                )

                rank = self._rank_for_method(
                    doc=doc,
                    method=method,
                    fallback_rank=fallback_rank,
                )
                score = self._score_for_method(doc=doc, method=method)

                entry[f"{method}_doc"] = doc
                entry[f"{method}_rank"] = rank
                entry[f"{method}_score"] = score
                entry["rrf_score"] += 1.0 / (self.rrf_k + rank)

        fused_docs: List[Document] = []

        for entry in entries.values():
            base_doc = entry["dense_doc"] or entry["lexical_doc"]
            if base_doc is None:
                continue

            metadata = dict(base_doc.metadata or {})
            retrieval_methods = []

            if entry["dense_rank"] is not None:
                retrieval_methods.append("dense")
            if entry["lexical_rank"] is not None:
                retrieval_methods.append("lexical")

            fused_score = round(entry["rrf_score"], 8)
            metadata["_dense_rank"] = entry["dense_rank"]
            metadata["_dense_score"] = entry["dense_score"]
            metadata["_lexical_rank"] = entry["lexical_rank"]
            metadata["_lexical_score"] = entry["lexical_score"]
            metadata["_hybrid_fused_score"] = fused_score
            metadata["_retrieval_methods"] = retrieval_methods
            metadata["_retrieval_method"] = (
                "hybrid" if len(retrieval_methods) > 1 else retrieval_methods[0]
            )
            metadata["_retrieval_score"] = fused_score
            metadata["_retrieval_score_type"] = "rrf"

            fused_docs.append(
                Document(
                    page_content=base_doc.page_content,
                    metadata=metadata,
                )
            )

        fused_docs.sort(
            key=lambda doc: (
                -float(doc.metadata.get("_hybrid_fused_score", 0.0)),
                self._best_rank(doc),
            )
        )

        for final_rank, doc in enumerate(fused_docs[: self.top_k], start=1):
            doc.metadata["_retrieval_rank"] = final_rank

        return fused_docs[: self.top_k]

    def _doc_key(self, doc: Document, fallback_rank: int) -> str:
        metadata = doc.metadata or {}
        chunk_id = metadata.get("chunk_id")
        if chunk_id:
            return str(chunk_id)

        document_id = metadata.get("document_id")
        chunk_index = metadata.get("chunk_index")
        if document_id is not None and chunk_index is not None:
            return f"{document_id}:{chunk_index}"

        source = metadata.get("source")
        if source is not None and chunk_index is not None:
            return f"{source}:{chunk_index}"

        content_hash = sha1(doc.page_content.encode("utf-8")).hexdigest()
        return f"fallback:{fallback_rank}:{content_hash}"

    def _rank_for_method(self, doc: Document, method: str, fallback_rank: int) -> int:
        value = (doc.metadata or {}).get(f"_{method}_rank")
        if value is None:
            value = (doc.metadata or {}).get("_retrieval_rank")

        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback_rank

    def _score_for_method(self, doc: Document, method: str) -> float | None:
        value = (doc.metadata or {}).get(f"_{method}_score")
        if value is None:
            value = (doc.metadata or {}).get("_retrieval_score")

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _best_rank(self, doc: Document) -> int:
        candidates = [
            (doc.metadata or {}).get("_dense_rank"),
            (doc.metadata or {}).get("_lexical_rank"),
            (doc.metadata or {}).get("_retrieval_rank"),
        ]
        numeric_ranks = []

        for candidate in candidates:
            try:
                numeric_ranks.append(int(candidate))
            except (TypeError, ValueError):
                continue

        return min(numeric_ranks) if numeric_ranks else self.top_k + self.rrf_k
