"""Riwayat sesi: gabungan state memori (otoritatif untuk sesi yang masih hidup) dan database."""
import logging

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from app.core.auth import User
from app.schemas.models import SessionListItem, SummaryOut
from app.services.summary import build_summary

log = logging.getLogger("history")


def _status_from_db(status: str) -> str:
    # ACTIVE di DB tetapi tidak ada di memori = server restart di tengah sesi.
    return "INTERRUPTED" if status == "ACTIVE" else status


def _item_from_row(r: dict) -> SessionListItem:
    return SessionListItem(
        id=r["id"], title=r.get("title") or "Study Session", reflection=r.get("reflection"),
        status=_status_from_db(r["status"]),
        started_at=r["started_at"], ended_at=r.get("ended_at"), end_reason=r.get("end_reason"),
        total_study_seconds=r.get("total_study_seconds") or 0,
        total_break_seconds=r.get("total_break_seconds") or 0,
        estimated_drowsy_seconds=r.get("estimated_drowsy_seconds") or 0,
        blink_count=r.get("blink_count") or 0, yawn_count=r.get("yawn_count") or 0,
        eye_closure_count=r.get("eye_closure_count") or 0,
        alert_1_count=r.get("alert_1_count") or 0, alert_2_count=r.get("alert_2_count") or 0,
    )


def _visible(owner_id: str | None, user: User | None) -> bool:
    """Riwayat hanya berisi sesi milik pengguna saat ini; tamu hanya melihat sesi tamu."""
    return owner_id == (user.id if user else None)


async def list_items(app: FastAPI, limit: int, offset: int, user: User | None = None) -> list[SessionListItem]:
    by_id: dict[str, SessionListItem] = {}

    repo = app.state.persister.repo
    if repo.enabled:
        try:
            rows = await run_in_threadpool(repo.list_sessions, limit + offset, user.id if user else None)
            by_id.update({r["id"]: _item_from_row(r) for r in rows if _visible(r.get("user_id"), user)})
        except Exception:
            log.exception("Gagal membaca riwayat dari database; menampilkan sesi di memori saja")

    for s in app.state.store.all():  # memori menimpa DB: lebih baru dari write-behind
        if not _visible(s.user_id, user):
            continue
        sm = build_summary(s)
        by_id[s.id] = SessionListItem(
            id=s.id, title=s.title, reflection=s.reflection, status=s.status, started_at=s.started_at, ended_at=s.ended_at,
            end_reason=s.end_reason, total_study_seconds=sm.total_study_seconds,
            total_break_seconds=sm.total_break_seconds,
            estimated_drowsy_seconds=sm.estimated_drowsy_seconds, blink_count=sm.blink_count,
            yawn_count=sm.yawn_count, eye_closure_count=sm.eye_closure_count,
            alert_1_count=sm.alert_1_count, alert_2_count=sm.alert_2_count,
        )

    items = sorted(by_id.values(), key=lambda i: i.started_at, reverse=True)
    return items[offset: offset + limit]


async def load_summary(app: FastAPI, session_id: str, user: User | None = None) -> SummaryOut | None:
    s = app.state.store.get(session_id)
    if s is not None:
        return build_summary(s) if (s.user_id is None or (user is not None and user.id == s.user_id)) else None

    repo = app.state.persister.repo
    if not repo.enabled:
        return None
    try:
        data = await run_in_threadpool(repo.get_session_rows, session_id)
    except Exception:
        log.exception("Gagal membaca sesi %s dari database", session_id)
        return None
    if data is None:
        return None

    r, blocks = data["session"], data["blocks"]
    owner = r.get("user_id")
    if owner is not None and (user is None or user.id != owner):
        return None
    events = [{k: v for k, v in e.items() if k != "session_id"} for e in data["events"]]
    return SummaryOut(
        session_id=r["id"], status=_status_from_db(r["status"]), end_reason=r.get("end_reason"),
        title=r.get("title") or "Study Session", reflection=r.get("reflection"), started_at=r.get("started_at"),
        total_study_seconds=r.get("total_study_seconds") or 0,
        total_break_seconds=r.get("total_break_seconds") or 0,
        total_pause_seconds=r.get("total_pause_seconds") or 0,
        blocks_completed=sum(b["status"] == "COMPLETED" for b in blocks),
        blocks_stopped_early=sum(b["status"] == "STOPPED_EARLY" for b in blocks),
        blink_count=r.get("blink_count") or 0, yawn_count=r.get("yawn_count") or 0,
        eye_closure_count=r.get("eye_closure_count") or 0,
        estimated_drowsy_seconds=r.get("estimated_drowsy_seconds") or 0,
        alert_1_count=r.get("alert_1_count") or 0, alert_2_count=r.get("alert_2_count") or 0,
        events=events,
    )
