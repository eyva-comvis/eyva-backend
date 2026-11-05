"""Akun email + password lewat Supabase Auth: daftar, verifikasi email, login, refresh token.

Daftar dan login Google tetap dibuka untuk siapa saja. Login Google dilakukan frontend langsung ke Supabase
(`signInWithOAuth`); semua token hasilnya dipakai sama seperti token dari endpoint ini.

Alur daftar: POST /auth/register -> kode dikirim ke email -> POST /auth/verify-email -> token (langsung login).
Prasyarat: template email "Confirm sign up" di Supabase berisi `{{ .Token }}`.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api import auth as auth_api
from app.core.auth import SessionExpired, verify_token
from app.core.config import get_settings
from app.core.ratelimit import RateLimiter, client_ip

log = logging.getLogger("accounts")
router = APIRouter(prefix="/auth", tags=["auth"])

_login_fails = RateLimiter(max_events=8, window_seconds=600)  # per IP + email
_register_hits = RateLimiter(max_events=10, window_seconds=3600)  # per IP
_verify_fails = RateLimiter(max_events=10, window_seconds=600)  # per IP + email

EMAIL = auth_api.EMAIL_PATTERN


class RegisterIn(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL)
    password: str = Field(max_length=72)
    username: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.]{3,24}$")


class LoginIn(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL)
    password: str = Field(min_length=1, max_length=72)


class VerifyEmailIn(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL)
    code: str = Field(pattern=r"^\d{6,10}$")


class ResendIn(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=6, max_length=512)


class UserOut(BaseModel):
    id: str
    email: str | None = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    session_expires_at: datetime | None = None  # setelah ini wajib login ulang walau refresh token masih ada
    user: UserOut


class RegisterOut(BaseModel):
    requires_verification: bool
    message: str
    tokens: TokenOut | None = None


class MessageOut(BaseModel):
    message: str


def _norm(email: str) -> str:
    return email.strip().lower()


def _upstream_down(r) -> None:
    if r.status_code >= 500:
        raise HTTPException(502, "Layanan autentikasi sedang bermasalah, coba lagi")


def _tokens(data: dict) -> TokenOut:
    """Ubah respons sesi Supabase menjadi TokenOut. Gagal bila login sudah melewati batas umur login."""
    settings = get_settings()
    access = data["access_token"]
    user = data.get("user") or {}
    expires_at = None
    try:
        v = verify_token(access, settings)
        expires_at = v.session_expires_at(settings)
        user = {"id": v.id, "email": v.email}
    except SessionExpired:
        raise
    except Exception:
        log.warning("Token baru dari Supabase tidak lolos verifikasi lokal")
        raise HTTPException(502, "Token dari layanan autentikasi tidak dapat diverifikasi") from None
    return TokenOut(access_token=access, refresh_token=data.get("refresh_token", ""),
                    expires_in=int(data.get("expires_in") or 3600), session_expires_at=expires_at,
                    user=UserOut(id=str(user.get("id")), email=user.get("email")))


def _check_password(pw: str) -> None:
    n = get_settings().password_min_length
    if len(pw) < n:
        raise HTTPException(422, f"Password minimal {n} karakter")


@router.post("/register", response_model=RegisterOut, status_code=201)
async def register(body: RegisterIn, request: Request):
    """Daftar dengan email + password. Terbuka untuk siapa saja. Kode verifikasi dikirim ke email."""
    ip = client_ip(request)
    _register_hits.check(ip, "Terlalu banyak pendaftaran dari jaringan ini, coba lagi nanti")
    _check_password(body.password)
    _register_hits.hit(ip)
    payload = {"email": _norm(body.email), "password": body.password}
    if body.username:
        payload["data"] = {"username": body.username}
    r = await auth_api._call("POST", "/signup", json=payload)
    if r.status_code == 429:
        raise HTTPException(429, "Terlalu sering mendaftar, coba lagi beberapa menit lagi")
    _upstream_down(r)
    if r.status_code in (400, 422):
        code = ""
        try:
            code = str(r.json().get("error_code") or "")
        except Exception:
            pass
        if code == "weak_password":
            raise HTTPException(422, auth_api._err_text(r) or "Password terlalu lemah")
        if code in ("validation_failed", "email_address_invalid"):
            raise HTTPException(422, "Format email tidak valid")
        if code == "user_already_exists":  # bila konfirmasi email dimatikan Supabase menjawab ini
            raise HTTPException(409, "Email sudah terdaftar, silakan login")
        raise HTTPException(422, auth_api._err_text(r) or "Pendaftaran ditolak")
    if r.status_code >= 400:
        raise HTTPException(400, "Pendaftaran ditolak")
    data = r.json()
    if data.get("access_token"):  # verifikasi email dimatikan di Supabase: langsung login
        return RegisterOut(requires_verification=False, message="Pendaftaran berhasil.", tokens=_tokens(data))
    # Jawaban sama untuk email baru maupun yang sudah terdaftar agar tidak membocorkan akun yang ada.
    return RegisterOut(requires_verification=True,
                       message="Kode verifikasi dikirim ke email. Masukkan kode untuk menyelesaikan pendaftaran. Cek folder spam.")


@router.post("/verify-email", response_model=TokenOut)
async def verify_email(body: VerifyEmailIn, request: Request):
    key = f"{client_ip(request)}|{_norm(body.email)}"
    _verify_fails.check(key)
    r = await auth_api._call("POST", "/verify", json={"type": "signup", "email": _norm(body.email), "token": body.code})
    if r.status_code == 429:
        raise HTTPException(429, "Terlalu banyak percobaan, coba lagi beberapa menit lagi")
    _upstream_down(r)
    data = r.json() if r.status_code == 200 else {}
    if not data.get("access_token"):
        _verify_fails.hit(key)
        raise HTTPException(400, "Kode salah atau sudah kedaluwarsa")
    _verify_fails.reset(key)
    return _tokens(data)


@router.post("/resend-verification", response_model=MessageOut)
async def resend_verification(body: ResendIn, request: Request):
    _register_hits.check(client_ip(request), "Terlalu banyak permintaan dari jaringan ini, coba lagi nanti")
    _register_hits.hit(client_ip(request))
    r = await auth_api._call("POST", "/resend", json={"type": "signup", "email": _norm(body.email)})
    if r.status_code == 429:
        raise HTTPException(429, "Terlalu sering meminta kode, coba lagi beberapa menit lagi")
    _upstream_down(r)
    return MessageOut(message="Jika email belum terverifikasi, kode baru sudah dikirim. Cek folder spam.")


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request):
    """Login email + password. Untuk Google gunakan `signInWithOAuth` di frontend."""
    email = _norm(body.email)
    key = f"{client_ip(request)}|{email}"
    _login_fails.check(key, "Terlalu banyak percobaan login, coba lagi 10 menit lagi")
    r = await auth_api._call("POST", "/token", json={"email": email, "password": body.password},
                             params={"grant_type": "password"})
    if r.status_code == 429:
        raise HTTPException(429, "Terlalu banyak percobaan login, coba lagi beberapa menit lagi")
    _upstream_down(r)
    if r.status_code != 200:
        code = ""
        try:
            code = str(r.json().get("error_code") or "")
        except Exception:
            pass
        if code == "email_not_confirmed":
            raise HTTPException(403, "Email belum diverifikasi. Masukkan kode verifikasi atau minta kode baru.")
        _login_fails.hit(key)
        raise HTTPException(401, "Email atau password salah")
    _login_fails.reset(key)
    try:
        return _tokens(r.json())
    except SessionExpired:
        raise HTTPException(401, "Sesi login berakhir, silakan login ulang") from None


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn):
    """Tukar refresh token dengan access token baru, selama login belum melewati SESSION_MAX_HOURS."""
    r = await auth_api._call("POST", "/token", json={"refresh_token": body.refresh_token},
                             params={"grant_type": "refresh_token"})
    if r.status_code == 429:
        raise HTTPException(429, "Terlalu banyak permintaan, coba lagi sebentar lagi")
    _upstream_down(r)
    if r.status_code != 200:
        raise HTTPException(401, "Refresh token tidak valid, silakan login ulang")
    data = r.json()
    try:
        return _tokens(data)
    except SessionExpired:
        # Batas umur login terlewati: matikan sesi di Supabase agar refresh token ini tidak bisa dipakai lagi.
        await auth_api._call("POST", "/logout", token=data.get("access_token"), params={"scope": "local"})
        raise HTTPException(401, "Sesi login berakhir, silakan login ulang") from None
