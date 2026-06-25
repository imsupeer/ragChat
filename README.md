# Local RAG Workspace

## Project Summary

**Local RAG Workspace** is a local-first, full-stack RAG portfolio project — an engineering artifact built to show how retrieval-augmented generation works end to end, not a hosted “chat with your docs” product.

|             |                                                                 |
| ----------- | --------------------------------------------------------------- |
| **Stack**   | FastAPI · Next.js · Ollama (default) · ChromaDB · SQLite        |
| **Also supports** | llama.cpp chat · local embeddings (`local_hash`, `sentence_transformers`) |
| **Purpose** | Inspectable RAG with sources, pipeline stages, and debug traces |
| **Runtime** | Single-user, runs entirely on your machine                      |

Upload documents, ask grounded questions, constrain retrieval to selected files, stream answers over SSE, and inspect retrieval scores, reranking, prompt assembly, and generation metadata in the UI. Every major pipeline stage is visible in code and in the **Evidence Workspace** panel.

## Engineering Highlights

- **Structure-aware chunking** — Markdown headings, PDF page metadata, section paths on every chunk
- **Dense retrieval** — semantic search via embeddings + ChromaDB (Ollama default; local alternatives available)
- **Optional hybrid BM25 + RRF** — lexical + dense merge for exact-term and identifier matches
- **Optional heuristic reranking** — local post-retrieval reordering without a cross-encoder dependency
- **Strict grounded prompting** — answers must cite retrieved context; explicit refusal when evidence is missing
- **SSE streaming** — token-by-token generation with structured error events
- **Upload recovery** — SQLite job queue, startup re-enqueue, Chroma rollback on partial failure, frontend retry
- **Persisted debug metadata** — retrieval/rerank/prompt/generation debug survives page reload in SQLite
- **Local eval harness** — fixture dataset, recall@k, offline mode with `--fake-embeddings`
- **Playwright smoke demo** — one local E2E test for upload → chat → sources → persisted debug (not CI)
- **Optional multi-turn query rewriting** — chat history rewrites the retrieval query only; final answers stay document-grounded
- **Model Advisor** — hardware-based Ollama model recommendations, runtime status, preload/unload controls
- **Hardware telemetry** — local CPU/RAM/GPU panel (best-effort; no cloud calls)
- **Provider abstractions** — swappable LLM and embeddings providers without rewriting the RAG flow
- **Per-provider Chroma collections** — vectors isolated by embeddings provider to avoid vector-space mismatch
- **Explicit reindex workflow** — opt-in reindex of registered documents when switching embeddings providers

## Demo Flow

Use this path for interviews, portfolio walkthroughs, or the Playwright smoke test.

1. **Start Ollama** on the host (`ollama serve`) and pull models (e.g. `llama3.1:8b`, `mxbai-embed-large`).
2. **Start the backend** — `uvicorn` on port 8000 or Docker `rag-backend` with `OLLAMA_BASE_URL=http://host.docker.internal:11434`.
3. **Start the frontend** at `http://localhost:3000` (`npm run dev` or Docker `rag-frontend`).
4. **Upload a fixture document** — e.g. `scripts/eval_data/docs/limitations.md` from the sidebar uploader.
5. **Wait for indexing** — upload queue reaches completed; document appears under **Indexed documents**.
6. **Ask a grounded question** — e.g. _“Does PDF handling include OCR?”_ with the document selected.
7. **Inspect sources and debug** — open **Evidence Workspace → Sources** and **Debug** (retrieval, used-in-prompt chunks, optional query rewrite).
8. **Reload the page** — confirm chat history and debug metadata persist on the assistant message.
9. **Run the smoke demo** (optional) — from `frontend/`: `npm run test:e2e` (requires Ollama, backend, and frontend running).

For follow-up rewriting, set `ENABLE_QUERY_REWRITING=true` in `backend/.env`, restart the backend, ask a first question in a chat, then a pronoun-style follow-up (e.g. _“Is it enabled by default?”_) and check **Query Rewriting** in the Debug tab.

## Screenshots

<p align="center">
  <img src="assets/screenshots/Screenshot_1.png" alt="Main workspace with chat, documents, pipeline stages, and evidence panel" width="100%" />
