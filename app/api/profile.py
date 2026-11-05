"""Profil pengguna (username dan avatar) dari tabel `profiles` Supabase.

Baris profil dibuat otomatis oleh trigger saat pendaftaran (lihat db/schema.sql). Avatar hanya boleh salah satu
dari pilihan bawaan frontend; avatar lain (mis. foto Google) dilaporkan sebagai `avatar_selected: false` sehingga
frontend bisa mengarahkan pengguna ke halaman pilih avatar.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core.auth import attach_user

log = logging.getLogger("profile")
router = APIRouter(prefix="/profile", tags=["profile"], dependencies=[Depends(attach_user)])

AVATARS = {"/images/FemaleAva.svg", "/images/MaleAva.svg"}
USERNAME = r"^[A-Za-z0-9_.]{3,24}$"


class ProfileOut(BaseModel):
    user_id: str
    email: str | None
    username: str | None
    avatar_url: str | None
    avatar_selected: bool  # avatar_url salah satu avatar bawaan aplikasi


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, pattern=USERNAME)
    avatar_url: str | None = Field(default=None, max_length=200)


def _default_username(email: str | None) -> str | None:
    if not email:
        return None
    base = "".join(c for c in email.split("@")[0] if c.isalnum() or c in "_.")[:24]
    return base if len(base) >= 3 else None


def _out(user, row: dict | None) -> ProfileOut:
    row = row or {}
    avatar = row.get("avatar_url")
    return ProfileOut(user_id=user.id, email=user.email, username=row.get("username") or _default_username(user.email),
                      avatar_url=avatar, avatar_selected=avatar in AVATARS)


@router.get("", response_model=ProfileOut)
async def get_profile(request: Request):
    user, repo = current_user(request), request.app.state.persister.repo
    row = None
    if repo.enabled:
        try:
            row = await run_in_threadpool(repo.get_profile, user.id)
        except Exception:
            log.exception("Gagal membaca profil %s", user.id)
            raise HTTPException(502, "Gagal membaca profil") from None
    return _out(user, row)


@router.patch("", response_model=ProfileOut)
async def update_profile(body: ProfileUpdate, request: Request):
    user, repo = current_user(request), request.app.state.persister.repo
    changes = body.model_dump(exclude_none=True)
    if "avatar_url" in changes and changes["avatar_url"] not in AVATARS:
        raise HTTPException(422, "Avatar tidak dikenal")
    if not changes:
        raise HTTPException(422, "Tidak ada perubahan")
    if not repo.enabled:
        raise HTTPException(503, "Penyimpanan profil belum dikonfigurasi")
    try:
        row = await run_in_threadpool(repo.update_profile, user.id, changes)
    except Exception as e:
        if "duplicate" in str(e).lower() or "23505" in str(e):
            raise HTTPException(409, "Username sudah dipakai") from None
        log.exception("Gagal menyimpan profil %s", user.id)
        raise HTTPException(502, "Gagal menyimpan profil") from None
    return _out(user, row)
