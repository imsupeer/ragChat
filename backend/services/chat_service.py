from typing import Optional, List
from prompts.rag_prompt import build_rag_prompt
from retrieval.formatter import format_retrieved_chunks, serialize_sources
from retrieval.retriever import Retriever
from services.chroma_service import ChromaService
from services.ollama_service import OllamaService


class ChatService:
    def __init__(
        self,
        chroma_service: ChromaService,
        ollama_service: OllamaService,
        top_k: int = 5,
        max_context_chunks: int = 5,
    ) -> None:
        self.chroma_service = chroma_service
        self.ollama_service = ollama_service
        self.retriever = Retriever(chroma_service=chroma_service, top_k=top_k)
        self.max_context_chunks = max_context_chunks

    def prepare(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
    ) -> dict:
        docs = self.retriever.search(question=question, document_ids=document_ids)
        docs = docs[: self.max_context_chunks]
        context = format_retrieved_chunks(docs)
        prompt = build_rag_prompt(retrieved_chunks=context, user_question=question)

        return {
            "prompt": prompt,
            "docs": docs,
            "sources": serialize_sources(docs),
        }

    async def ask(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
    ) -> dict:
        prepared = self.prepare(question=question, document_ids=document_ids)
        answer = await self.ollama_service.generate(prepared["prompt"])

        return {
            "answer": answer,
            "sources": prepared["sources"],
        }
