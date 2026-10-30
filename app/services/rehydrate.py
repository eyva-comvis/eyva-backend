"""Memuat ulang sesi dari database ke memori setelah server restart/redeploy.

Waktu dinding (started_at) diubah kembali menjadi jam monotonik. Selama server mati, blok belajar yang aktif
tetap dihitung berjalan (jam dinding terus berjalan), sama seperti timer di browser. Hitungan blink/yawn/alert
dipulihkan dari baris sesi; mesin alert dan tracker temporal mulai bersih.
"""
from datetime import datetime

from app.core.config import Settings
from app.services.session_store import Alert, Block, Break, Session, mono, new_id, now_dt


def _dt(v: str | datetime | None) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def _to_mono(at: datetime, now: datetime, m: float) -> float:
    return m - (now - at).total_seconds()


def session_from_rows(data: dict, settings: Settings) -> Session:
    r, now, m = data["session"], now_dt(), mono()
    s = Session(
        r["id"], r["configured_study_seconds"], r["configured_break_seconds"], _dt(r["started_at"]), settings,
        status=r["status"], end_reason=r.get("end_reason"), user_id=r.get("user_id"),
        title=r.get("title") or "Study Session", mandatory_break=r.get("mandatory_break", True),
        soundtrack=r.get("soundtrack"), reflection=r.get("reflection"), ended_at=_dt(r.get("ended_at")),
    )
    s.events = [{k: v for k, v in e.items() if k != "session_id"} for e in data["events"]]
    s.persisted_events = len(s.events)  # semua event ini sudah ada di database

    # Jeda manual terakhir per blok: PAUSED_BY_USER tanpa RESUMED_AFTER_ADVICE sesudahnya.
    paused_at: dict[str, datetime] = {}
    for e in s.events:
        if e["event_type"] == "PAUSED_BY_USER" and e.get("block_id"):
            paused_at[e["block_id"]] = _dt(e["timestamp"])
        elif e["event_type"] == "RESUMED_AFTER_ADVICE":
            paused_at.pop(e.get("block_id"), None)

    for b in sorted(data["blocks"], key=lambda x: x["sequence_number"]):
        started = _dt(b["started_at"])
        blk = Block(b["id"], b["sequence_number"], b["planned_duration_seconds"], started,
                    _to_mono(started, now, m), status=b["status"], paused_seconds=float(b.get("paused_seconds") or 0),
                    end_reason=b.get("end_reason"))
        if b.get("ended_at"):
            blk.ended_at = _dt(b["ended_at"])
            blk.ended_mono = _to_mono(blk.ended_at, now, m)
        elif b["id"] in paused_at:
            blk.paused_since = _to_mono(paused_at[b["id"]], now, m)
        s.blocks[blk.id] = blk

    for br in data.get("breaks", []):
        started = _dt(br["started_at"])
        brk = Break(br["id"], br["planned_duration_seconds"], started, _to_mono(started, now, m),
                    after_block_id=br.get("after_block_id"), status=br["status"])
        if br.get("ended_at"):
            brk.ended_at = _dt(br["ended_at"])
            brk.ended_mono = _to_mono(brk.ended_at, now, m)
        s.breaks[brk.id] = brk

    s.tracker.blink_count = r.get("blink_count") or 0
    s.tracker.yawn_count = r.get("yawn_count") or 0
    s.tracker.eye_closure_count = r.get("eye_closure_count") or 0
    s.drowsy_seconds = float(r.get("estimated_drowsy_seconds") or 0)
    for level, n in ((1, r.get("alert_1_count") or 0), (2, r.get("alert_2_count") or 0)):
        for _ in range(n):  # hanya untuk hitungan di summary; sudah dianggap direspons
            a = Alert(new_id(), level, None, now, response="RESTORED")
            s.alerts[a.id] = a
    return s
