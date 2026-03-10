from typing import List, Optional
from uuid import uuid4
from langchain_chroma import Chroma
from langchain_core.documents import Document


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

        for doc in docs:
            doc.metadata["document_id"] = document_id

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
        return self._vector_store.similarity_search(query, **search_kwargs)

    def delete_document(self, document_id: str) -> None:
        self._vector_store.delete(where={"document_id": document_id})
