from typing import List, Optional
from uuid import uuid4

from langchain_chroma import Chroma
from langchain_core.documents import Document

from retrieval.collection_identity import resolve_active_collection_name
from retrieval.embedding_metadata import (
    embedding_metadata_from_provider,
    filter_dense_results,
)
from retrieval.lexical_cache import LexicalSearchCache
from services.embeddings_provider import EmbeddingsProvider


class ChromaService:
    def __init__(
        self,
        persist_directory: str,
        embedding_function,
        *,
        embeddings_provider: EmbeddingsProvider | None = None,
        collection_strategy: str = "per_embedding_provider",
        default_collection: str = "rag_chat",
        collection_prefix: str = "rag",
    ) -> None:
        self.persist_directory = persist_directory
        self.embedding_function = embedding_function
        self._embeddings_provider = embeddings_provider
        self._collection_strategy = collection_strategy
        self._default_collection = default_collection
        self._collection_prefix = collection_prefix
        self._vector_stores: dict[str, Chroma] = {}
        self._lexical_cache = LexicalSearchCache()
        self._last_embedding_filter_stats: dict[str, object] = {}
        self._active_collection_name = self._resolve_active_collection_name()

    @property
    def collection_name(self) -> str:
        return self._active_collection_name

    @property
    def vector_store(self) -> Chroma:
        return self._vector_store_for(self._active_collection_name)

    def _provider_info(self) -> dict[str, object] | None:
        if self._embeddings_provider is None:
            return None
        return self._embeddings_provider.provider_info()

    def _resolve_active_collection_name(self) -> str:
        info = self._provider_info()
        if info is None:
            return resolve_active_collection_name(
                strategy=self._collection_strategy,
                default_collection=self._default_collection,
                collection_prefix=self._collection_prefix,
            )
        return resolve_active_collection_name(
            strategy=self._collection_strategy,
            default_collection=self._default_collection,
            collection_prefix=self._collection_prefix,
            provider=str(info["provider"]),
            model=str(info["model"]),
            dimension=int(info["dimension"]),
        )

    def _collection_metadata(self) -> dict[str, str | int]:
        info = self._provider_info()
        if info is None:
            return {
                "collection_strategy": self._collection_strategy,
            }
        return {
            "embedding_provider": str(info["provider"]),
            "embedding_model": str(info["model"]),
            "embedding_dimension": int(info["dimension"]),
            "collection_strategy": self._collection_strategy,
        }

    def _vector_store_for(self, collection_name: str) -> Chroma:
        if collection_name in self._vector_stores:
            return self._vector_stores[collection_name]

        kwargs: dict[str, object] = {
            "collection_name": collection_name,
            "persist_directory": self.persist_directory,
            "embedding_function": self.embedding_function,
        }
        metadata = self._collection_metadata()
        try:
            store = Chroma(collection_metadata=metadata, **kwargs)
        except TypeError:
            store = Chroma(**kwargs)

        self._vector_stores[collection_name] = store
        return store

    def list_known_collection_names(self) -> list[str]:
        names = set(self._vector_stores.keys())
        names.add(self._active_collection_name)
        names.add(self._default_collection)
        try:
            import chromadb

            client = chromadb.PersistentClient(path=self.persist_directory)
            for collection in client.list_collections():
                names.add(collection.name)
        except Exception:
            pass
        return sorted(name for name in names if name)

    def get_collection_status(self) -> dict[str, object]:
        info = self._provider_info() or {}
        return {
            "strategy": self._collection_strategy,
            "active_collection": self._active_collection_name,
            "default_collection": self._default_collection,
            "provider": info.get("provider"),
            "model": info.get("model"),
            "dimension": info.get("dimension"),
            "known_collections": self.list_known_collection_names(),
        }

    def summarize_collections(self) -> dict[str, dict[str, int]]:
        summary: dict[str, dict[str, int]] = {}
        for collection_name in self.list_known_collection_names():
            summary[collection_name] = self._document_counts_for_collection(collection_name)
        return summary

    def get_last_embedding_filter_stats(self) -> dict[str, object]:
        return dict(self._last_embedding_filter_stats)

    def get_last_lexical_cache_stats(self) -> dict[str, object]:
        return dict(self._lexical_cache.last_stats)

    def add_documents(self, document_id: str, docs: List[Document]) -> None:
        ids = [str(uuid4()) for _ in docs]
        embedding_metadata: dict[str, str | int] = {}
        if self._embeddings_provider is not None:
            embedding_metadata = embedding_metadata_from_provider(
                self._embeddings_provider.provider_info()
            )
            embedding_metadata["collection_name"] = self._active_collection_name

        for doc, chunk_id in zip(docs, ids):
            doc.metadata["document_id"] = document_id
            doc.metadata["chunk_id"] = chunk_id
            if embedding_metadata:
                doc.metadata.update(embedding_metadata)

        self.vector_store.add_documents(documents=docs, ids=ids)
        self._lexical_cache.invalidate()

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        document_ids: Optional[List[str]] = None,
    ) -> List[Document]:
        search_kwargs = {"k": k}
        if document_ids:
            search_kwargs["filter"] = {"document_id": {"$in": document_ids}}

        results = self.vector_store.similarity_search_with_score(
            query, **search_kwargs
        )
        docs: List[Document] = []

        for rank, (doc, score) in enumerate(results, start=1):
            doc.metadata["_dense_score"] = float(score)
            doc.metadata["_dense_rank"] = rank
            doc.metadata["_retrieval_score"] = float(score)
            doc.metadata["_retrieval_rank"] = rank
            doc.metadata["_retrieval_score_type"] = "distance"
            doc.metadata["_retrieval_method"] = "dense"
            doc.metadata["_retrieval_methods"] = ["dense"]

            if "chunk_id" not in doc.metadata:
                chunk_id = getattr(doc, "id", None)
                if chunk_id:
                    doc.metadata["chunk_id"] = str(chunk_id)

            docs.append(doc)

        if self._embeddings_provider is not None:
            provider_info = self._embeddings_provider.provider_info()
            docs, filter_stats = filter_dense_results(
                docs,
                provider=str(provider_info["provider"]),
                model=str(provider_info["model"]),
                dimension=int(provider_info["dimension"]),
            )
            self._last_embedding_filter_stats = filter_stats
        else:
            self._last_embedding_filter_stats = {}

        return docs

    def lexical_search(
        self,
        query: str,
        k: int = 5,
        document_ids: Optional[List[str]] = None,
    ) -> List[Document]:
        results, _stats = self._lexical_cache.search(
            query=query,
            k=k,
            document_ids=document_ids,
            collection_name=self._active_collection_name,
            load_corpus=lambda: self.list_documents(document_ids=None),
        )

        if not results:
            return []

        ranked_docs: List[Document] = []

        for rank, (doc, score) in enumerate(results, start=1):
            doc.metadata["_lexical_score"] = float(score)
            doc.metadata["_lexical_rank"] = rank
            doc.metadata["_retrieval_score"] = float(score)
            doc.metadata["_retrieval_rank"] = rank
            doc.metadata["_retrieval_score_type"] = "bm25"
            doc.metadata["_retrieval_method"] = "lexical"
            doc.metadata["_retrieval_methods"] = ["lexical"]
            ranked_docs.append(doc)

        return ranked_docs

    def list_documents(
        self,
        document_ids: Optional[List[str]] = None,
    ) -> List[Document]:
        return self._list_documents_from_collection(
            self._active_collection_name,
            document_ids=document_ids,
        )

    def delete_document(self, document_id: str) -> None:
        targets = (
            [self._active_collection_name]
            if self._collection_strategy == "legacy_single"
            else self.list_known_collection_names()
        )
        for collection_name in targets:
            self._delete_document_from_collection(document_id, collection_name)
        self._lexical_cache.invalidate()

    def delete_document_from_active_collection(self, document_id: str) -> None:
        self._delete_document_from_collection(document_id, self._active_collection_name)
        self._lexical_cache.invalidate()

    def list_document_ids_with_vector_counts(self) -> dict[str, int]:
        return self._document_counts_for_collection(self._active_collection_name)

    def list_chunk_metadatas(self) -> list[dict[str, object]]:
        store = self._vector_store_for(self._active_collection_name)
        try:
            result = store.get(include=["metadatas"])
        except TypeError:
            result = store._collection.get(include=["metadatas"])

        metadatas: list[dict[str, object]] = []
        for metadata in result.get("metadatas") or []:
            metadatas.append(dict(metadata or {}))
        return metadatas

    def _list_documents_from_collection(
        self,
        collection_name: str,
        *,
        document_ids: Optional[List[str]] = None,
    ) -> List[Document]:
        where_filter = None
        if document_ids:
            where_filter = {"document_id": {"$in": document_ids}}

        store = self._vector_store_for(collection_name)
        try:
            result = store.get(
                where=where_filter,
                include=["documents", "metadatas"],
            )
        except TypeError:
            result = store._collection.get(
                where=where_filter,
                include=["documents", "metadatas"],
            )

        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        materialized: List[Document] = []

        for index, page_content in enumerate(documents):
            if not isinstance(page_content, str):
                continue

            metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
            if "chunk_id" not in metadata and index < len(ids):
                metadata["chunk_id"] = str(ids[index])
            materialized.append(Document(page_content=page_content, metadata=metadata))

        return materialized

    def _delete_document_from_collection(self, document_id: str, collection_name: str) -> None:
        store = self._vector_store_for(collection_name)
        try:
            result = store.get(
                where={"document_id": document_id},
                include=["metadatas"],
            )
        except TypeError:
            result = store._collection.get(
                where={"document_id": document_id},
                include=["metadatas"],
            )
        ids = result.get("ids") or []
        if ids:
            store.delete(ids=ids)

    def _document_counts_for_collection(self, collection_name: str) -> dict[str, int]:
        store = self._vector_store_for(collection_name)
        try:
            result = store.get(include=["metadatas"])
        except TypeError:
            result = store._collection.get(include=["metadatas"])

        counts: dict[str, int] = {}
        for metadata in result.get("metadatas") or []:
            if not metadata:
                continue
            document_id = metadata.get("document_id")
            if not document_id:
                continue
            document_key = str(document_id)
            counts[document_key] = counts.get(document_key, 0) + 1
        return counts
