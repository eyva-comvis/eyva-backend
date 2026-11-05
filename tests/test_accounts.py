"""Tes daftar, verifikasi email, login, dan refresh token. Supabase Auth dipalsukan."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import accounts, auth as auth_api
from app.core import auth as core_auth
from app.core.config import get_settings
from app.main import app
from tests.conftest import SECRET, make_token

ANON = {"Authorization": ""}
EMAIL = "baru@example.com"


class FakeSupabase:
    def __init__(self):
        self.calls: list[tuple] = []
        self.signup = lambda payload: httpx.Response(200, json={"id": "u1", "email": payload["email"]})
        self.token_login = lambda payload: httpx.Response(200, json=session("u1"))
        self.verify_ok = True
        self.refresh = lambda payload: httpx.Response(200, json=session("u1"))

    async def __call__(self, method, path, *, json=None, token=None, params=None):
        self.calls.append((method, path, json, token, params))
        req = httpx.Request(method, "http://supabase.test" + path)
        if path == "/signup":
            r = self.signup(json)
        elif path == "/verify":
            r = httpx.Response(200, json=session("u1")) if self.verify_ok else httpx.Response(403, json={"msg": "invalid"})
        elif path == "/resend":
            r = httpx.Response(200, json={})
        elif path == "/token" and params == {"grant_type": "password"}:
            r = self.token_login(json)
        elif path == "/token" and params == {"grant_type": "refresh_token"}:
            r = self.refresh(json)
        else:
            r = httpx.Response(204)  # /logout
        r.request = req
        return r


def session(sub, login_ago=5):
    return {"access_token": make_token(sub, login_ago=login_ago, session_id="s-" + sub), "refresh_token": "rt-user" + sub[-1:],
            "expires_in": 3600, "token_type": "bearer", "user": {"id": sub, "email": f"{sub}@example.com"}}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(get_settings(), "supabase_jwt_secret", SECRET)
    fake = FakeSupabase()
    monkeypatch.setattr(auth_api, "_call", fake)
    core_auth._revoked.clear()
    for lim in (accounts._login_fails, accounts._register_hits, accounts._verify_fails):
        lim.reset()
    with TestClient(app) as c:
        yield c, fake


def post(c, path, body, **kw):
    return c.post(path, json=body, headers=ANON, **kw)


def test_register_is_open_and_requires_email_verification(env):
    c, fake = env
    r = post(c, "/auth/register", {"email": " Baru@Example.com ", "password": "PasswordKuat1", "username": "baru_user"})
    assert r.status_code == 201 and r.json()["requires_verification"] is True and r.json()["tokens"] is None
    assert fake.calls[0][1:3] == ("/signup", {"email": "baru@example.com", "password": "PasswordKuat1", "data": {"username": "baru_user"}})


def test_register_validation_happens_before_calling_supabase(env):
    c, fake = env
    assert post(c, "/auth/register", {"email": EMAIL, "password": "short"}).status_code == 422
    assert post(c, "/auth/register", {"email": "bukan-email", "password": "PasswordKuat1"}).status_code == 422
    assert post(c, "/auth/register", {"email": EMAIL, "password": "PasswordKuat1", "username": "a!"}).status_code == 422
    assert fake.calls == []


def test_register_returns_tokens_when_supabase_confirmation_is_off(env):
    c, fake = env
    fake.signup = lambda p: httpx.Response(200, json=session("u2"))
    r = post(c, "/auth/register", {"email": EMAIL, "password": "PasswordKuat1"})
    assert r.status_code == 201 and r.json()["requires_verification"] is False
    assert r.json()["tokens"]["access_token"] and r.json()["tokens"]["user"]["id"] == "u2"


def test_register_maps_supabase_errors(env):
    c, fake = env
    fake.signup = lambda p: httpx.Response(422, json={"error_code": "user_already_exists", "msg": "x"})
    assert post(c, "/auth/register", {"email": EMAIL, "password": "PasswordKuat1"}).status_code == 409
    fake.signup = lambda p: httpx.Response(422, json={"error_code": "weak_password", "msg": "Password terlalu mudah ditebak"})
    r = post(c, "/auth/register", {"email": EMAIL, "password": "PasswordKuat1"})
    assert r.status_code == 422 and "mudah" in r.json()["detail"]
    fake.signup = lambda p: httpx.Response(429, json={})
    assert post(c, "/auth/register", {"email": EMAIL, "password": "PasswordKuat1"}).status_code == 429


def test_register_is_rate_limited_per_ip(env):
    c, fake = env
    for _ in range(10):
        assert post(c, "/auth/register", {"email": EMAIL, "password": "PasswordKuat1"}).status_code == 201
    assert post(c, "/auth/register", {"email": EMAIL, "password": "PasswordKuat1"}).status_code == 429


def test_verify_email_logs_in_or_rejects_bad_code(env):
    c, fake = env
    r = post(c, "/auth/verify-email", {"email": EMAIL, "code": "123456"})
    assert r.status_code == 200 and r.json()["access_token"] and r.json()["refresh_token"] == "rt-user1"
    assert fake.calls[0][1:3] == ("/verify", {"type": "signup", "email": EMAIL, "token": "123456"})
    fake.verify_ok = False
    assert post(c, "/auth/verify-email", {"email": EMAIL, "code": "000000"}).status_code == 400
    assert post(c, "/auth/verify-email", {"email": EMAIL, "code": "abc"}).status_code == 422


def test_verify_email_locks_after_repeated_wrong_codes(env):
    c, fake = env
    fake.verify_ok = False
    for _ in range(10):
        assert post(c, "/auth/verify-email", {"email": EMAIL, "code": "000000"}).status_code == 400
    assert post(c, "/auth/verify-email", {"email": EMAIL, "code": "000000"}).status_code == 429


def test_resend_verification_is_generic(env):
    c, _ = env
    r = post(c, "/auth/resend-verification", {"email": "siapa@example.com"})
    assert r.status_code == 200 and "kode baru" in r.json()["message"]


def test_login_success_returns_tokens_and_session_deadline(env):
    c, fake = env
    r = post(c, "/auth/login", {"email": "U1@Example.com", "password": "apa-saja"})
    body = r.json()
    assert r.status_code == 200 and body["access_token"] and body["user"] == {"id": "u1", "email": "u1@example.com"}
    assert body["session_expires_at"]  # login 5 detik lalu + 12 jam
    assert fake.calls[0][2]["email"] == "u1@example.com"
    # token hasil login langsung dipakai ke endpoint terproteksi
    assert c.get("/me", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 200


def test_login_wrong_password_is_generic_and_locks_out(env):
    c, fake = env
    fake.token_login = lambda p: httpx.Response(400, json={"error_code": "invalid_credentials", "msg": "Invalid login credentials"})
    for _ in range(8):
        r = post(c, "/auth/login", {"email": EMAIL, "password": "salah"})
        assert r.status_code == 401 and r.json()["detail"] == "Email atau password salah"
    assert post(c, "/auth/login", {"email": EMAIL, "password": "salah"}).status_code == 429
    n = len(fake.calls)
    assert post(c, "/auth/login", {"email": EMAIL, "password": "benar"}).status_code == 429
    assert len(fake.calls) == n  # setelah terkunci Supabase tidak dihubungi lagi
    assert post(c, "/auth/login", {"email": "lain@example.com", "password": "salah"}).status_code == 401  # kunci per email


def test_login_unverified_email_and_successful_login_resets_counter(env):
    c, fake = env
    fake.token_login = lambda p: httpx.Response(400, json={"error_code": "email_not_confirmed", "msg": "x"})
    r = post(c, "/auth/login", {"email": EMAIL, "password": "x"})
    assert r.status_code == 403 and "verifikasi" in r.json()["detail"]
    fake.token_login = lambda p: httpx.Response(400, json={"error_code": "invalid_credentials"})
    for _ in range(7):
        post(c, "/auth/login", {"email": EMAIL, "password": "salah"})
    fake.token_login = lambda p: httpx.Response(200, json=session("u1"))
    assert post(c, "/auth/login", {"email": EMAIL, "password": "benar"}).status_code == 200
    fake.token_login = lambda p: httpx.Response(400, json={"error_code": "invalid_credentials"})
    assert post(c, "/auth/login", {"email": EMAIL, "password": "salah"}).status_code == 401  # hitungan sudah direset


def test_login_rejects_session_older_than_max_age(env):
    c, fake = env
    fake.token_login = lambda p: httpx.Response(200, json=session("u1", login_ago=13 * 3600))
    r = post(c, "/auth/login", {"email": EMAIL, "password": "x"})
    assert r.status_code == 401 and "login ulang" in r.json()["detail"]


def test_refresh_issues_new_tokens(env):
    c, fake = env
    r = post(c, "/auth/refresh", {"refresh_token": "rt-user1"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert fake.calls[0][2] == {"refresh_token": "rt-user1"}


def test_refresh_after_max_login_age_ends_the_session(env):
    c, fake = env
    fake.refresh = lambda p: httpx.Response(200, json=session("u1", login_ago=13 * 3600))
    r = post(c, "/auth/refresh", {"refresh_token": "rt-user1"})
    assert r.status_code == 401 and "login ulang" in r.json()["detail"]
    assert any(m == "POST" and p == "/logout" for m, p, *_ in fake.calls)  # refresh token dimatikan di Supabase


def test_refresh_with_invalid_token_is_401(env):
    c, fake = env
    fake.refresh = lambda p: httpx.Response(400, json={"error_code": "refresh_token_not_found"})
    assert post(c, "/auth/refresh", {"refresh_token": "nope-nope"}).status_code == 401
