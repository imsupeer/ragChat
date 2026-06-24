# Engineering Notes

Concise reference for how this portfolio project is structured, what was hardened during the implementation batches, and what is intentionally out of scope.

## Local-first RAG architecture

This repo is a single-user, local RAG workspace — not a hosted SaaS.

- **Backend:** FastAPI orchestrates ingestion, retrieval, reranking, prompt assembly, and Ollama generation.
- **Frontend:** Next.js streams answers, shows source attribution, and exposes debug evidence in the InsightPanel.
- **Persistence split:** ChromaDB (vectors), SQLite (chats/messages/jobs), JSON registry (document metadata), filesystem (raw uploads).
- **External runtime:** Ollama on the host for chat and embeddings. Docker backend reaches it via `host.docker.internal`.

Design goal: make pipeline stages inspectable instead of hiding them behind a generic chat UI.

## Batch 1 — Eval integrity

**Problem:** Eval fixtures and harness drifted from live behavior (stale docs, wrong refusal phrase, hybrid/rerank ignored).

**Outcome:**
- Fixture docs and `dataset.json` aligned with current retrieval/prompt behavior.
- `scripts/eval.py` reads hybrid/rerank settings from backend config and supports CLI overrides.
- Eval report includes active configuration.

**Validate:** `python scripts/eval.py --skip-generation --fake-embeddings` or full eval with Ollama.

## Batch 2 — Upload reliability

**Problem:** In-process upload queue lost work on restart; partial indexing could leave orphan vectors.

**Outcome:**
- Startup recovery re-enqueues `queued` / `processing` jobs from SQLite.
- Failed registry writes trigger Chroma rollback.
- Retry API and frontend retry/stall handling for recoverable jobs.

**Validate:** `python -m pytest tests/services/test_upload_queue.py`

## Batch 3 — SSE and chat state

**Problem:** Stream failures left bad UI/SQLite state; regenerate duplicated user messages.

**Outcome:**
- Structured SSE `{ type: "error", message, code, recoverable }`.
- User message persisted after successful `prepare()`, not before generation.
- Regenerate replaces the paired assistant answer in place.
- Stream lifecycle guarded by `chatId` / `assistantId`; cancel and chat-switch cleanup.

**Validate:** `python -m pytest tests/api/test_chat_api.py`

## Batch 4 — Observability persistence

**Problem:** Debug metadata existed only for the current browser session.

**Outcome:**
- SQLite `debug_json` on assistant messages (auto-migrated).
- `/chat`, `/chat/stream`, and regenerate persist debug payloads.
- InsightPanel separates **Used in Prompt**, **Reranked Candidates**, and **Retrieved Candidates**.
- Score labels clarify distance vs BM25 vs RRF vs rerank semantics.

**Validate:** `python -m pytest tests/services/test_sqlite_store.py tests/api/test_chats_api.py`

## Batch 5 — Local quality gates

**Problem:** Validation required tribal knowledge; eval indexing needed Ollama even for retrieval-only checks.

**Outcome:**
- Root `requirements-dev.txt` and `pytest.ini` (`pythonpath = backend`).
- `scripts/validate.ps1` / `scripts/validate.sh` for one-command local checks.
- `scripts/eval.py --fake-embeddings` for offline retrieval eval.
- README documents host vs Docker Ollama URLs and browser CORS (`localhost`, not `127.0.0.1`).

**Validate:**

```bash
powershell -ExecutionPolicy Bypass -File scripts/validate.ps1
```

## Batch 6 — Cleanup and portfolio polish

**Outcome:**
- Removed unused `InMemoryChatHistory` (SQLite is the chat source of truth).
- Removed duplicate `frontend/next.config.js` (kept `next.config.mjs`).
- Removed unused sync `sendChatMessage` helper from the frontend.
- Trimmed prompt module docstrings; behavior unchanged.
- This document and audit status updates in `tttsss/`.

## Batch 7 — Local Playwright smoke demo

**Goal:** One local E2E test for the portfolio demo flow without CI/CD.

**Outcome:**
- `@playwright/test` in `frontend/` with `playwright.config.ts` and `e2e/smoke-demo.spec.ts`.
- Minimal `data-testid` hooks on upload, chat, document list, and InsightPanel.
- `npm run test:e2e` documented in README (manual prerequisites: Ollama, backend, frontend).

**Validate:**

```bash
cd frontend && npm ci && npx playwright install chromium && npm run test:e2e
```

## Batch 8 — Multi-turn query rewriting