</p>

<p align="center">
  <img src="assets/screenshots/Screenshot_2.png" alt="Evidence workspace showing retrieval diagnostics, timings, and token estimates" width="49%" />
  <img src="assets/screenshots/Screenshot_3.png" alt="Chat response with indexed documents and source inspection workflow" width="49%" />
</p>

## Why I Built It

Most RAG demos stop at "upload a file and ask a question." I wanted a project that was more useful in interviews and more realistic as an engineering artifact:

- the backend should separate ingestion from chat serving
- retrieval decisions should be visible and measurable
- the frontend should show how an answer was built, not just render text
- the whole system should run locally so infrastructure, latency, and quality trade-offs stay visible

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
    -> embed with active embeddings provider
    -> store chunks in active Chroma collection
    -> register document metadata

Question flow
  Next.js
    -> POST /chat or /chat/stream
    -> optional query rewrite from chat history (retrieval query only)
    -> retrieve dense or hybrid candidates
    -> optional reranking
    -> build grounded prompt from retrieved chunks + original question
    -> generate with active LLM provider
    -> stream tokens + sources + debug info
    -> persist chat history and debug metadata in SQLite
```

## Persistence model

Data is split across four stores (no distributed transactions — consistency is application-managed):

| Store | Role |
| ----- | ---- |
| **Filesystem** (`storage/docs/`) | Raw uploaded files |
| **JSON registry** (`storage/registry.json`) | Document metadata (`id`, filename, path, chunk count) |
| **SQLite** (`storage/app.db`) | Chats, messages, upload jobs, persisted debug JSON |
| **ChromaDB** (`vector_db/`) | Embeddings and chunk metadata (per-provider collections when configured) |

**Upload recovery:** Jobs are tracked in SQLite. On restart, `queued` / `processing` jobs are re-enqueued. Failed registry writes roll back Chroma vectors. Document delete removes vectors (all known collections) → file → registry, with safe partial-failure handling.

**Reconciliation:** On startup (`RECONCILE_ON_STARTUP=true`), a read-only drift report compares registry, Chroma, filesystem, and upload jobs. Inspect via `GET /debug/reconciliation`. Optional repair plan at `POST /debug/reconciliation/repair` (dry-run by default; only safe fixes apply).

## Observability and safety

- Structured debug on every RAG request: retrieval scores, rerank details, prompt assembly, timings, token estimates
- Debug metadata persisted on assistant messages in SQLite and survives reload
- `GET /health` — liveness; `GET /health/ready` — SQLite, Chroma, upload worker, embeddings, reconciliation
- `GET /debug/metrics` — in-process counters (uploads, indexing, streams, reconciliation, cache hits)
- API errors are sanitized (no absolute paths in client responses); full details stay in server logs
- SSE stream errors use structured `{ type: "error", message, code, recoverable }` events

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

## Key Design Decisions

| Decision                                                             | Why it was chosen                                                                              | Trade-off                                                       |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Local-first (Ollama + ChromaDB)** instead of hosted LLM/vector DB  | Keeps the stack reproducible, inspectable, and free of vendor lock-in for a portfolio artifact | Weaker models and more manual ops than managed APIs             |
| **Split persistence** (Chroma + SQLite + JSON registry + filesystem) | Each store matches its concern and is easy to debug in isolation                               | No cross-store transactions; consistency is application-managed |
| **Query rewriting uses history for retrieval only**                  | Follow-ups can retrieve the right chunks without treating prior assistant text as evidence     | Heuristic follow-up detection; extra LLM call when rewriting    |
| **Final answers grounded only in retrieved context**                 | Makes hallucinations and missed retrievals visible and testable                                | Conservative refusals when retrieval misses                     |
| **CI/CD intentionally out of scope**                                 | Focus stays on the RAG pipeline; validation is local and scriptable                            | No automated gates on push/PR today                             |
| In-process upload queue                                              | Fast uploads without Redis/SQS                                                                 | Jobs need SQLite recovery on restart                            |
| Optional hybrid + reranking                                          | Simple dense baseline; advanced modes opt-in                                                   | More configuration surface                                      |
| Debug metadata in API and UI                                         | RAG failures become diagnosable in interviews and development                                  | Larger payloads and UI complexity                               |
| Per-provider Chroma collections                                      | Switching embeddings providers does not query incompatible vector spaces                       | Old collections remain until explicitly reindexed or deleted    |
| Explicit reindex (no auto-migrate)                                   | Safe, inspectable provider switches without silent data loss                                   | User must run reindex after changing embeddings provider        |

## Current Stack

### Backend

- FastAPI
- LangChain
- Ollama (default LLM + embeddings)
- ChromaDB
- SQLite
- PyPDF
- Optional: llama.cpp server, `sentence-transformers`

### Frontend

- Next.js 14
- React 18
- TypeScript
- Tailwind CSS
- Zustand

## Repository layout

| Path | Purpose |
| ---- | ------- |
| `backend/` | FastAPI app, RAG pipeline, providers, services |
| `frontend/` | Next.js UI, Evidence Workspace, Model Advisor, E2E tests |
| `scripts/` | Eval, validation, startup, reindex, model download, benchmarks |
| `tests/` | Pytest suite (API, ingestion, retrieval, providers, scripts) |
| `runtime/` | llama-server binary location, PID/log files (gitignored artifacts) |
| `models/demo/` | Demo GGUF manifest and model file (not committed) |
| `storage/` | Local uploads, registry, SQLite (gitignored user data) |
| `vector_db/` | Chroma persistence (gitignored) |

## Local Development

For a guided walkthrough, see [Demo Flow](#demo-flow) above.

### Prerequisites

- Python 3.11+
- Node.js 18+
- Ollama running locally (default path) **or** llama.cpp + local embeddings for zero-Ollama mode

Recommended Ollama models:

```bash
ollama pull llama3.1:8b
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

