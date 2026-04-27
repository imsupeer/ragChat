from typing import List, Optional
from uuid import uuid4
from langchain_chroma import Chroma
from langchain_core.documents import Document
from retrieval.bm25 import BM25Index


class ChromaService:
    def __init__(self, persist_directory: str, embedding_function) -> None:
        self.persist_directory = persist_directory
        self.embedding_function = embedding_function
        self.collection_name = "rag_chat"
        self._vector_store = Chroma(
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_function,
        )

    @property
    def vector_store(self) -> Chroma:
        return self._vector_store

    def add_documents(self, document_id: str, docs: List[Document]) -> None:
        ids = [str(uuid4()) for _ in docs]

        for doc, chunk_id in zip(docs, ids):
            doc.metadata["document_id"] = document_id
            doc.metadata["chunk_id"] = chunk_id

        self._vector_store.add_documents(documents=docs, ids=ids)

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        document_ids: Optional[List[str]] = None,
    ) -> List[Document]:
        search_kwargs = {"k": k}
        if document_ids:
            search_kwargs["filter"] = {"document_id": {"$in": document_ids}}

        results = self._vector_store.similarity_search_with_score(
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

        return docs

    def lexical_search(
        self,
        query: str,
        k: int = 5,
        document_ids: Optional[List[str]] = None,
    ) -> List[Document]:
        docs = self.list_documents(document_ids=document_ids)
        if not docs:
            return []

        bm25 = BM25Index(docs)
        results = bm25.search(query=query, k=k)
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
        where_filter = None
        if document_ids:
            where_filter = {"document_id": {"$in": document_ids}}

        try:
            result = self._vector_store.get(
                where=where_filter,
                include=["documents", "metadatas"],
            )
        except TypeError:
            result = self._vector_store._collection.get(
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

    def delete_document(self, document_id: str) -> None:
        result = self._vector_store.get(
            where={"document_id": document_id},
            include=["metadatas"],
        )
        ids = result.get("ids") or []
        if ids:
            self._vector_store.delete(ids=ids)
