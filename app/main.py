from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import detect, predict, sessions, stats
from app.core.config import get_settings
from app.db.repository import Persister, build_repository
from app.services.inference import build_engine
from app.services.session_store import SessionStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.store = SessionStore()
    app.state.engine = build_engine(settings)  # model dimuat sekali saat startup
    app.state.persister = Persister(build_repository(settings))
    yield
    await app.state.persister.drain()  # selesaikan tulisan yang tertunda saat shutdown


app = FastAPI(title="Smart Study Assistant API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_origin_regex=get_settings().cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(predict.router)
app.include_router(stats.router)
app.include_router(detect.router)


@app.get("/health", tags=["meta"])
def health():
    s = get_settings()
    return {
        "status": "ok",
        "inference_backend": s.inference_backend,
        "inference": app.state.engine.info(),
        "persistence": app.state.persister.repo.enabled,
        "auth": {"enabled": bool(s.supabase_url or s.supabase_jwt_secret), "required": s.auth_required},
        "llm": {
            "enabled": bool(s.llm_api_key),
            "model": s.llm_model,
            "fallbacks": [m.strip() for m in s.llm_fallback_models.split(",") if m.strip()],
        },
    }


@app.get("/", include_in_schema=False)
def root():
    """Halaman sambutan agar membuka URL backend di browser tidak tampil 404."""
    return {"service": "Loopa Smart Study Assistant API", "status": "ok", "docs": "/docs", "health": "/health"}
