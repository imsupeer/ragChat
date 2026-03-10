from typing import List, Optional
from langchain_core.documents import Document
from services.chroma_service import ChromaService


class Retriever:
    def __init__(self, chroma_service: ChromaService, top_k: int = 5) -> None:
        self.chroma_service = chroma_service
        self.top_k = top_k

    def search(
        self, question: str, document_ids: Optional[List[str]] = None
    ) -> List[Document]:
        return self.chroma_service.similarity_search(
            query=question,
            k=self.top_k,
            document_ids=document_ids,
        )
