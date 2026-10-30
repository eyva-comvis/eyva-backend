import os
import time

os.environ.update(
    INFERENCE_BACKEND="mock", MOCK_SCENARIO="drowsy",
    EYE_CLOSURE_SECONDS="0.1", ALERT1_CONFIRM_SECONDS="0.3",
    ALERT2_RECHECK_SECONDS="0.3", ALERT_COOLDOWN_SECONDS="5",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FRAME = {"image_b64": "AAAA"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def start(c):
    sid = c.post("/sessions", json={"configured_study_seconds": 1500,
                                    "configured_break_seconds": 300}).json()["id"]
    bid = c.post(f"/sessions/{sid}/blocks").json()["id"]
    return sid, bid


def poll_until_alert(c, sid, level):
    for _ in range(60):
        r = c.post(f"/sessions/{sid}/predict", json=FRAME).json()
        if r["alert"] and r["alert"]["level"] == level:
            return r
        time.sleep(0.05)
    raise AssertionError(f"alert {level} tidak muncul")


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_history_works_without_database(client):  # mode in-memory (Supabase tidak diset)
    sid, _ = start(client)
    items = client.get("/sessions").json()["items"]
    assert any(i["id"] == sid and i["status"] == "ACTIVE" for i in items)


def test_full_flow_end_after_alert2(client):  # AT-03, 05, 06
    sid, bid = start(client)
    r1 = poll_until_alert(client, sid, 1)
    assert r1["timer_paused"] and r1["alert"]["actions"] == ["ACKNOWLEDGE"]
    aid1 = r1["alert"]["id"]

    # aksi salah untuk level 1 ditolak; respons ganda idempoten (AT-16)
    assert client.post(f"/sessions/{sid}/alerts/{aid1}/respond", json={"action": "END_SESSION"}).status_code == 422
    assert client.post(f"/sessions/{sid}/alerts/{aid1}/respond", json={"action": "ACKNOWLEDGE"}).status_code == 200
    dup = client.post(f"/sessions/{sid}/alerts/{aid1}/respond", json={"action": "ACKNOWLEDGE"}).json()
    assert dup["already_processed"]

    r2 = poll_until_alert(client, sid, 2)
    assert r2["alert"]["actions"] == ["CONTINUE", "END_SESSION"]
    end = client.post(f"/sessions/{sid}/alerts/{r2['alert']['id']}/respond", json={"action": "END_SESSION"}).json()
    assert end["session_ended"]

    summ = client.get(f"/sessions/{sid}/summary").json()
    assert summ["end_reason"] == "ENDED_AFTER_SECOND_ALERT"
    assert summ["alert_1_count"] == 1 and summ["alert_2_count"] == 1
    assert client.post(f"/sessions/{sid}/predict", json=FRAME).status_code == 409


def test_continue_shows_advice_and_resume(client):  # AT-07, 08
    sid, bid = start(client)
    aid1 = poll_until_alert(client, sid, 1)["alert"]["id"]
    client.post(f"/sessions/{sid}/alerts/{aid1}/respond", json={"action": "ACKNOWLEDGE"})
    aid2 = poll_until_alert(client, sid, 2)["alert"]["id"]
    r = client.post(f"/sessions/{sid}/alerts/{aid2}/respond", json={"action": "CONTINUE"}).json()
    assert r["show_advice"] and 2 <= len(r["advice"]) <= 4
    assert client.post(f"/sessions/{sid}/blocks/{bid}/resume").json()["timer_paused"] is False


def test_break_cycle_and_insight(client):  # AT-09..11
    sid, bid = start(client)
    assert client.post(f"/sessions/{sid}/blocks/{bid}/complete").status_code == 200
    assert client.post(f"/sessions/{sid}/predict", json=FRAME).status_code == 409  # tidak ada monitoring saat break
    brk = client.post(f"/sessions/{sid}/breaks").json()
    assert client.post(f"/sessions/{sid}/breaks/{brk['id']}/complete").status_code == 200
    assert client.post(f"/sessions/{sid}/end", json={"reason": "COMPLETED"}).json()["status"] == "ENDED"
    assert client.post(f"/sessions/{sid}/insights").json()["text"]


def test_cors_preflight_allows_loopback_on_any_port(client):
    for origin in ("http://localhost:3000", "http://127.0.0.1:3000", "http://127.0.0.1:3001"):
        r = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
    bad = client.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert bad.status_code == 400


def test_root_is_friendly(client):
    r = client.get("/")
    assert r.status_code == 200 and r.json()["docs"] == "/docs"