**Goal:** Optional follow-up support for retrieval without treating chat history as answer evidence.

**Outcome:**
- `ENABLE_QUERY_REWRITING=false` by default with `QUERY_REWRITE_HISTORY_TURNS` and `QUERY_REWRITE_MODEL`.
- History loads from SQLite when `chat_id` is present; ambiguous follow-ups rewrite into standalone retrieval queries via local Ollama.
- Retrieval and reranking use the rewritten query; the final RAG prompt still uses the original user question and retrieved document context only.
- Debug metadata and InsightPanel expose rewrite details.
- Eval dataset includes two follow-up examples with explicit `retrieval_question` for offline harness checks.

**Validate:**

```bash
python -m pytest tests/services/test_query_rewriter.py tests/services/test_chat_service_query_rewrite.py
python scripts/eval.py --skip-generation --fake-embeddings
```

## Batch 9 — Portfolio README and demo narrative

**Goal:** Make the public-facing story clear for recruiters, tech leads, and interview walkthroughs.

**Outcome:**
- README restructured with **Project Summary**, **Engineering Highlights**, **Demo Flow**, **Key Design Decisions**, **Validation**, and **Limitations and Future Work**.
- Architecture diagram updated for query rewriting and persisted debug.
- Narrative aligned with Batches 1–8 (no code or behavior changes).

