# Local RAG Workspace

Personal project focused on one problem: how to build a local RAG system that is inspectable, reproducible, and honest about its trade-offs.

This is not positioned as a SaaS clone or "chat with docs" product. It is a full-stack engineering project that demonstrates document ingestion, structure-aware chunking, hybrid retrieval, reranking, grounded generation, streaming UX, source attribution, observability, and lightweight evaluation running entirely on local infrastructure.

## Screenshots

<p align="center">
  <img src="docs/screenshots/workspace-overview.png" alt="Main workspace with chat, documents, pipeline stages, and evidence panel" width="100%" />
</p>

<p align="center">
  <img src="docs/screenshots/evidence-panel.png" alt="Evidence workspace showing retrieval diagnostics, timings, and token estimates" width="49%" />
  <img src="docs/screenshots/upload-and-documents.png" alt="Chat response with indexed documents and source inspection workflow" width="49%" />
</p>

## What This Project Demonstrates

- Full local RAG stack using FastAPI, Next.js, Ollama, ChromaDB, LangChain, SQLite, and Zustand
- Structure-aware ingestion for PDF, TXT, and Markdown instead of fixed-size splitting only
- Dense retrieval baseline with optional BM25 lexical retrieval and Reciprocal Rank Fusion
- Optional post-retrieval reranking to improve final chunk ordering
- Grounded prompt construction with explicit evidence formatting
- Streaming answers with source references and debug metadata exposed to the UI
- Structured observability for retrieval, reranking, prompt building, and generation
- Lightweight offline evaluation harness for retrieval recall and answer correctness

## Why I Built It

Most RAG demos stop at "upload a file and ask a question." I wanted a project that was more useful in interviews and more realistic as an engineering artifact:

- the backend should separate ingestion from chat serving
- retrieval decisions should be visible and measurable
- the frontend should show how an answer was built, not just render text
- the whole system should run locally so infrastructure, latency, and quality trade-offs stay visible

The result is a portfolio project about system design, not just model integration.

## Architecture

```text
Upload flow
  Next.js
    -> POST /documents/upload
    -> save raw file to local storage
    -> create upload job in SQLite
    -> enqueue background indexing task
    -> load + segment document
    -> structure-aware chunking
    -> embed with Ollama
    -> store chunks in ChromaDB
    -> register document metadata

Question flow
  Next.js
    -> POST /chat or /chat/stream
    -> retrieve dense or hybrid candidates
    -> optional reranking
    -> build grounded prompt
    -> generate with Ollama
    -> stream tokens + sources + debug info
    -> persist chat history in SQLite
```

## Technical Highlights

### 1. Structure-aware chunking

The ingestion pipeline first segments documents by structure, then applies recursive splitting to stay within chunk limits.

- Markdown is split by heading hierarchy
- PDFs preserve page numbers and detect heading-like lines heuristically
- chunks carry `section_title`, `section_path`, and `page` metadata

This improves both retrieval quality and source attribution compared with pure fixed-size chunking.

### 2. Hybrid retrieval

Dense similarity search is still the baseline, but the system can optionally add local BM25 keyword search.

- dense search catches semantic matches
- BM25 helps with filenames, identifiers, exact terms, and version-like strings
- results are merged with Reciprocal Rank Fusion

This makes the retrieval pipeline more realistic than a dense-only demo while keeping everything local and lightweight.

### 3. Optional reranking

After retrieval, the system can rerank the top candidates with a lightweight local scoring function.

- improves final chunk ordering
- helps promote chunks that directly answer the question
- stays cheaper and easier to inspect than a heavy cross-encoder dependency

### 4. Observability built into the RAG path

The backend exposes structured debug data instead of hiding the pipeline behind a spinner.

Available debug data includes:

- retrieval scores, methods, and chunk IDs
- rerank rank and rerank score
- prompt length and token estimates
- generation latency and output token estimates
- total request latency and per-stage timings

The frontend surfaces this through an evidence workspace so the project demonstrates RAG debugging, not just RAG output.

### 5. Evaluation harness

