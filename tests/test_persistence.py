import os
import time
from types import SimpleNamespace

os.environ.update(
    INFERENCE_BACKEND="mock", MOCK_SCENARIO="normal",
    EYE_CLOSURE_SECONDS="0.1", ALERT1_CONFIRM_SECONDS="0.3",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.repository import Persister, SupabaseRepository  # noqa: E402
from app.main import app  # noqa: E402

FRAME = {"image_b64": "AAAA"}


class FakeTable:
    def __init__(self, db, name):
        self.db, self.name, self.rows, self.mode = db, name, None, None
        self.filters, self.order_key, self.desc, self.lim = [], None, False, None

    def upsert(self, rows, on_conflict=None):
        self.rows, self.mode = rows, "upsert"
        return self

    def insert(self, rows):
        self.rows, self.mode = rows, "insert"
        return self

    def select(self, cols="*"):
        self.mode = "select"
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def order(self, col, desc=False):
        self.order_key, self.desc = col, desc
        return self

    def limit(self, n):
        self.lim = n
        return self

    def execute(self):
        if self.db.fail:
            raise RuntimeError("supabase down")
        store = self.db.tables.setdefault(self.name, {})
        if self.mode == "select":
            out = [r for r in store.values() if all(r.get(c) == v for c, v in self.filters)]
            if self.order_key:
                out.sort(key=lambda r: r[self.order_key], reverse=self.desc)
            return SimpleNamespace(data=out[: self.lim] if self.lim else out)
        for r in self.rows:
            key = r.get("id") or f"auto{len(store)}"
            store[key] = r
        self.db.calls.append(self.name)
        return SimpleNamespace(data=self.rows)


class FakeClient:
    def __init__(self):
        self.tables, self.calls, self.fail = {}, [], False

    def table(self, name):
        return FakeTable(self, name)


@pytest.fixture
def env():
    fake = FakeClient()
    with TestClient(app) as c:
        app.state.persister = Persister(SupabaseRepository("", "", client=fake))
        yield c, fake


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_lifecycle_is_persisted_in_fk_order(env):
    c, fake = env
    sid = c.post("/sessions", json={"configured_study_seconds": 1500, "configured_break_seconds": 300}).json()["id"]
    bid = c.post(f"/sessions/{sid}/blocks").json()["id"]
    for _ in range(3):
        c.post(f"/sessions/{sid}/predict", json=FRAME)
    c.post(f"/sessions/{sid}/blocks/{bid}/complete")
    brk = c.post(f"/sessions/{sid}/breaks").json()["id"]
    c.post(f"/sessions/{sid}/breaks/{brk}/complete")
    c.post(f"/sessions/{sid}/end", json={"reason": "COMPLETED"})

    assert wait_for(lambda: fake.tables.get("sessions", {}).get(sid, {}).get("status") == "ENDED")
    assert fake.tables["pomodoro_blocks"][bid]["status"] == "COMPLETED"
    assert fake.tables["breaks"][brk]["after_block_id"] == bid
    types = {e["event_type"] for e in fake.tables["events"].values()}
    assert {"SESSION_CREATED", "STUDY_STARTED", "STUDY_COMPLETED", "BREAK_STARTED", "SESSION_ENDED"} <= types
    # parent sebelum child pada setiap sinkronisasi
    calls = fake.calls
    assert calls.index("sessions") < calls.index("pomodoro_blocks") < calls.index("breaks")


def test_db_failure_does_not_break_requests_and_recovers(env):
    c, fake = env
    fake.fail = True
    r = c.post("/sessions", json={"configured_study_seconds": 1500, "configured_break_seconds": 300})
    assert r.status_code == 201
    sid = r.json()["id"]
    c.post(f"/sessions/{sid}/blocks")  # tetap 201 walau DB mati
    time.sleep(0.3)
    assert "sessions" not in fake.tables

    fake.fail = False
    c.post(f"/sessions/{sid}/end", json={"reason": "MANUAL"})
    assert wait_for(lambda: "SESSION_CREATED" in {e["event_type"] for e in fake.tables.get("events", {}).values()})
    # event yang gagal tersimpan sebelumnya ikut terkirim (kursor tidak maju saat gagal)
    assert "STUDY_STARTED" in {e["event_type"] for e in fake.tables["events"].values()}


def _run_session(c, end=True):
    sid = c.post("/sessions", json={"configured_study_seconds": 1500, "configured_break_seconds": 300}).json()["id"]
    bid = c.post(f"/sessions/{sid}/blocks").json()["id"]
    c.post(f"/sessions/{sid}/predict", json=FRAME)
    if end:
        c.post(f"/sessions/{sid}/end", json={"reason": "MANUAL"})
    return sid, bid


def test_history_survives_server_restart(env):  # FR-16
    from app.services.session_store import SessionStore

    c, fake = env
    sid_old, _ = _run_session(c)
    assert wait_for(lambda: fake.tables.get("sessions", {}).get(sid_old, {}).get("status") == "ENDED")

    app.state.store = SessionStore()  # simulasi restart: memori kosong, DB tetap
    sid_new, _ = _run_session(c, end=False)  # sesi baru, masih berjalan di memori

    data = c.get("/sessions").json()
    ids = [i["id"] for i in data["items"]]
    assert ids[0] == sid_new and sid_old in ids  # terbaru dulu, gabungan memori + DB
    old = next(i for i in data["items"] if i["id"] == sid_old)
    assert old["status"] == "ENDED" and old["end_reason"] == "MANUAL"

    summ = c.get(f"/sessions/{sid_old}/summary")
    assert summ.status_code == 200 and summ.json()["end_reason"] == "MANUAL"
    assert any(e["event_type"] == "SESSION_ENDED" for e in summ.json()["events"])
    assert c.post(f"/sessions/{sid_old}/insights").status_code == 200
    # sesi lama tidak bisa dimutasi setelah restart
    assert c.post(f"/sessions/{sid_old}/blocks").status_code == 404


def test_session_active_in_db_but_lost_from_memory_is_interrupted(env):
    from app.services.session_store import SessionStore

    c, fake = env
    sid, _ = _run_session(c, end=False)
    assert wait_for(lambda: "pomodoro_blocks" in fake.tables)
    app.state.store = SessionStore()
    item = next(i for i in c.get("/sessions").json()["items"] if i["id"] == sid)
    assert item["status"] == "INTERRUPTED"
    assert c.get(f"/sessions/{sid}/summary").json()["status"] == "INTERRUPTED"


def test_history_pagination_and_unknown_id(env):
    c, _ = env
    for _ in range(3):
        _run_session(c)
    assert len(c.get("/sessions?limit=2").json()["items"]) == 2
    assert c.get("/sessions?limit=0").status_code == 422
    assert c.get("/sessions/doesnotexist/summary").status_code == 404


def test_health_reports_persistence_flag(env):
    c, _ = env
    assert c.get("/health").json()["persistence"] is True