**Validate:** Read [`README.md`](../README.md) and follow [Demo Flow](../README.md#demo-flow).

## Batch UP — Answer modes (strict RAG vs hybrid assistant)

**Goal:** Optional answer behavior while preserving strict document-grounded RAG as the default.

**Outcome:**
- `ANSWER_MODE=strict_rag` (default) keeps existing strict grounding, refusal phrase, and output format unchanged.
- `ANSWER_MODE=hybrid_assistant` allows general model knowledge when documents are missing, incomplete, or irrelevant, with mandatory **Document Evidence** / **General Knowledge Used** separation.
- Document-specific follow-ups (“according to the uploaded file”) remain strict in hybrid mode.
- `ChatService` and prompt debug metadata expose `prompt.answer_mode`; InsightPanel shows the active mode.

**Validate:**

```bash
python -m pytest tests/prompts/test_rag_prompt.py tests/services/test_chat_service_answer_mode.py
python -m pytest
python scripts/eval.py --skip-generation --fake-embeddings
```

## Batch B0.1 — Stream failure debug persistence

**Goal:** Keep retrieval/prompt debug inspectable after reload when `/chat/stream` generation fails.

**Outcome:**
- Stream error path persists `prepared["debug"]` plus `generation.status: "failed"` on assistant messages.
- Sources from successful `prepare()` are kept even when no tokens were streamed.
- SSE `{ type: "error", code, message, recoverable }` contract unchanged; safe error messages avoid path leakage.

**Validate:**

```bash
python -m pytest tests/api/test_chat_api.py
```

## Batch B1 — Persistence and SQLite Reliability

**Goal:** Harden SQLite concurrency, registry durability, compensating document delete, and upload job consistency.

**Outcome:**
- SQLite connections use `foreign_keys`, `busy_timeout=5000`, WAL, and `synchronous=NORMAL`.
- Hot-path indexes on `messages(chat_id, created_at)` and `upload_jobs(status, created_at)`, `upload_jobs(document_id)`.
- `registry.json` writes use temp file + `os.replace` with in-process lock.
- `DocumentDeleteService` deletes Chroma → file → registry; partial failures keep registry and return safe 500 messages.
- Successful deletes clear `upload_jobs.document_id` references.

**Validate:**

```bash
python -m pytest tests/services/test_sqlite_store.py tests/services/test_document_registry.py tests/services/test_document_delete.py tests/api/test_documents_api.py
```

## Batch B2 — Retrieval Performance

**Goal:** Eliminate per-query BM25 rebuild and add a local retrieval benchmark.

**Outcome:**
- In-memory lexical cache: corpus loaded once per revision; BM25 indexes cached per scope key (`all` or sorted `document_ids`).
- Cache invalidates on `add_documents` and `delete_document`.
- `scripts/benchmark_retrieval.py` for repeated retrieval latency with `--fake-embeddings`.

**Validate:**

```bash
python -m pytest tests/retrieval/
python scripts/benchmark_retrieval.py --fake-embeddings --from-eval --repeat 5
```

## Batch B3 — Streaming and Async Hardening

**Goal:** Harden SSE disconnect handling, upload queue shutdown, and FastAPI lifespan without changing RAG semantics.

**Outcome:**
- `/chat/stream` checks `request.is_disconnected()` before generation and inside the token loop; Ollama iteration stops on disconnect.
- Disconnect policy: no `done`/`error` after disconnect; partial answers persist with `generation.status: "client_disconnected"`; empty cancelled assistant when user was persisted but no tokens streamed.
- Success path sets `generation.status: "completed"`; B0.1 failure path unchanged.
- SQLite persistence in the stream generator uses `asyncio.to_thread`.
- `UploadQueueService.shutdown()` stops the worker, resets interrupted `processing` jobs to `queued`, and clears active job tracking.
- `main.py` uses FastAPI `lifespan` (startup recovery + shutdown hook); deprecated `on_event` removed.

**Validate:**

```bash
python -m pytest tests/api/test_chat_api.py tests/api/test_main_lifespan.py tests/services/test_upload_queue.py
```

## Batch B4 — Upload/Ingestion Robustness

**Goal:** Safer uploads and indexing without changing RAG semantics.

**Outcome:**
- `MAX_UPLOAD_BYTES` (default 50 MB) and `UPLOAD_READ_CHUNK_BYTES` (default 1 MB) settings in `core/config.py`.
- `/documents/upload` streams chunked writes via `stream_upload_to_disk()`; oversized uploads return HTTP 413 and remove partial files.
- Permanent indexing failures (empty/unparseable content) delete raw files when `CLEANUP_FAILED_UPLOAD_FILES=true` (default); recoverable failures (e.g. registry write) keep files for retry.
- Text loaders try `utf-8`, `utf-8-sig`, then `latin-1`; `encoding` recorded in document metadata.
- Shared `safe_ingestion_error_message()` avoids path leakage in API/job errors.

**Optional env:**

```env
MAX_UPLOAD_BYTES=52428800
UPLOAD_READ_CHUNK_BYTES=1048576
CLEANUP_FAILED_UPLOAD_FILES=true
```

**Validate:**

```bash
python -m pytest tests/api/test_documents_api.py tests/services/test_upload_queue.py tests/ingestion/
```

## Batch B6 — Persistence Reconciliation

**Goal:** Detect drift across registry, Chroma, filesystem uploads, and SQLite upload jobs without destructive repair.

**Outcome:**
- `PersistenceReconciliationService` produces a structured JSON report with issue types, severity, and suggested actions.
- Drift cases: `registry_missing_file`, `registry_missing_vectors`, `orphan_chroma_vectors`, `orphan_file`, `upload_job_missing_document`, `upload_job_missing_file`.
- `ChromaService.list_document_ids_with_vector_counts()` for read-only vector inspection (no BM25 cache invalidation).
- Startup runs report-only reconciliation when `RECONCILE_ON_STARTUP=true` (default); never mutates state.
- `GET /debug/reconciliation` returns the report for local inspection.

**Optional env:**

```env
RECONCILE_ON_STARTUP=true
RECONCILE_REPAIR_ON_STARTUP=false
```

**Validate:**

```bash
python -m pytest tests/services/test_reconciliation.py tests/api/test_debug_api.py tests/api/test_main_lifespan.py
```

## Batch B6.1 — Safe Reconciliation Repair

**Goal:** Generate a repair plan from reconciliation findings and apply only safe, explicit repairs (dry-run by default).

**Outcome:**
- `build_repair_plan()` / `run_repair(dry_run=True)` derive actions from the reconciliation report.
- Safe apply actions: clear stale `upload_jobs.document_id`; mark missing-file jobs failed with a safe message.
- Manual review only: `orphan_chroma_vectors`, `orphan_file`, registry drift when file or vectors still exist.
- Optional medium action (opt-in): `remove_stale_registry_entry` when file missing and zero Chroma vectors (`include_stale_registry_cleanup` + `RECONCILE_ALLOW_STALE_REGISTRY_REPAIR=true`).
- `POST /debug/reconciliation/repair` — default `dry_run: true`; no startup repair (`RECONCILE_REPAIR_ON_STARTUP=false`).
- Metrics: `reconciliation.repair.plan`, `.applied`, `.failed`, `.manual_review`; structured logs for plan/apply.

**Optional env:**

```env
RECONCILE_ALLOW_STALE_REGISTRY_REPAIR=false
```

**Validate:**

```bash
python -m pytest tests/services/test_reconciliation.py tests/api/test_debug_api.py tests/services/test_sqlite_store.py
```

## Batch B5 — Observability, Readiness and Safer Error Surfaces

**Goal:** Safer API errors, local metrics, dependency readiness, and debug metadata path redaction without changing RAG semantics.

**Outcome:**
- Centralized `redact_local_paths()`, `safe_error_message()`, and domain-specific safe error helpers; `log_api_exception()` keeps full details in server logs.
- Chat/upload routes no longer return raw `str(exc)` to clients.
- Debug metadata strips `file_path` / `stored_path` via `clean_metadata()`.
- In-process `LocalMetrics` with counters for chat streams, uploads, indexing, retrieval, reconciliation, and lexical cache hits/misses.
- `GET /debug/metrics` returns uptime, counters, and last-value stats (no prompts/paths).
- `GET /health` remains simple liveness; `GET /health/ready` checks SQLite, Chroma, upload queue worker, reconciliation last status, and Ollama (degraded if unavailable).
- OpenTelemetry deferred; config placeholders `OTEL_ENABLED=false`, `OTEL_SERVICE_NAME=local-rag-workspace`.

**Validate:**

```bash
python -m pytest tests/api/test_debug_api.py tests/api/test_health_api.py tests/retrieval/test_observability.py tests/services/test_metrics.py
```

## Batch B7 — Backend DX and Testability

**Goal:** Improve test isolation, cache reset, live-test opt-in, and local backend validation without changing product behavior.

**Outcome:**
- `clear_dependency_caches()` in `core/dependencies.py` resets `@lru_cache` getters, settings, and in-process metrics.
- `reset_local_metrics()` in `services/metrics.py` for deterministic metrics tests.
- Expanded `tests/conftest.py`: autouse cache reset, `test_settings`, `temp_workspace`, `metrics_snapshot_reset`, live marker registration.
- Shared helpers in `tests/helpers/` (`fakes.py`, `fastapi_app.py`).
- Live harness opt-in via `@pytest.mark.live` + `RUN_LIVE_TESTS=true` (`tests/live/`).
- `scripts/validate_backend.py` runs pytest (excluding live), eval, benchmark; flags `--fast`, `--skip-eval`, `--skip-benchmark`, `--include-live`.

**Default validation:**

```bash
python scripts/validate_backend.py
```

**Live tests (manual):**

```bash
RUN_LIVE_TESTS=true python -m pytest tests/live/
```

## Backend optimization track (complete)

Batches B0–B7 and B6.1 hardened persistence, retrieval cache, streaming lifecycle, uploads, reconciliation/repair, observability, and testability. Full narrative: [`tttsss/backend_track_summary.md`](../tttsss/backend_track_summary.md).

**Validate:**

```bash
python scripts/validate_backend.py
```

## Batch 10 — Evaluation report export

**Goal:** Produce a reviewer-friendly Markdown eval report as a portfolio artifact.

**Outcome:**
- `scripts/eval.py --report-md <path>` writes a Markdown report while preserving existing console and JSON output.
- Report sections: Summary, Active Configuration, Dataset Overview, Per-example Results, Failed Cases, Notes.
- Includes answer mode, query rewriting, fake embeddings status, and per-example chunk IDs.
- Works offline with `--skip-generation --fake-embeddings`; parent directories are created automatically.

**Validate:**

```bash
python -m pytest tests/scripts/test_eval_markdown_report.py
python scripts/eval.py --skip-generation --fake-embeddings --report-md tttsss/eval_report.md
```

**Validate:** `npm run build`; manual retrieval scope and upload queue walkthrough.

## Batch UI-2 — Document selection and upload UX

**Goal:** Make retrieval scope, upload queue lifecycle, and service health visible in the main workspace.

**Outcome:**
- Header **retrieval scope badge** (all docs vs scoped vs none indexed) plus optional last-answer source count.
- Completed upload queue items auto-dismiss after 5 seconds; failed/recoverable jobs stay visible.
- Raw job IDs hidden behind expandable technical details.
- Backend/Ollama status polls every 30s with manual refresh button.

**Validate:**

```bash
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Batch UI-8 — Local E2E UX coverage

**Goal:** Small local Playwright suite covering UI-1–UI-7 flows without CI/CD.

**Outcome:**
- Shared helpers in `frontend/e2e/helpers/demoFlow.ts`.
- Specs: `smoke-demo`, `empty-state`, `chat-actions`, `mobile-evidence-panel`.
- Scripts: `test:e2e`, `test:e2e:headed`, `test:e2e:ui` (local only).

**Prerequisites:** Backend `:8000`, frontend `:3000`, Ollama with models pulled.

**Validate:**

```bash
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Batch UI-7 — Visual system polish

**Goal:** Consistent labels/badges, reduced first-look technical noise, clearer selected message state.

**Outcome:**
- Shared `.app-label` and `.app-badge*` utilities in `globals.css`.
- `debugMode` defaults to `false` for fresh sessions; toggles renamed to “Show technical metadata”.
- Selected assistant messages show left accent, chip, and clearer panel linkage.
- Inspect action uses `SearchCheck` (distinct from metadata `Braces` icon).

**Validate:**

```bash
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Batch UI-6 — Mobile evidence panel UX

**Goal:** Single responsive evidence panel; clearer open/close affordances and touch-friendly controls below `xl`.

**Outcome:**
- One `InsightPanel` instance via `EvidencePanelShell` (inline at `xl+`, fixed drawer below).
- Mobile drawer: backdrop dismiss, Escape close, body scroll lock, focus to close button.
- Header mobile CTA when sources available; panel starts closed below `xl`.
- E2E no longer needs `.first()` for panel selectors; tablet viewport check added.

**Validate:**

```bash
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Batch UI-5 — Accessibility and keyboard navigation

**Goal:** Baseline accessibility polish — ARIA labels, landmarks, focus rings, error announcements, keyboard-friendly upload, reduced motion.

**Outcome:**
- Icon-only controls have accessible names; panel/debug toggles expose expanded/pressed state.
- Sidebar, chat, and evidence panel regions labeled; stream errors use `role="alert"` and link to composer.
- Shared `focus-ring` utility; upload dropzone is keyboard-operable via react-dropzone div root.
- Streaming bounce animation respects `prefers-reduced-motion`.

**Validate:**

```bash
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Batch UI-4 — InsightPanel information architecture

**Goal:** Progressive disclosure for evidence/debug; reviewer-friendly summary without removing technical data.

**Outcome:**
- Reviewer summary at top of panel (answer mode, query rewriting, sources, chunks, latency).
- Sources tab uses compact evidence summary instead of full answer duplication.
- Debug tab sections collapsible: Used in Prompt open by default; retrieved/reranked candidates collapsed.
- Plain-language answer mode and score helper text; distinct Pipeline Debug vs Metadata toggle icons.

**Validate:**

```bash
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Batch UI-3 — Chat streaming and response polish

**Goal:** Improve chat discoverability, scroll behavior, destructive-action safety, and stream control.

**Outcome:**
- Message actions always visible; Inspect emphasized with test IDs.
- Copy success announced via `aria-live`.
- Smart auto-scroll with Jump to latest when scrolled up.
- Inline delete confirmation for chats and documents.
- Confirm before switching chats during active generation.
- Source preview links to `+N more` in Evidence panel.

**Validate:**

```bash
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Batch UI-1 — Demo clarity and empty states

**Goal:** Guide first-time users through upload → index → ask → inspect within 30–60 seconds.

**Outcome:**
- Contextual `ChatEmptyState`: upload guidance when no docs, starter prompts when indexed, indexing-in-progress hint from upload queue.
- `ChatStageIndicator` idle copy reflects document readiness.
- Chat session list shows helper text when no chats exist.
- Page title set to **Local RAG Workspace**.

**Validate:**

```bash
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Why CI/CD is out of scope

This is a portfolio project meant to run locally and be discussed in interviews.

- Validation is documented and scriptable on a developer machine.
- Ollama and Docker compose are environment-specific; full generation eval is manual.
- GitHub Actions was intentionally not added to keep the repo focused on the RAG system itself.

If the project graduates from portfolio to product, add CI for pytest, frontend build, and offline eval (`--skip-generation --fake-embeddings`).

## Remaining known limitations

See README **Limitations**. Highest-impact open items from the original audit are largely addressed by the backend optimization track (see `tttsss/backend_track_summary.md`). Remaining optional gaps:

- OCR / layout-aware PDF ingestion
- Orphan Chroma vectors and orphan files (manual review via reconciliation)
- Query rewriting is heuristic + optional; not long-term memory
- Split persistence without distributed transactions
- Single smoke E2E only (no full browser matrix or CI wiring)

## Quick validation

```bash
pip install -r requirements-dev.txt
python -m pytest
cd frontend && npm ci && npm run build
python scripts/eval.py --skip-generation --fake-embeddings
```
