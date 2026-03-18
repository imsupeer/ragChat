from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes_chat import router as chat_router
from api.routes_chats import router as chats_router
from api.routes_documents import router as documents_router
from core.config import get_settings
from core.dependencies import get_sqlite_store, get_upload_queue_service

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.1",
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


@app.on_event("startup")
def startup_event():
    get_sqlite_store()
    get_upload_queue_service()


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
