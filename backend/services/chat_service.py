import json
from typing import Optional, List, AsyncGenerator
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

    async def ask(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
    ) -> dict:
        docs = self.retriever.search(question=question, document_ids=document_ids)
        docs = docs[: self.max_context_chunks]
        context = format_retrieved_chunks(docs)
        prompt = build_rag_prompt(retrieved_chunks=context, user_question=question)
        answer = await self.ollama_service.generate(prompt)

        return {
            "answer": answer,
            "sources": serialize_sources(docs),
        }

    async def stream_answer(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        docs = self.retriever.search(question=question, document_ids=document_ids)
        docs = docs[: self.max_context_chunks]
        context = format_retrieved_chunks(docs)
        prompt = build_rag_prompt(retrieved_chunks=context, user_question=question)

        initial_payload = {
            "type": "sources",
            "sources": serialize_sources(docs),
        }
        yield f"data: {json.dumps(initial_payload, ensure_ascii=False)}\n\n"

        async for token in self.ollama_service.stream(prompt):
            payload = {
                "type": "token",
                "token": token,
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield 'data: {"type":"done"}\n\n'