# LLM (default: Ollama)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.1:8b
OLLAMA_EMBED_MODEL=mxbai-embed-large

# Embeddings (default: Ollama)
EMBEDDINGS_PROVIDER=ollama

# llama.cpp (optional; used when LLM_PROVIDER=llama_cpp)
LLAMA_CPP_BASE_URL=http://localhost:11435
LLAMA_CPP_CHAT_MODEL=demo-model.gguf

# Chroma
CHROMA_PERSIST_DIRECTORY=./vector_db
CHROMA_COLLECTION_STRATEGY=per_embedding_provider
CHROMA_DEFAULT_COLLECTION=rag_chat
CHROMA_COLLECTION_PREFIX=rag

# Storage
DOCUMENTS_DIRECTORY=./storage/docs
REGISTRY_PATH=./storage/registry.json
SQLITE_PATH=./storage/app.db

# Retrieval
CHUNK_SIZE=800
CHUNK_OVERLAP=200
TOP_K=5
MAX_CONTEXT_CHUNKS=5
ENABLE_HYBRID=true
ENABLE_RERANKING=true
RERANK_TOP_M=10
RERANK_TOP_K=5
ENABLE_QUERY_REWRITING=false
QUERY_REWRITE_HISTORY_TURNS=4
ANSWER_MODE=strict_rag

# Upload
MAX_UPLOAD_BYTES=52428800
UPLOAD_READ_CHUNK_BYTES=1048576
CLEANUP_FAILED_UPLOAD_FILES=true

# Reconciliation
RECONCILE_ON_STARTUP=true
RECONCILE_REPAIR_ON_STARTUP=false
RECONCILE_ALLOW_STALE_REGISTRY_REPAIR=false

OTEL_ENABLED=false
OTEL_SERVICE_NAME=local-rag-workspace
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

### One-command startup

The workspace scripts can start Ollama mode (default) or llama.cpp mode:

```bash
./start.sh                              # Ollama default guidance
./start.sh --provider llama_cpp         # zero-Ollama chat + local_hash embeddings
./start.sh --provider llama_cpp --download-model
./start.sh --dry-run --provider llama_cpp --download-model
./stop.sh
```

```powershell
.\start.ps1
.\start.ps1 -Provider llama_cpp -DownloadModel
.\stop.ps1
```

