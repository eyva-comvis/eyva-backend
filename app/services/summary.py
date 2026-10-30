from app.schemas.models import SummaryOut
from app.services.session_store import Session, mono


def build_summary(s: Session) -> SummaryOut:
    m = mono()
    blocks = list(s.blocks.values())
    alerts = list(s.alerts.values())
    return SummaryOut(
        session_id=s.id,
        status=s.status,
        title=s.title,
        reflection=s.reflection,
        started_at=s.started_at,
        end_reason=s.end_reason,
        total_study_seconds=round(sum(b.active_seconds(m) for b in blocks)),
        total_break_seconds=round(sum(b.actual_seconds(m) for b in s.breaks.values())),
        total_pause_seconds=round(sum(b.total_paused(m) for b in blocks)),
        blocks_completed=sum(b.status == "COMPLETED" for b in blocks),
        blocks_stopped_early=sum(b.status == "STOPPED_EARLY" for b in blocks),
        blink_count=s.tracker.blink_count,
        yawn_count=s.tracker.yawn_count,
        eye_closure_count=s.tracker.eye_closure_count,
        estimated_drowsy_seconds=round(s.drowsy_seconds),
        alert_1_count=sum(a.level == 1 for a in alerts),
        alert_2_count=sum(a.level == 2 for a in alerts),
        events=s.events,
    )
