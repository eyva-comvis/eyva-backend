"""Login wajib di semua endpoint, jadi setiap TestClient otomatis membawa token pengguna uji.

Tes yang butuh klien tanpa login memakai header `Authorization: ""` (lihat ANON di test_auth_stats.py).
Env harus diatur sebelum `app` diimpor (Settings di-cache).
"""
import os
import time

os.environ["SUPABASE_JWT_SECRET"] = "test-secret-with-enough-length-for-hs256!"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""
os.environ["SUPABASE_ANON_KEY"] = ""
os.environ["SESSION_MAX_HOURS"] = "12"
# Tes tidak butuh model/torch. Diatur di sini (bukan di tiap berkas tes) karena Settings di-cache pada impor pertama `app`.
os.environ.update(INFERENCE_BACKEND="mock", MOCK_SCENARIO="drowsy", EYE_CLOSURE_SECONDS="0.1", ALERT1_CONFIRM_SECONDS="0.3",
                  ALERT2_RECHECK_SECONDS="0.3", ALERT_COOLDOWN_SECONDS="5")
os.environ["LLM_API_KEY"] = ""  # tes tidak boleh memanggil LLM sungguhan (key asli bisa ada di .env)

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SECRET = os.environ["SUPABASE_JWT_SECRET"]


def make_token(sub: str = "default-user", *, exp_in: int = 3600, aud: str = "authenticated", secret: str = SECRET,
               login_ago: int | None = None, methods: tuple[str, ...] = ("password",), session_id: str | None = None) -> str:
    now = int(time.time())
    claims = {"sub": sub, "email": f"{sub}@example.com", "aud": aud, "exp": now + exp_in}
    if login_ago is not None:
        claims["amr"] = [{"method": m, "timestamp": now - login_ago} for m in methods]
    if session_id:
        claims["session_id"] = session_id
    return jwt.encode(claims, secret, algorithm="HS256")


_orig_init = TestClient.__init__


def _init_with_default_login(self, *args, **kwargs):
    headers = {"Authorization": f"Bearer {make_token()}", **(kwargs.pop("headers", None) or {})}
    _orig_init(self, *args, headers=headers, **kwargs)


TestClient.__init__ = _init_with_default_login
