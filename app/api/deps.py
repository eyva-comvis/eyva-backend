from fastapi import HTTPException, Request

from app.core.auth import User
from app.services.session_store import Session, SessionStore


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


def current_user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


def persist(request: Request, s: Session) -> None:
    request.app.state.persister.schedule(s)


def owns(owner_id: str | None, user: User | None) -> bool:
    """Sesi tamu (tanpa pemilik) terbuka bagi siapa pun yang tahu ID-nya; sesi milik pengguna hanya untuk pemiliknya."""
    return owner_id is None or (user is not None and user.id == owner_id)


def get_session_or_404(request: Request, session_id: str) -> Session:
    s = get_store(request).get(session_id)
    # 404 (bukan 403) agar keberadaan sesi orang lain tidak bocor.
    if s is None or not owns(s.user_id, current_user(request)):
        raise HTTPException(404, "Session tidak ditemukan")
    return s


def require_active(s: Session) -> Session:
    if s.status != "ACTIVE":
        raise HTTPException(409, "Session sudah berakhir")
    return s
