"""Persistensi write-behind ke Supabase.

State in-memory tetap sumber utama selama sesi berjalan. Setelah tiap perubahan penting
Persister mengupsert snapshot ke database di background. Semua upsert idempoten, dan
kegagalan DB tidak boleh menggagalkan request (NFR-03).
"""
import asyncio
import logging
from typing import Any, Protocol

from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.services.session_store import Session, mono
from app.services.summary import build_summary

log = logging.getLogger("persistence")

# Urutan penting: parent sebelum child (foreign key).
TABLE_ORDER = ["sessions", "pomodoro_blocks", "breaks", "session_metrics", "events"]


class Repository(Protocol):
    enabled: bool

    def write(self, payload: dict[str, list[dict]]) -> None: ...
    def list_sessions(self, limit: int, user_id: str | None = None) -> list[dict]: ...
    def get_session_rows(self, session_id: str) -> dict | None: ...


class NullRepository:
    enabled = False

    def write(self, payload: dict[str, list[dict]]) -> None:
        pass

    def list_sessions(self, limit: int, user_id: str | None = None) -> list[dict]:
        return []

    def get_session_rows(self, session_id: str) -> dict | None:
        return None


class SupabaseRepository:
    enabled = True

    def __init__(self, url: str, service_key: str, client: Any = None):
        if client is None:
            from supabase import create_client  # pip install supabase

            client = create_client(url, service_key)
        self.client = client

    def write(self, payload: dict[str, list[dict]]) -> None:
        for table in TABLE_ORDER:
            rows = payload.get(table)
            if not rows:
                continue
            if table == "session_metrics":  # id bigserial: insert saja
                self.client.table(table).insert(rows).execute()
            else:
                self.client.table(table).upsert(rows, on_conflict="id").execute()

    def list_sessions(self, limit: int, user_id: str | None = None) -> list[dict]:
        """`limit` terbaru (urut started_at menurun). Paginasi dilakukan di service setelah digabung dengan memori.
        Dengan user_id: hanya milik pengguna itu. Tanpa user_id: semua baris (service menyaring sesi tamu)."""
        q = self.client.table("sessions").select("*")
        if user_id:
            q = q.eq("user_id", user_id)
        res = q.order("started_at", desc=True).limit(limit).execute()
        return res.data or []

    def get_session_rows(self, session_id: str) -> dict | None:
        res = self.client.table("sessions").select("*").eq("id", session_id).limit(1).execute()
        if not res.data:
            return None
        blocks = (self.client.table("pomodoro_blocks").select("*")
                  .eq("session_id", session_id).execute()).data or []
        events = (self.client.table("events").select("*")
                  .eq("session_id", session_id).order("timestamp").execute()).data or []
        return {"session": res.data[0], "blocks": blocks, "events": events}


def build_repository(settings: Settings) -> Repository:
    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseRepository(settings.supabase_url, settings.supabase_service_key)
    log.info("Supabase tidak dikonfigurasi: persistensi dimatikan (in-memory saja)")
    return NullRepository()


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def build_payload(s: Session, events_from: int, metrics: list[dict]) -> dict[str, list[dict]]:
    m = mono()
    sm = build_summary(s)
    return {
        "sessions": [{
            "id": s.id, "user_id": s.user_id, "title": s.title, "mandatory_break": s.mandatory_break,
            "soundtrack": s.soundtrack, "reflection": s.reflection, "started_at": _iso(s.started_at), "ended_at": _iso(s.ended_at),
            "status": s.status, "configured_study_seconds": s.study_seconds,
            "configured_break_seconds": s.break_seconds,
            "total_study_seconds": sm.total_study_seconds, "total_break_seconds": sm.total_break_seconds,
            "total_pause_seconds": sm.total_pause_seconds,
            "estimated_drowsy_seconds": sm.estimated_drowsy_seconds,
            "blink_count": sm.blink_count, "yawn_count": sm.yawn_count,
            "eye_closure_count": sm.eye_closure_count,
            "drowsiness_event_count": sm.alert_1_count,  # 1 episode = 1 Alert 1
            "alert_1_count": sm.alert_1_count, "alert_2_count": sm.alert_2_count,
            "end_reason": s.end_reason,
        }],
        "pomodoro_blocks": [{
            "id": b.id, "session_id": s.id, "sequence_number": b.sequence_number,
            "planned_duration_seconds": b.planned_seconds,
            "actual_active_seconds": round(b.active_seconds(m)),
            "paused_seconds": round(b.total_paused(m)),
            "started_at": _iso(b.started_at), "ended_at": _iso(b.ended_at),
            "status": b.status, "end_reason": b.end_reason,
        } for b in s.blocks.values()],
        "breaks": [{
            "id": br.id, "session_id": s.id, "after_block_id": br.after_block_id,
            "planned_duration_seconds": br.planned_seconds,
            "actual_duration_seconds": round(br.actual_seconds(m)),
            "started_at": _iso(br.started_at), "ended_at": _iso(br.ended_at), "status": br.status,
        } for br in s.breaks.values()],
        "session_metrics": [{**row, "session_id": s.id} for row in metrics],
        "events": [{**e, "session_id": s.id} for e in s.events[events_from:]],
    }


class Persister:
    def __init__(self, repo: Repository):
        self.repo = repo
        self._tasks: set[asyncio.Task] = set()

    def schedule(self, s: Session) -> None:
        """Jadwalkan sinkronisasi di background; tidak memblokir request."""
        if not self.repo.enabled:
            return
        t = asyncio.create_task(self.sync(s))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def sync(self, s: Session) -> bool:
        if not self.repo.enabled:
            return True
        async with s.db_lock:
            ev_n, met_n = len(s.events), len(s.pending_metrics)
            payload = build_payload(s, s.persisted_events, list(s.pending_metrics[:met_n]))
            try:
                await run_in_threadpool(self.repo.write, payload)
            except Exception:
                log.exception("Gagal menyimpan sesi %s ke database; akan dicoba lagi pada sinkronisasi berikutnya", s.id)
                return False
            s.persisted_events = ev_n  # kursor maju hanya jika berhasil
            del s.pending_metrics[:met_n]
            return True

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
