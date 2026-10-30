"""Tes autentikasi (JWT Supabase HS256), kepemilikan sesi, refleksi, pause, dan statistik."""
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.stats import compute_stats
from app.core.config import get_settings
from app.main import app
from app.schemas.models import SessionListItem

SECRET = "test-secret-with-enough-length-for-hs256!"
CFG = {"configured_study_seconds": 60, "configured_break_seconds": 60}


def token(sub: str, *, exp_in: int = 3600, aud: str = "authenticated", secret: str = SECRET) -> dict:
    t = jwt.encode({"sub": sub, "email": f"{sub}@example.com", "aud": aud, "exp": int(time.time()) + exp_in}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def client(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(s, "auth_required", False)
    with TestClient(app) as c:
        yield c


def make(c, headers=None, **extra) -> str:
    r = c.post("/sessions", json={**CFG, **extra}, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_me_reports_identity(client):
    assert client.get("/me").json()["authenticated"] is False
    r = client.get("/me", headers=token("user-a")).json()
    assert r["authenticated"] and r["user_id"] == "user-a" and r["auth_enabled"]


def test_invalid_expired_or_wrong_audience_tokens_are_rejected(client):
    for h in (token("u", secret="x" * 40), token("u", exp_in=-10), token("u", aud="anon"), {"Authorization": "Bearer garbage"}):
        assert client.get("/me", headers=h).status_code == 401


def test_auth_required_blocks_anonymous(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_required", True)
    assert client.post("/sessions", json=CFG).status_code == 401
    assert client.post("/sessions", json=CFG, headers=token("u1")).status_code == 201


def test_sessions_are_private_to_their_owner(client):
    a, b = token("owner-a"), token("owner-b")
    sid = make(client, a, title="Thesis")
    assert client.post(f"/sessions/{sid}/blocks", headers=a).status_code == 201
    for h in ({}, b):  # tamu dan pengguna lain: 404, bukan 403
        assert client.post(f"/sessions/{sid}/blocks", headers=h).status_code == 404
        assert client.get(f"/sessions/{sid}/summary", headers=h).status_code == 404
        assert client.post(f"/sessions/{sid}/end", headers=h).status_code == 404
    assert client.get(f"/sessions/{sid}/summary", headers=a).json()["title"] == "Thesis"


def test_guest_sessions_stay_open_and_history_is_per_user(client):
    guest = make(client)
    mine = make(client, token("hist-a"))
    theirs = make(client, token("hist-b"))
    ids_a = {i["id"] for i in client.get("/sessions?limit=100", headers=token("hist-a")).json()["items"]}
    ids_guest = {i["id"] for i in client.get("/sessions?limit=100").json()["items"]}
    assert mine in ids_a and theirs not in ids_a and guest not in ids_a
    assert guest in ids_guest and mine not in ids_guest
    assert client.post(f"/sessions/{guest}/blocks").status_code == 201  # tamu tetap bisa


def test_title_validation_and_defaults(client):
    assert client.post("/sessions", json={**CFG, "title": ""}).status_code == 422
    assert client.post("/sessions", json={**CFG, "title": "x" * 81}).status_code == 422
    r = client.post("/sessions", json=CFG).json()
    assert r["title"] == "Study Session" and r["mandatory_break"] is True


def test_reflection_is_saved_and_validated(client):
    h = token("refl")
    sid = make(client, h)
    client.post(f"/sessions/{sid}/end", json={"reason": "MANUAL"}, headers=h)
    assert client.post(f"/sessions/{sid}/reflection", json={"mood": "great"}, headers=h).status_code == 422
    assert client.post(f"/sessions/{sid}/reflection", json={"mood": "good"}, headers=h).json()["reflection"] == "good"
    assert client.get(f"/sessions/{sid}/summary", headers=h).json()["reflection"] == "good"
    item = next(i for i in client.get("/sessions", headers=h).json()["items"] if i["id"] == sid)
    assert item["reflection"] == "good"
    assert client.post(f"/sessions/{sid}/reflection", json={"mood": "okay"}, headers=token("other")).status_code == 404


def test_manual_pause_then_resume(client):
    sid = make(client)
    bid = client.post(f"/sessions/{sid}/blocks").json()["id"]
    assert client.post(f"/sessions/{sid}/blocks/{bid}/pause").json()["timer_paused"] is True
    assert client.post(f"/sessions/{sid}/blocks/{bid}/resume").json()["timer_paused"] is False
    events = [e["event_type"] for e in client.get(f"/sessions/{sid}/summary").json()["events"]]
    assert "PAUSED_BY_USER" in events
    assert client.post(f"/sessions/{sid}/blocks/nope/pause").status_code == 404


def _item(days_ago: int, study_min: int, alerts: int = 0, drowsy_s: int = 0, mood: str | None = None) -> SessionListItem:
    started = datetime(2026, 10, 30, 10, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return SessionListItem(id=f"s{days_ago}{study_min}", status="ENDED", started_at=started, ended_at=started, end_reason="MANUAL",
                           total_study_seconds=study_min * 60, total_break_seconds=300, estimated_drowsy_seconds=drowsy_s,
                           blink_count=0, yawn_count=0, eye_closure_count=0, alert_1_count=alerts, alert_2_count=0, reflection=mood)


def test_stats_totals_per_day_streak_and_insight():
    now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    items = [_item(0, 25), _item(0, 30, alerts=2, drowsy_s=300, mood="good"), _item(1, 20), _item(2, 40), _item(20, 99)]
    st = compute_stats(items, 14, now)
    assert st.sessions == 4 and st.total_focus_seconds == (25 + 30 + 20 + 40) * 60  # sesi 20 hari lalu di luar jendela
    assert st.current_streak_days == 3 and st.alerts == 2 and st.mood_counts == {"good": 1}
    assert len(st.per_day) == 14 and st.per_day[-1].focus_minutes == 55 and st.per_day[-1].sessions == 2
    assert st.per_day[0].focus_minutes == 0
    assert compute_stats([], 7, now).insight.startswith("No sessions yet")


def test_stats_endpoint_is_per_user(client):
    h = token("stats-user")
    sid = make(client, h)
    client.post(f"/sessions/{sid}/end", json={"reason": "MANUAL"}, headers=h)
    mine = client.get("/stats?days=7", headers=h).json()
    assert mine["sessions"] == 1 and len(mine["per_day"]) == 7
    assert client.get("/stats?days=7", headers=token("nobody")).json()["sessions"] == 0
    assert client.get("/stats?days=3").status_code == 422
