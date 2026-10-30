"""Autentikasi: verifikasi JWT Supabase (Sign in with Google atau email).

- Token dikirim frontend sebagai `Authorization: Bearer <access_token>`.
- Proyek Supabase baru memakai kunci asimetris (ES256/RS256) -> kunci publik diambil dari JWKS
  `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`. Proyek lama memakai HS256 -> isi SUPABASE_JWT_SECRET.
- AUTH_REQUIRED=false (default): tanpa token = mode tamu (sesi tanpa pemilik). Dengan token valid sesi dimiliki pengguna.
- Bila SUPABASE_URL dan SUPABASE_JWT_SECRET sama-sama kosong, auth dianggap tidak dikonfigurasi dan token diabaikan.
"""
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from jwt import PyJWKClient

from app.core.config import Settings, get_settings

_ALLOWED_ALGS = {"HS256", "RS256", "ES256"}  # "none" dan lainnya ditolak
_jwks_clients: dict[str, PyJWKClient] = {}


@dataclass(frozen=True)
class User:
    id: str
    email: str | None = None


def auth_configured(settings: Settings) -> bool:
    return bool(settings.supabase_url or settings.supabase_jwt_secret)


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
    return User(id=str(claims["sub"]), email=claims.get("email"))


async def get_user(request: Request) -> User | None:
    settings = get_settings()
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer ") and auth_configured(settings):
        try:
            return await run_in_threadpool(verify_token, header[7:].strip(), settings)
        except Exception:
            raise HTTPException(401, "Token tidak valid atau kedaluwarsa") from None
    if settings.auth_required:
        raise HTTPException(401, "Perlu login")
    return None


async def attach_user(request: Request) -> None:
    """Dependency router: simpan pengguna saat ini di request.state agar helper sinkron bisa memakainya."""
    request.state.user = await get_user(request)
