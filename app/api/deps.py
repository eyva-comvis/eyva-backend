import asyncio
import logging

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.core.auth import User
from app.core.config import get_settings
from app.services.rehydrate import session_from_rows
from app.services.session_store import Session, SessionStore

log = logging.getLogger("deps")


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


def current_user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


def persist(request: Request, s: Session) -> None:
    request.app.state.persister.schedule(s)


def owns(owner_id: str | None, user: User | None) -> bool:
    """Sesi tamu (tanpa pemilik) terbuka bagi siapa pun yang tahu ID-nya; sesi milik pengguna hanya untuk pemiliknya."""
    return owner_id is None or (user is not None and user.id == owner_id)


_load_lock = asyncio.Lock()


async def get_session_or_404(request: Request, session_id: str) -> Session:
    """Sesi dari memori; bila tidak ada (server baru restart/redeploy), dimuat ulang dari database."""
    store = get_store(request)
    s = store.get(session_id)
    if s is None:
        repo = request.app.state.persister.repo
        if repo.enabled:
            async with _load_lock:  # cegah dua request memuat sesi yang sama menjadi dua objek
                s = store.get(session_id)
                if s is None:
                    try:
                        data = await run_in_threadpool(repo.get_session_rows, session_id)
                    except Exception:
                        log.exception("Gagal memuat sesi %s dari database", session_id)
                        data = None
                    if data is not None and owns(data["session"].get("user_id"), current_user(request)):
                        s = session_from_rows(data, get_settings())
                        store.add(s)
    # 404 (bukan 403) agar keberadaan sesi orang lain tidak bocor.
    if s is None or not owns(s.user_id, current_user(request)):
        raise HTTPException(404, "Session tidak ditemukan")
    return s


def require_active(s: Session) -> Session:
    if s.status != "ACTIVE":
        raise HTTPException(409, "Session sudah berakhir")
    return s
