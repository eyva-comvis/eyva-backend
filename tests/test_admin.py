"""Tes dashboard admin: akses hanya untuk ADMIN_EMAILS dan agregasi data."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import admin as admin_api
from app.core.config import get_settings
from app.main import app
from tests.conftest import SECRET, make_token

ANON = {"Authorization": ""}
NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)

USERS = [
    {"id": "u1", "email": "a@example.com", "provider": "google", "created_at": "2026-11-04T10:00:00Z",
     "last_sign_in_at": "2026-11-05T09:00:00Z", "confirmed": True},
    {"id": "u2", "email": "b@example.com", "provider": "email", "created_at": "2026-10-01T10:00:00Z",
     "last_sign_in_at": None, "confirmed": False},
]
SESSIONS = [
    {"id": "s1", "user_id": "u1", "title": "Skripsi", "status": "ENDED", "started_at": "2026-11-05T08:00:00Z",
     "total_study_seconds": 3600, "alert_1_count": 2, "alert_2_count": 1, "reflection": "good"},
    {"id": "s2", "user_id": "u1", "title": "Baca", "status": "ENDED", "started_at": "2026-11-04T08:00:00Z",
     "total_study_seconds": 1800, "alert_1_count": 0, "alert_2_count": 0, "reflection": "tough"},
    {"id": "s3", "user_id": None, "title": "Lama", "status": "ENDED", "started_at": "2026-09-01T08:00:00Z",
     "total_study_seconds": 600},
]


def hdr(email_sub: str) -> dict:
    return {"Authorization": f"Bearer {make_token(email_sub)}"}  # email token uji = "<sub>@example.com"


class FakeRepo:
    enabled = True

    def list_sessions(self, limit, user_id=None):
        return SESSIONS


@pytest.fixture
def env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(s, "admin_emails", "Admin@example.com, lain@example.com")

    async def fake_users():
        return USERS
    monkeypatch.setattr(admin_api, "_fetch_users", fake_users)
    with TestClient(app) as c:
        original = app.state.persister
        app.state.persister = SimpleNamespace(repo=FakeRepo(), drain=original.drain)
        yield c


def test_summarize_aggregates_users_sessions_and_days():
    d = admin_api.summarize(USERS, SESSIONS, active_now=1, now=NOW)
    u, s = d["users"], d["sessions"]
    assert u["total"] == 2 and u["new_7d"] == 1 and u["active_7d"] == 1 and u["unverified"] == 1
    assert u["providers"] == {"google": 1, "email": 1}
    assert u["recent"][0]["email"] == "a@example.com" and u["recent"][0]["sessions"] == 2
    assert s["total"] == 3 and s["active_now"] == 1 and s["alerts"] == 3
    assert s["total_focus_hours"] == 1.7 and s["avg_session_minutes"] == 33.3
    assert s["mood"] == {"good": 1, "tough": 1}
    assert len(s["per_day"]) == 14 and s["per_day"][-1] == {"date": "2026-11-05", "sessions": 1, "focus_minutes": 60.0}
    assert s["per_day"][-2]["sessions"] == 1  # sesi 1 September di luar jendela 14 hari
    assert s["recent"][0]["user_email"] == "a@example.com" and s["recent"][2]["user_email"] == "(tanpa akun)"


def test_summarize_handles_empty_data():
    d = admin_api.summarize([], [], 0, now=NOW)
    assert d["users"]["total"] == 0 and d["sessions"]["avg_session_minutes"] == 0.0 and d["sessions"]["recent"] == []


def test_overview_requires_login_and_admin_email(env):
    assert env.get("/admin/overview", headers=ANON).status_code == 401
    assert env.get("/admin/overview", headers=hdr("biasa")).status_code == 403


def test_overview_is_forbidden_when_no_admin_is_configured(env, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_emails", "")
    assert env.get("/admin/overview", headers=hdr("admin")).status_code == 403


def test_overview_for_admin_is_case_insensitive_and_complete(env):
    r = env.get("/admin/overview", headers=hdr("admin"))  # token email: admin@example.com
    assert r.status_code == 200
    d = r.json()
    assert d["users"]["total"] == 2 and d["sessions"]["total"] == 3
    assert d["system"]["persistence"] is True and d["system"]["admins"] == 2 and d["generated_at"]
    assert env.get("/admin/overview", headers=hdr("lain")).status_code == 200


def test_dashboard_page_is_public_html_without_data(env):
    r = env.get("/dashboard", headers=ANON)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Eyva Admin" in r.text and "a@example.com" not in r.text
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "/dashboard" not in env.get("/openapi.json", headers=ANON).text  # tidak muncul di Swagger
