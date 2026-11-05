"""Lupa password (kode verifikasi lewat email) dan logout, memakai Supabase Auth.

Alur untuk frontend:
  1. POST /auth/forgot-password   {email}                 -> Supabase mengirim kode ke email pengguna
  2. POST /auth/verify-reset-code {email, code}           -> {reset_token}
  3. POST /auth/reset-password    {reset_token, new_password}
Setelah reset, semua sesi login akun itu dicabut; pengguna login ulang dengan password baru.
Akun yang masuk lewat Google tidak memakai alur ini.

Prasyarat di Supabase: provider Email aktif dan template email "Reset Password" berisi `{{ .Token }}` (kode angka).
"""
import logging
import time
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core.auth import attach_user, auth_configured, revoke_session, verify_token
from app.core.config import Settings, get_settings

log = logging.getLogger("auth")
router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_PATTERN = r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$"
RESET_TOKEN_MAX_AGE_SECONDS = 15 * 60  # token reset hanya sah sesaat setelah kode diverifikasi


class ForgotPasswordIn(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)


class VerifyCodeIn(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    code: str = Field(pattern=r"^\d{6,10}$")


class ResetTokenOut(BaseModel):
    reset_token: str
    expires_in: int


class ResetPasswordIn(BaseModel):
    reset_token: str = Field(min_length=20)
    new_password: str = Field(max_length=72)  # batas bcrypt di Supabase; panjang minimum dicek dari settings


class MessageOut(BaseModel):
    message: str


def _supabase(settings: Settings) -> tuple[str, str]:
    key = settings.supabase_anon_key or settings.supabase_service_key
    if not settings.supabase_url or not key:
        raise HTTPException(503, "Supabase Auth belum dikonfigurasi di server (SUPABASE_URL dan SUPABASE_ANON_KEY)")
    return f"{settings.supabase_url.rstrip('/')}/auth/v1", key


async def _call(method: str, path: str, *, json: dict | None = None, token: str | None = None,
                params: dict | None = None) -> httpx.Response:
    settings = get_settings()
    base, key = _supabase(settings)
    headers = {"apikey": key, "Authorization": f"Bearer {token or key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.request(method, f"{base}{path}", json=json, headers=headers, params=params)
    except httpx.HTTPError:
        log.exception("Gagal menghubungi Supabase Auth")
        raise HTTPException(502, "Layanan autentikasi tidak dapat dihubungi, coba lagi") from None


def _err_text(r: httpx.Response) -> str:
    try:
        b = r.json()
        return str(b.get("msg") or b.get("message") or b.get("error_description") or b.get("error") or "")
    except Exception:
        return ""


@router.post("/forgot-password", response_model=MessageOut)
async def forgot_password(body: ForgotPasswordIn):
    """Kirim kode verifikasi ke email. Jawaban selalu sama agar tidak membocorkan email mana yang terdaftar."""
    r = await _call("POST", "/recover", json={"email": body.email.strip().lower()})
    if r.status_code == 429:
        raise HTTPException(429, "Terlalu sering meminta kode, coba lagi beberapa menit lagi")
    if r.status_code >= 500:
        raise HTTPException(502, "Layanan autentikasi sedang bermasalah, coba lagi")
    if r.status_code >= 400:
        log.warning("recover ditolak (%s): %s", r.status_code, _err_text(r))
    return MessageOut(message="Jika email terdaftar, kode verifikasi sudah dikirim. Cek inbox dan folder spam.")


@router.post("/verify-reset-code", response_model=ResetTokenOut)
async def verify_reset_code(body: VerifyCodeIn):
    r = await _call("POST", "/verify", json={"type": "recovery", "email": body.email.strip().lower(), "token": body.code})
    if r.status_code == 429:
        raise HTTPException(429, "Terlalu banyak percobaan, coba lagi beberapa menit lagi")
    if r.status_code >= 500:
        raise HTTPException(502, "Layanan autentikasi sedang bermasalah, coba lagi")
    data = r.json() if r.status_code == 200 else {}
    if not data.get("access_token"):
        raise HTTPException(400, "Kode salah atau sudah kedaluwarsa")
    return ResetTokenOut(reset_token=data["access_token"], expires_in=RESET_TOKEN_MAX_AGE_SECONDS)


@router.post("/reset-password", response_model=MessageOut)
async def reset_password(body: ResetPasswordIn):
    settings = get_settings()
    if len(body.new_password) < settings.password_min_length:
        raise HTTPException(422, f"Password minimal {settings.password_min_length} karakter")
    try:
        user = verify_token(body.reset_token, settings) if auth_configured(settings) else None
    except Exception:
        user = None
    recent = user is not None and user.login_at is not None and \
        (datetime.now(timezone.utc) - user.login_at).total_seconds() <= RESET_TOKEN_MAX_AGE_SECONDS
    # Hanya token hasil verifikasi kode (metode "otp") yang boleh mengganti password tanpa password lama.
    if user is None or not recent or "otp" not in user.amr_methods:
        raise HTTPException(400, "Sesi reset tidak valid atau sudah kedaluwarsa, minta kode baru")

    r = await _call("PUT", "/user", json={"password": body.new_password}, token=body.reset_token)
    if r.status_code >= 500:
        raise HTTPException(502, "Layanan autentikasi sedang bermasalah, coba lagi")
    if r.status_code >= 400:
        detail = _err_text(r)
        if r.status_code in (401, 403):
            raise HTTPException(400, "Sesi reset tidak valid atau sudah kedaluwarsa, minta kode baru")
        raise HTTPException(422, detail or "Password ditolak")
    # Cabut semua sesi login akun ini supaya perangkat lain ikut keluar.
    await _call("POST", "/logout", token=body.reset_token, params={"scope": "global"})
    revoke_session(user.session_id, user.expires_at.timestamp() if user.expires_at else time.time() + 3600)
    return MessageOut(message="Password berhasil diubah. Silakan login dengan password baru.")


@router.post("/logout", status_code=204, dependencies=[Depends(attach_user)])
async def logout(request: Request, scope: Literal["local", "global", "others"] = Query("local")):
    """Akhiri login: sesi Supabase dicabut (refresh token mati) dan token ini langsung ditolak backend."""
    user = current_user(request)
    r = await _call("POST", "/logout", token=user.token, params={"scope": scope})
    if r.status_code >= 500:
        raise HTTPException(502, "Layanan autentikasi sedang bermasalah, coba lagi")
    if scope != "others":
        revoke_session(user.session_id, user.expires_at.timestamp() if user.expires_at else time.time() + 3600)
    return Response(status_code=204)