See [Providers and embeddings](#providers-and-embeddings) and [Zero-Ollama llama.cpp setup](#zero-ollama-llamacpp-setup) below for details.

## Providers and embeddings

Defaults remain **`LLM_PROVIDER=ollama`** and **`EMBEDDINGS_PROVIDER=ollama`**. Both are fully supported and unchanged unless you opt into alternatives.

### LLM providers

| Provider | Description | Ollama required |
| -------- | ----------- | --------------- |
| `ollama` (default) | Chat, streaming, query rewrite, runtime preload/unload | Yes |
| `llama_cpp` | Local chat via OpenAI-compatible `llama-server` HTTP | No |

The backend routes chat, streaming, query rewrite, and runtime operations through an `LLMProvider` abstraction. Planned but not implemented: `embedded_llamacpp`, `openai_compatible`, `lmstudio`, `localai`.

### Embeddings providers

| Provider | Description | Ollama required |
| -------- | ----------- | --------------- |
| `ollama` (default) | High-quality semantic embeddings | Yes |
| `local_hash` | Dependency-free demo vectors (not semantically meaningful) | No |
| `sentence_transformers` | Better local semantic retrieval when installed and cached locally | No |

```env
EMBEDDINGS_PROVIDER=ollama
EMBEDDINGS_PROVIDER=local_hash
EMBEDDINGS_PROVIDER=sentence_transformers
```

For `sentence_transformers`:

```bash
pip install -r backend/requirements-embeddings.txt
python scripts/check_sentence_transformers_embeddings.py --strict
```

`SENTENCE_TRANSFORMERS_LOCAL_FILES_ONLY=true` by default — no silent model download.

### Chroma collection strategy

By default (`CHROMA_COLLECTION_STRATEGY=per_embedding_provider`), vectors are stored in provider-specific collections (e.g. `rag_local_hash_local_hash_v1_384`) so switching embeddings providers does not query a shared incompatible index.

- **`per_embedding_provider`** (default) — isolated collections per provider/model/dimension
- **`legacy_single`** — all vectors in `CHROMA_DEFAULT_COLLECTION` (`rag_chat`) for backward compatibility

Document delete removes vectors from **all** known collections. No automatic migration or reindex on provider switch.

### Reindex workflow

After changing `EMBEDDINGS_PROVIDER`, reindex registered documents into the active collection (explicit, opt-in):

```bash
# Preview plan (default)
python scripts/reindex_documents.py --dry-run

# Execute (requires confirmation)
python scripts/reindex_documents.py --run --yes

# Replace vectors in active collection only
python scripts/reindex_documents.py --run --yes --force
```

API: `POST /documents/reindex` — defaults to `dry_run=true`. Use `{"dry_run": false}` to execute.

Reindex reloads registered files, reuses existing chunking, writes to the active collection only, and preserves raw files and registry entries.

Inspect collection status via:

- `GET /models/runtime` — `embeddings.collection` and `embeddings.reindex` blocks
- `GET /health/ready` — `checks.embeddings.collection` and reindex guidance
- `GET /debug/embeddings` — full diagnostics

## Zero-Ollama llama.cpp setup

Prerequisites: `llama-server` in `runtime/bin/` (or `LLAMA_CPP_SERVER_BIN`), demo GGUF at `models/demo/model.gguf`.

**Quick start (explicit download + start):**

```bash
./start.sh --provider llama_cpp --download-model
```

**Or download first:**

```bash
python scripts/download_demo_model.py
./start.sh --provider llama_cpp
```

The start script sets process-level env for the backend child (`LLM_PROVIDER=llama_cpp`, `LLAMA_CPP_BASE_URL`, `LLAMA_CPP_CHAT_MODEL`) without rewriting `.env`. Script flags win over conflicting `.env` values for launched processes.

Zero-Ollama startup defaults to `EMBEDDINGS_PROVIDER=local_hash` unless `--embeddings sentence_transformers` is passed.

**Manual setup**

1. Place `llama-server` in `runtime/bin/`.
2. Place a GGUF model as `models/demo/model.gguf` (see `models/demo/model-manifest.json`).
3. Run `python scripts/check_llama_cpp_runtime.py` (add `--strict` to fail when files are missing).
4. Start with `./start.sh --provider llama_cpp` or run the server manually:

```bash
llama-server --model ./models/demo/model.gguf --port 11435
```

**Example zero-Ollama `.env`:**

```env
LLM_PROVIDER=llama_cpp
EMBEDDINGS_PROVIDER=local_hash
LLAMA_CPP_BASE_URL=http://localhost:11435
LLAMA_CPP_CHAT_MODEL=model.gguf
```

**Workspace scripts:**

```bash
python scripts/check_llama_cpp_runtime.py
python scripts/check_llama_cpp_runtime.py --strict
python scripts/download_demo_model.py
python scripts/reindex_documents.py --dry-run --direct
./start.sh --check-only
./start.sh --dry-run --provider llama_cpp --download-model
./stop.sh
```

Default demo model metadata points to **Qwen2.5 1.5B Instruct GGUF** (`Q4_K_M`). The backend and frontend never download models automatically; only explicit script flags do.

## API reference (local diagnostics)

| Endpoint | Purpose |
| -------- | ------- |
| `GET /health` | Process liveness |
| `GET /health/ready` | Dependency readiness (`ok`, `degraded`, or `error`) |
| `GET /debug/reconciliation` | Persistence drift report (read-only) |
| `POST /debug/reconciliation/repair` | Repair plan (dry-run by default) |
| `GET /debug/embeddings` | Embeddings/collection diagnostics and reindex guidance |
| `GET /debug/metrics` | In-process counters (resets on restart) |
| `POST /documents/reindex` | Reindex plan or run (dry-run by default) |
| `POST /models/recommendations` | Hardware-based model recommendations |
| `GET /models/catalog` | Curated local model catalog |
| `GET /models/settings` | Active chat model settings |
| `PUT /models/settings` | Set chat model (no automatic `ollama pull`) |
| `GET /models/runtime` | LLM + embeddings runtime status |
| `POST /models/runtime/preload` | Preload active chat model |
| `POST /models/runtime/unload` | Unload active model from memory |
| `GET /hardware/telemetry` | Local CPU/RAM/GPU telemetry |

Example model recommendation:

```bash
curl -X POST http://localhost:8000/models/recommendations \
  -H "Content-Type: application/json" \
  -d '{
    "gpu_vendor": "AMD",
    "gpu_model": "RX 6700 XT",
    "vram_gb": 12,
    "ram_gb": 32,
    "priority": "balanced",
    "use_cases": ["rag", "coding", "cybersecurity"]
  }'
```

### Model Advisor and runtime

The Model Advisor panel recommends local models from your hardware profile. Use **Use for chat** (or `PUT /models/settings`) to apply a model; the app never pulls or installs models automatically.

Runtime status from `/models/runtime` distinguishes **selected** vs **installed** vs **loaded** models. Preload/unload are explicit only. The header uses the backend as the single source of truth for Ollama status.

Default chat model is `llama3.1:8b` (catalog-aligned). Install models manually, e.g. `ollama pull llama3.1:8b`.

Optional Ollama runtime config: `OLLAMA_KEEP_ALIVE=5m`, `OLLAMA_PRELOAD_TIMEOUT_SECONDS=30`, `OLLAMA_TAGS_TIMEOUT_SECONDS=2`, `OLLAMA_PS_TIMEOUT_SECONDS=2`.

### Answer modes and query rewriting

`ANSWER_MODE` controls how the model uses retrieved documents:

- **`strict_rag`** (default) — answers use only retrieved document context
- **`hybrid_assistant`** — documents are highest priority; general knowledge allowed when context is insufficient

Optional multi-turn query rewriting (`ENABLE_QUERY_REWRITING=true`) rewrites the retrieval query from chat history. Final answers remain document-grounded in `strict_rag` mode.

### Hardware telemetry

The sidebar **Local hardware** panel polls `GET /hardware/telemetry` for CPU/RAM (via `psutil`) and best-effort GPU/VRAM (NVIDIA `nvidia-smi`, AMD `rocm-smi` / `amd-smi`). Disable with `HARDWARE_TELEMETRY_ENABLED=false`.

## Docker

```bash
cd docker
docker compose up --build
```

The current Docker setup still expects Ollama to be running locally and reachable from the backend container.

For Docker, set in `backend/.env`:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Use `http://localhost:11434` when running the backend directly on the host.

## Validation

Core checks from the repo root (backend venv activated):

```bash
python -m pytest
python scripts/validate_backend.py --fast
python scripts/eval.py --skip-generation --fake-embeddings --report-md tttsss/eval_report.md
cd frontend && npm run build
cd frontend && npm run test:e2e
```

| Command | What it verifies |
| ------- | ---------------- |
| `python -m pytest` | API, ingestion, retrieval, upload recovery, reindex, providers |
| `python scripts/validate_backend.py` | Pytest + offline eval + retrieval benchmark |
| `python scripts/validate_backend.py --fast` | Pytest only (faster) |
| `python scripts/eval.py --skip-generation --fake-embeddings` | Retrieval recall@k (no Ollama) |
| `python scripts/reindex_documents.py --dry-run --direct` | Reindex plan without running backend |
| `cd frontend && npm run build` | Next.js production build and TypeScript |
| `cd frontend && npm run test:e2e` | Playwright suite (Ollama + backend + frontend required) |

One-command shortcuts:

```bash
# Windows
powershell -ExecutionPolicy Bypass -File scripts/validate.ps1

# macOS/Linux
bash scripts/validate.sh
```

Live tests (opt-in, requires Ollama):

```bash
RUN_LIVE_TESTS=true python -m pytest tests/live/
```

### Eval report vs full eval

- **Fake embeddings + skip-generation** — deterministic offline validation; no Ollama required. Best for portfolio artifacts.
- **Full eval** — requires Ollama with configured embed and chat models; generation output may vary.

`tttsss/eval_report.md` is a local generated artifact and can be regenerated at any time.

### E2E prerequisites

Ollama on the host, backend on `:8000`, frontend on `http://localhost:3000`. First run: `npx playwright install chromium` from `frontend/`. Tests are **local-only** (no CI/CD): `smoke-demo`, `empty-state`, `chat-actions`, `mobile-evidence-panel`.

### Ollama and URL notes

| Runtime | Backend `OLLAMA_BASE_URL` | Frontend URL | Notes |
| ------- | ------------------------- | ------------ | ----- |
| Backend on host | `http://localhost:11434` | `http://localhost:3000` | Default local development |
| Backend in Docker | `http://host.docker.internal:11434` | `http://localhost:3000` | Ollama on the host |
| Browser access | n/a | `http://localhost:3000` | Avoid `127.0.0.1:3000` unless `CORS_ORIGINS` includes it |

## Why no CI/CD

This is a portfolio project meant to run locally and be discussed in interviews. Validation is documented and scriptable on a developer machine. Ollama, Docker, and full generation eval are environment-specific. GitHub Actions was intentionally not added so the repo stays focused on the RAG system itself. If the project graduates to a product, add CI for pytest, frontend build, and offline eval (`--fake-embeddings`).

## Limitations and Future Work

Current boundaries (intentionally visible, not hidden):

- **No authentication or multi-tenancy** — single-user local workspace only
- **No OCR or layout-aware PDF parsing** — text extraction via PyPDF only
- **Heuristic follow-up detection** for query rewriting — pattern-based, not a classifier
- **BM25 cache scoped per collection** — still rebuilt from Chroma corpus at scale
- **In-process ingestion and reindex** — not a durable external queue
- **Heuristic reranking** — not a learned cross-encoder
- **Split persistence without distributed transactions** — Chroma, SQLite, registry, filesystem
- **Small eval harness** — fixture-based, not a production benchmark suite
- **No production deployment hardening** — secrets, scaling, monitoring, and CI/CD left for a product phase

Reasonable next steps:

- larger gold eval dataset and learned reranking
- durable background jobs and richer tracing
- CI for pytest, frontend build, offline eval, and optional E2E

## Why It Works As A Portfolio Project

This repo lets me talk concretely about:

- how I separate ingestion from serving
- how I reason about chunking and retrieval quality
- how I combine lexical and semantic retrieval
- how I expose evidence and observability in the UI
- how I design provider abstractions and safe embeddings migration
- how I think about local-first trade-offs instead of hiding everything behind managed APIs

That makes it a better engineering portfolio piece than a generic AI demo because the interesting decisions are visible in both the code and the interface.
