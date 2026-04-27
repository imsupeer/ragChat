import asyncio
from typing import Optional, List
from time import perf_counter
from uuid import uuid4
from core.observability import (
    build_chunk_debug,
    build_generation_debug,
    build_prompt_debug,
    elapsed_ms,
    log_structured,
)
from prompts.rag_prompt import build_rag_prompt
from retrieval.formatter import format_retrieved_chunks, serialize_sources
from retrieval.reranker import HeuristicReranker
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
        enable_hybrid: bool = False,
        enable_reranking: bool = False,
        rerank_top_m: int = 10,
        rerank_top_k: int = 5,
    ) -> None:
        self.chroma_service = chroma_service
        self.ollama_service = ollama_service
        self.max_context_chunks = max_context_chunks
        self.enable_reranking = enable_reranking
        self.rerank_top_k = min(max(rerank_top_k, 1), max_context_chunks)
        default_rerank_top_m = max(top_k, self.rerank_top_k * 2)
        requested_rerank_top_m = (
            rerank_top_m if rerank_top_m > 0 else default_rerank_top_m
        )
        self.rerank_top_m = max(requested_rerank_top_m, self.rerank_top_k)
        retrieval_top_k = max(top_k, self.rerank_top_m) if enable_reranking else top_k
        self.retriever = Retriever(
            chroma_service=chroma_service,
            top_k=retrieval_top_k,
            enable_hybrid=enable_hybrid,
        )
        self.reranker = HeuristicReranker() if enable_reranking else None

    def prepare(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
    ) -> dict:
        trace_id = str(uuid4())

        retrieval_started = perf_counter()
        retrieved_docs = self.retriever.search(
            question=question,
            document_ids=document_ids,
        )
        retrieval_finished = perf_counter()

        retrieval_debug = {
            "latency_ms": elapsed_ms(retrieval_started, retrieval_finished),
            "top_k": self.retriever.top_k,
            "max_context_chunks": self.max_context_chunks,
            "hybrid_enabled": self.retriever.enable_hybrid,
            "retrieval_mode": "hybrid" if self.retriever.enable_hybrid else "dense",
            "document_ids": document_ids or [],
            "retrieved_count": len(retrieved_docs),
            "used_count": 0,
            "results": [build_chunk_debug(doc) for doc in retrieved_docs],
        }

        reranking_debug = {
            "enabled": self.enable_reranking,
            "method": "heuristic_local" if self.enable_reranking else None,
            "latency_ms": 0.0,
            "top_m": self.rerank_top_m,
            "top_k": self.rerank_top_k,
            "candidate_count": min(len(retrieved_docs), self.rerank_top_m),
            "kept_count": 0,
            "results": [],
        }

        if self.enable_reranking and self.reranker:
            rerank_started = perf_counter()
            reranked_docs = self.reranker.rerank(
                question,
                retrieved_docs,
                top_m=self.rerank_top_m,
                top_k=self.rerank_top_k,
            )
            rerank_finished = perf_counter()
            used_docs = reranked_docs
            reranking_debug["latency_ms"] = elapsed_ms(rerank_started, rerank_finished)
            reranking_debug["kept_count"] = len(used_docs)
            reranking_debug["results"] = [build_chunk_debug(doc) for doc in used_docs]
            log_structured("rag.reranking", trace_id, reranking_debug)
        else:
            used_docs = retrieved_docs[: self.max_context_chunks]
            reranking_debug["kept_count"] = len(used_docs)

        retrieval_debug["used_count"] = len(used_docs)
        log_structured("rag.retrieval", trace_id, retrieval_debug)

        prompt_started = perf_counter()
        context = format_retrieved_chunks(used_docs)
        prompt = build_rag_prompt(retrieved_chunks=context, user_question=question)
        prompt_finished = perf_counter()
        prompt_debug = build_prompt_debug(
            prompt=prompt,
            context=context,
            used_docs=used_docs,
            latency_ms=elapsed_ms(prompt_started, prompt_finished),
        )
        log_structured("rag.prompt", trace_id, prompt_debug)

        return {
            "trace_id": trace_id,
            "prompt": prompt,
            "docs": used_docs,
            "sources": serialize_sources(used_docs),
            "debug": {
                "trace_id": trace_id,
                "retrieval": retrieval_debug,
                "reranking": reranking_debug,
                "prompt": prompt_debug,
            },
        }

    async def ask(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
    ) -> dict:
        request_started = perf_counter()
        prepared = await asyncio.to_thread(
            self.prepare,
            question=question,
            document_ids=document_ids,
        )

        generation_started = perf_counter()
        answer = await self.ollama_service.generate(prepared["prompt"])
        generation_finished = perf_counter()

        generation_debug = build_generation_debug(
            model=self.ollama_service.model,
            output_text=answer,
            latency_ms=elapsed_ms(generation_started, generation_finished),
        )
        log_structured("rag.generation", prepared["trace_id"], generation_debug)

        total_latency_ms = elapsed_ms(request_started, perf_counter())
        debug = {
            **prepared["debug"],
            "generation": generation_debug,
            "total_latency_ms": total_latency_ms,
        }
        log_structured(
            "rag.request.completed",
            prepared["trace_id"],
            {
                "total_latency_ms": total_latency_ms,
                "source_count": len(prepared["sources"]),
            },
        )

        return {
            "answer": answer,
            "sources": prepared["sources"],
            "debug": debug,
        }
