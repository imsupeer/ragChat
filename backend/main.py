from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes_chat import router as chat_router
from api.routes_chats import router as chats_router
from api.routes_debug import router as debug_router
from api.routes_documents import router as documents_router
from api.routes_health import router as health_router
from core.config import get_settings
from core.dependencies import (
    get_reconciliation_service,
    get_sqlite_store,
    get_upload_queue_service,
)
from core.observability import log_structured

logger = logging.getLogger("uvicorn.error")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_sqlite_store()
    upload_queue = get_upload_queue_service()

    if settings.reconcile_on_startup and not settings.reconcile_repair_on_startup:
        try:
            reconciliation = get_reconciliation_service()
            reconciliation.run_report()
        except Exception as exc:
            logger.exception("Startup persistence reconciliation failed.")
            log_structured(
                "persistence.reconciliation.failed",
                "startup",
                {"error": str(exc), "stage": "startup"},
            )
    elif settings.reconcile_repair_on_startup:
        logger.warning(
            "RECONCILE_REPAIR_ON_STARTUP is enabled but startup repair is not supported; "
            "running report-only reconciliation."
        )
        try:
            reconciliation = get_reconciliation_service()
            reconciliation.run_report()
        except Exception as exc:
            logger.exception("Startup persistence reconciliation failed.")
            log_structured(
                "persistence.reconciliation.failed",
                "startup",
                {"error": str(exc), "stage": "startup"},
            )

    try:
        yield
    finally:
        upload_queue.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="1.0.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(chats_router)
app.include_router(debug_router)
app.include_router(health_router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