The repo includes a lightweight evaluation script and a small fixture dataset.

It can measure:

- retrieval recall@k
- whether the expected chunk was retrieved
- simple answer correctness heuristics

That gives the project a measurable path for comparing chunking, retrieval, and reranking changes.

## Key Engineering Decisions

| Decision | Why it was chosen | Trade-off |
| --- | --- | --- |
| Use Ollama for chat and embeddings | Keeps the stack fully local and reproducible | Local models are weaker than top hosted models |
| Split persistence across Chroma, SQLite, JSON, and filesystem | Each concern stays easy to inspect | Consistency has to be managed manually |
| Use an in-process queue for indexing | Uploads return quickly without extra infrastructure | Jobs are not durable across crashes |
| Make hybrid retrieval and reranking optional | Baseline behavior stays simple and debuggable | More config branches to reason about |
| Surface debug metadata in the API and UI | Makes failures easier to diagnose | Adds payload size and implementation complexity |
| Keep the prompt strict and grounded | Makes hallucinations easier to spot | Missed retrievals produce conservative failures |

## Current Stack

### Backend

- FastAPI
- LangChain
- Ollama
- ChromaDB
- SQLite
- PyPDF

### Frontend

- Next.js 14
- React 18
- TypeScript
- Tailwind CSS
- Zustand

## Repository Guide

- `scripts/eval.py`: lightweight evaluation harness
- `tests/`: focused pytest suite across API, ingestion, retrieval, and prompt logic

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- Ollama running locally

Recommended models:

```bash
ollama pull llama3.1
ollama pull mxbai-embed-large
ollama serve
```

### Backend

Create `backend/.env`:

```env
APP_NAME=Local RAG Workspace
APP_ENV=development
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.1
OLLAMA_EMBED_MODEL=mxbai-embed-large

CHROMA_PERSIST_DIRECTORY=./vector_db
DOCUMENTS_DIRECTORY=./storage/docs
REGISTRY_PATH=./storage/registry.json
SQLITE_PATH=./storage/app.db

CHUNK_SIZE=800
CHUNK_OVERLAP=200
TOP_K=5
MAX_CONTEXT_CHUNKS=5
ENABLE_HYBRID=true
ENABLE_RERANKING=true
RERANK_TOP_M=10
RERANK_TOP_K=5
```

Run:

```bash
cd backend
python -m venv venv
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

Create `frontend/.env`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Run:

```bash
cd frontend
npm install
npm run dev
```

## Docker

```bash
cd docker
docker compose up --build
```

The current Docker setup still expects Ollama to be running locally and reachable from the backend container.

## Verification

From the repo root:

```bash
python -m pytest
```

From `frontend/`:

```bash
npm run build
```

Optional retrieval evaluation:

```bash
python scripts/eval.py --skip-generation
python scripts/eval.py
```

## Limitations

This project is intentionally strong as a portfolio artifact because the limitations are visible rather than hidden.

- The ingestion worker is in-process and not durable across backend restarts
- BM25 is rebuilt on demand instead of maintained as a dedicated lexical index
- Reranking is heuristic rather than model-based
- PDF handling is text extraction only and not layout-aware
- Persistence is split across several local stores without cross-store transactions
- The evaluation harness is small and heuristic, not a full benchmark suite
- The project is local-first and single-user; it does not try to solve auth, multitenancy, or hosted operations

## Where I Would Take It Next

- stronger retrieval evaluation with a larger gold dataset
- learned reranking or cross-encoder scoring
- contextual compression before prompt assembly
- richer failure analysis and tracing
- more robust ingestion with durable background jobs

## Why It Works As A Portfolio Project

This repo lets me talk concretely about:

- how I separate ingestion from serving
- how I reason about chunking and retrieval quality
- how I combine lexical and semantic retrieval
- how I expose evidence and observability in the UI
- how I think about local-first trade-offs instead of hiding everything behind managed APIs

That makes it a better engineering portfolio piece than a generic AI demo because the interesting decisions are visible in both the code and the interface.
