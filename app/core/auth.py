"""Autentikasi: verifikasi JWT Supabase (Sign in with Google atau email + password). Login wajib, tidak ada mode tamu.

- Token dikirim frontend sebagai `Authorization: Bearer <access_token>`.
- Proyek Supabase baru memakai kunci asimetris (ES256/RS256) -> kunci publik diambil dari JWKS
  `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`. Proyek lama memakai HS256 -> isi SUPABASE_JWT_SECRET.
- Umur login dibatasi: bila waktu login terakhir (klaim `amr[].timestamp`) lebih lama dari SESSION_MAX_HOURS,
  token ditolak walau access token-nya masih berlaku, sehingga pengguna tidak login selamanya lewat refresh token.
- Logout mencabut sesi di Supabase dan memasukkan `session_id` ke daftar cabut lokal sampai token kedaluwarsa.
- Bila SUPABASE_URL dan SUPABASE_JWT_SECRET kosong, semua endpoint terproteksi menjawab 503.
"""
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from jwt import PyJWKClient

from app.core.config import Settings, get_settings

_ALLOWED_ALGS = {"HS256", "RS256", "ES256"}  # "none" dan lainnya ditolak
_jwks_clients: dict[str, PyJWKClient] = {}

_revoked: dict[str, float] = {}  # session_id -> exp token terakhir (detik epoch)
_revoked_lock = threading.Lock()


@dataclass(frozen=True)
class User:
    id: str
    email: str | None = None
    session_id: str | None = None
    login_at: datetime | None = None  # waktu autentikasi terakhir pada sesi ini
    amr_methods: tuple[str, ...] = ()
    expires_at: datetime | None = None  # access token berakhir
    token: str = ""

    def session_expires_at(self, settings: Settings) -> datetime | None:
        """Batas akhir login (login_at + SESSION_MAX_HOURS); None bila tidak dapat dihitung atau dinonaktifkan."""
        if self.login_at is None or settings.session_max_hours <= 0:
            return None
        return datetime.fromtimestamp(self.login_at.timestamp() + settings.session_max_hours * 3600, tz=timezone.utc)


class SessionExpired(Exception):
    pass


def auth_configured(settings: Settings) -> bool:
    return bool(settings.supabase_url or settings.supabase_jwt_secret)


def revoke_session(session_id: str | None, exp: float) -> None:
    if not session_id:
        return
    now = time.time()
    with _revoked_lock:
        for k in [k for k, v in _revoked.items() if v < now]:  # buang yang token-nya sudah pasti mati
            del _revoked[k]
        _revoked[session_id] = exp


def _is_revoked(session_id: str | None) -> bool:
    if not session_id:
        return False
    with _revoked_lock:
        exp = _revoked.get(session_id)
    return exp is not None and exp >= time.time()


def verify_token(token: str, settings: Settings) -> User:
    alg = jwt.get_unverified_header(token).get("alg")
    if alg not in _ALLOWED_ALGS:
        raise jwt.InvalidAlgorithmError(f"algoritma tidak diizinkan: {alg}")
    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidTokenError("SUPABASE_JWT_SECRET belum diisi untuk token HS256")
        key = settings.supabase_jwt_secret
    else:
        if not settings.supabase_url:
            raise jwt.InvalidTokenError("SUPABASE_URL belum diisi untuk memverifikasi token asimetris")
        url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        client = _jwks_clients.setdefault(url, PyJWKClient(url, cache_keys=True))
        key = client.get_signing_key_from_jwt(token).key
    claims = jwt.decode(token, key, algorithms=[alg], audience=settings.supabase_jwt_audience,
                        options={"require": ["exp", "sub"]})

    amr = [a for a in (claims.get("amr") or []) if isinstance(a, dict)]
    stamps = [a["timestamp"] for a in amr if isinstance(a.get("timestamp"), (int, float))]
    login_at = datetime.fromtimestamp(max(stamps), tz=timezone.utc) if stamps else None
    user = User(
        id=str(claims["sub"]), email=claims.get("email"), session_id=claims.get("session_id"), login_at=login_at,
        amr_methods=tuple(str(a.get("method")) for a in amr),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc), token=token,
    )
    if _is_revoked(user.session_id):
        raise SessionExpired("Sesi sudah logout")
    limit = user.session_expires_at(settings)
    if limit is not None and limit <= datetime.now(timezone.utc):
        raise SessionExpired("Sesi login berakhir")
    return user


async def get_user(request: Request) -> User:
    settings = get_settings()
    if not auth_configured(settings):
        raise HTTPException(503, "Autentikasi belum dikonfigurasi di server")
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer ") or not header[7:].strip():
        raise HTTPException(401, "Perlu login", headers={"WWW-Authenticate": "Bearer"})
    try:
        return await run_in_threadpool(verify_token, header[7:].strip(), settings)
    except SessionExpired:
        raise HTTPException(401, "Sesi login berakhir, silakan login ulang", headers={"WWW-Authenticate": "Bearer"}) from None
    except Exception:
        raise HTTPException(401, "Token tidak valid atau kedaluwarsa", headers={"WWW-Authenticate": "Bearer"}) from None


async def attach_user(request: Request) -> None:
    """Dependency router: wajib login; simpan pengguna di request.state agar helper sinkron bisa memakainya."""
    request.state.user = await get_user(request)
