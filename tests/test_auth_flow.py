"""Tes alur lupa password (verifikasi kode lewat email) dan logout. Supabase Auth dipalsukan."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.core import auth as core_auth
from app.core.config import get_settings
from app.main import app
from tests.conftest import SECRET, make_token

ANON = {"Authorization": ""}


class FakeSupabase:
    def __init__(self):
        self.calls: list[tuple] = []
        self.verify_ok = True
        self.update_status = 200
        self.recover_status = 200

    async def __call__(self, method, path, *, json=None, token=None, params=None):
        self.calls.append((method, path, json, token, params))
        req = httpx.Request(method, "http://supabase.test" + path)
        if path == "/recover":
            return httpx.Response(self.recover_status, json={}, request=req)
        if path == "/verify":
            if not self.verify_ok:
                return httpx.Response(403, json={"msg": "Token has expired or is invalid"}, request=req)
            return httpx.Response(200, json={"access_token": make_token("reset-user", login_ago=5, methods=("otp",), session_id="sess-r")},
                                  request=req)
        if path == "/user":
            return httpx.Response(self.update_status, json={"msg": "weak"} if self.update_status >= 400 else {}, request=req)
        return httpx.Response(204, request=req)  # /logout


@pytest.fixture
def env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "supabase_jwt_secret", SECRET)
    fake = FakeSupabase()
    monkeypatch.setattr(auth_api, "_call", fake)
    core_auth._revoked.clear()
    with TestClient(app) as c:
        yield c, fake


def test_forgot_password_is_public_and_generic(env):
    c, fake = env
    r = c.post("/auth/forgot-password", json={"email": " User@Example.com "}, headers=ANON)
    assert r.status_code == 200 and "kode verifikasi" in r.json()["message"]
    assert fake.calls[0][:3] == ("POST", "/recover", {"email": "user@example.com"})
    fake.recover_status = 400  # email tidak terdaftar: jawaban tetap sama
    assert c.post("/auth/forgot-password", json={"email": "ghost@example.com"}, headers=ANON).status_code == 200
    fake.recover_status = 429
    assert c.post("/auth/forgot-password", json={"email": "a@b.co"}, headers=ANON).status_code == 429
    assert c.post("/auth/forgot-password", json={"email": "bukan-email"}, headers=ANON).status_code == 422


def test_verify_code_returns_reset_token_or_400(env):
    c, fake = env
    r = c.post("/auth/verify-reset-code", json={"email": "a@b.co", "code": "123456"}, headers=ANON)
    assert r.status_code == 200 and r.json()["reset_token"]
    assert fake.calls[0][2] == {"type": "recovery", "email": "a@b.co", "token": "123456"}
    fake.verify_ok = False
    assert c.post("/auth/verify-reset-code", json={"email": "a@b.co", "code": "000000"}, headers=ANON).status_code == 400
    assert c.post("/auth/verify-reset-code", json={"email": "a@b.co", "code": "12ab"}, headers=ANON).status_code == 422


def test_full_reset_flow_changes_password_and_revokes_sessions(env):
    c, fake = env
    tok = c.post("/auth/verify-reset-code", json={"email": "a@b.co", "code": "123456"}, headers=ANON).json()["reset_token"]
    r = c.post("/auth/reset-password", json={"reset_token": tok, "new_password": "PasswordBaru123"}, headers=ANON)
    assert r.status_code == 200 and "berhasil" in r.json()["message"]
    paths = [(m, p, params) for m, p, _j, _t, params in fake.calls]
    assert ("PUT", "/user", None) in paths and ("POST", "/logout", {"scope": "global"}) in paths
    # token reset tidak bisa dipakai lagi
    assert c.get("/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_reset_password_rejects_short_password_and_non_recovery_tokens(env):
    c, fake = env
    good = make_token("u", login_ago=5, methods=("otp",))
    assert c.post("/auth/reset-password", json={"reset_token": good, "new_password": "short"}, headers=ANON).status_code == 422
    for bad in (make_token("u"),  # token login biasa tanpa klaim amr
                make_token("u", login_ago=5, methods=("password",)),  # login password, bukan verifikasi kode
                make_token("u", login_ago=3600, methods=("otp",)),  # kode sudah lama diverifikasi
                "x" * 40):
        r = c.post("/auth/reset-password", json={"reset_token": bad, "new_password": "PasswordBaru123"}, headers=ANON)
        assert r.status_code == 400, bad
    assert not any(p == "/user" for _m, p, *_ in fake.calls)


def test_reset_password_surfaces_supabase_rejection(env):
    c, fake = env
    fake.update_status = 422
    tok = make_token("u", login_ago=5, methods=("otp",))
    r = c.post("/auth/reset-password", json={"reset_token": tok, "new_password": "PasswordBaru123"}, headers=ANON)
    assert r.status_code == 422


def test_logout_revokes_the_token_immediately(env):
    c, fake = env
    h = {"Authorization": f"Bearer {make_token('lo', session_id='sess-1')}"}
    assert c.get("/me", headers=h).status_code == 200
    assert c.post("/auth/logout", headers=h).status_code == 204
    assert ("POST", "/logout", None, h["Authorization"][7:], {"scope": "local"}) in fake.calls
    assert c.get("/me", headers=h).status_code == 401
    other = {"Authorization": f"Bearer {make_token('lo', session_id='sess-2')}"}  # perangkat lain tidak ikut keluar
    assert c.get("/me", headers=other).status_code == 200
    assert c.post("/auth/logout", headers=ANON).status_code == 401
    assert c.post("/auth/logout?scope=bogus", headers=other).status_code == 422
