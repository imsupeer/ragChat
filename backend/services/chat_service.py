import asyncio
from typing import Optional, List
from time import perf_counter
from uuid import uuid4
from core.observability import (
    build_chunk_debug,
    build_generation_debug,
    build_prompt_debug,
    build_query_rewriting_debug,
    elapsed_ms,
    log_structured,
)
from prompts.rag_prompt import build_rag_prompt
from retrieval.formatter import format_retrieved_chunks, serialize_sources
from retrieval.reranker import HeuristicReranker
from retrieval.retriever import Retriever
from services.chroma_service import ChromaService
from services.ollama_service import OllamaService
from services.query_rewriter import QueryRewriter, QueryRewriteOutcome
from services.metrics import get_local_metrics


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
        query_rewriter: QueryRewriter | None = None,
        answer_mode: str = "strict_rag",
    ) -> None:
        self.chroma_service = chroma_service
        self.ollama_service = ollama_service
        self.query_rewriter = query_rewriter
        self.answer_mode = answer_mode
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
        user_question: str,
        document_ids: Optional[List[str]] = None,
        retrieval_question: Optional[str] = None,
        query_rewriting_debug: Optional[dict] = None,
    ) -> dict:
        trace_id = str(uuid4())
        original_question = user_question.strip()
        retrieval_query = (retrieval_question or original_question).strip()

        retrieval_started = perf_counter()
        retrieved_docs = self.retriever.search(
            question=retrieval_query,
            document_ids=document_ids,
        )
        retrieval_finished = perf_counter()
        retrieval_latency_ms = elapsed_ms(retrieval_started, retrieval_finished)
        metrics = get_local_metrics()
        metrics.set_last("retrieval.last_latency_ms", retrieval_latency_ms)
        if self.retriever.enable_hybrid:
            metrics.increment("retrieval.hybrid")
        else:
            metrics.increment("retrieval.dense")
        if self.enable_reranking:
            metrics.increment("retrieval.reranking.enabled")

        retrieval_debug = {
            "latency_ms": retrieval_latency_ms,
            "top_k": self.retriever.top_k,
            "max_context_chunks": self.max_context_chunks,
            "hybrid_enabled": self.retriever.enable_hybrid,
            "retrieval_mode": "hybrid" if self.retriever.enable_hybrid else "dense",
            "document_ids": document_ids or [],
            "retrieved_count": len(retrieved_docs),
            "used_count": 0,
            "query": retrieval_query,
            "results": [build_chunk_debug(doc) for doc in retrieved_docs],
        }

        rewriting_debug = query_rewriting_debug or build_query_rewriting_debug(
            enabled=False,
            used=False,
            original_question=original_question,
            rewritten_query=retrieval_query,
            history_turns_used=0,
            latency_ms=0.0,
        )

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
                retrieval_query,
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
        retrieval_debug["candidate_count"] = len(retrieved_docs)
        log_structured("rag.retrieval", trace_id, retrieval_debug)

        prompt_started = perf_counter()
        context = format_retrieved_chunks(used_docs)
        prompt = build_rag_prompt(
            retrieved_chunks=context,
            user_question=original_question,
            answer_mode=self.answer_mode,
        )
        prompt_finished = perf_counter()
        prompt_debug = build_prompt_debug(
            prompt=prompt,
            context=context,
            used_docs=used_docs,
            latency_ms=elapsed_ms(prompt_started, prompt_finished),
            answer_mode=self.answer_mode,
        )
        log_structured("rag.prompt", trace_id, prompt_debug)
        if rewriting_debug.get("enabled"):
            log_structured("rag.query_rewriting", trace_id, rewriting_debug)

        return {
            "trace_id": trace_id,
            "prompt": prompt,
            "docs": used_docs,
            "sources": serialize_sources(used_docs),
            "debug": {
                "trace_id": trace_id,
                "query_rewriting": rewriting_debug,
                "retrieval": retrieval_debug,
                "reranking": reranking_debug,
                "prompt": prompt_debug,
            },
        }

    async def resolve_retrieval_query(
        self,
        question: str,
        chat_history: Optional[List[dict]] = None,
    ) -> QueryRewriteOutcome:
        history = chat_history or []
        if self.query_rewriter is None:
            return QueryRewriteOutcome(
                enabled=False,
                used=False,
                original_question=question.strip(),
                rewritten_query=question.strip(),
                history_turns_used=0,
                latency_ms=0.0,
            )

        return await self.query_rewriter.rewrite(question, history)

    async def prepare_request(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
        chat_history: Optional[List[dict]] = None,
        retrieval_question: Optional[str] = None,
        query_rewriting_debug: Optional[dict] = None,
    ) -> dict:
        if retrieval_question is None and query_rewriting_debug is None:
            rewrite_outcome = await self.resolve_retrieval_query(question, chat_history)
            retrieval_question = rewrite_outcome.rewritten_query
            query_rewriting_debug = rewrite_outcome.to_debug()
        elif query_rewriting_debug is None:
            query_rewriting_debug = build_query_rewriting_debug(
                enabled=False,
                used=retrieval_question.strip() != question.strip(),
                original_question=question.strip(),
                rewritten_query=(retrieval_question or question).strip(),
                history_turns_used=0,
                latency_ms=0.0,
            )

        return await asyncio.to_thread(
            self.prepare,
            user_question=question,
            document_ids=document_ids,
            retrieval_question=retrieval_question,
            query_rewriting_debug=query_rewriting_debug,
        )

    async def ask(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
        chat_history: Optional[List[dict]] = None,
        retrieval_question: Optional[str] = None,
        query_rewriting_debug: Optional[dict] = None,
    ) -> dict:
        request_started = perf_counter()
        prepared = await self.prepare_request(
            question=question,
            document_ids=document_ids,
            chat_history=chat_history,
            retrieval_question=retrieval_question,
            query_rewriting_debug=query_rewriting_debug,
        )

        generation_started = perf_counter()
        answer = await self.ollama_service.generate(prepared["prompt"])
        generation_finished = perf_counter()

        generation_debug = build_generation_debug(
            model=self.ollama_service.model,
            output_text=answer,
            latency_ms=elapsed_ms(generation_started, generation_finished),
            keep_alive=self.ollama_service.keep_alive,
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
