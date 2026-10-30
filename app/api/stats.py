"""Statistik pengguna (halaman Statistics) dan identitas sesi login (/me)."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import current_user
from app.core.auth import attach_user, auth_configured
from app.core.config import get_settings
from app.schemas.models import DayStat, MeOut, SessionListItem, StatsOut
from app.services.history import list_items

router = APIRouter(tags=["stats"], dependencies=[Depends(attach_user)])


def _as_dt(v) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _insight(n: int, avg_min: float, alerts: int, drowsy_pct: float, moods: dict[str, int], streak: int) -> str:
    if n == 0:
        return "No sessions yet. Start one and your rhythm will show up here."
    if drowsy_pct >= 15:
        return (f"Signs of drowsiness showed up in about {drowsy_pct:.0f}% of your study time. "
                "Shorter blocks or taking your break a little earlier might feel better. These are visual indications, not a diagnosis.")
    if moods.get("tough", 0) > moods.get("good", 0) and moods.get("tough", 0) >= 2:
        return "A few sessions felt tough. Consider lighter goals or a longer break next time. Small steps still count."
    if streak >= 3:
        return f"You've studied {streak} days in a row. Keep taking breaks and listening to your body's signals."
    if alerts == 0:
        return f"Smooth sessions so far (about {avg_min:.0f} min each) with no drowsiness alerts. Nice rhythm."
    return "You're doing great! Keep taking breaks and listening to your body's signals."


def compute_stats(items: list[SessionListItem], days: int, now: datetime | None = None) -> StatsOut:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    start = today - timedelta(days=days - 1)
    per_day = {(start + timedelta(days=i)).isoformat(): [0.0, 0, 0] for i in range(days)}
    focus = brk = alerts = drowsy = 0
    moods: dict[str, int] = {}
    active_days: set = set()
    counted = 0
    for it in items:
        d = _as_dt(it.started_at).date()
        active_days.add(d)
        if d < start:
            continue
        counted += 1
        focus += it.total_study_seconds
        brk += it.total_break_seconds
        a = it.alert_1_count + it.alert_2_count
        alerts += a
        drowsy += it.estimated_drowsy_seconds
        if it.reflection:
            moods[it.reflection] = moods.get(it.reflection, 0) + 1
        row = per_day.get(d.isoformat())
        if row is not None:
            row[0] += it.total_study_seconds / 60
            row[1] += 1
            row[2] += a
    streak, cur = 0, today if today in active_days else today - timedelta(days=1)
    while cur in active_days:
        streak += 1
        cur -= timedelta(days=1)
    avg = (focus / 60 / counted) if counted else 0.0
    pct = (drowsy / focus * 100) if focus else 0.0
    return StatsOut(
        days=days, sessions=counted, total_focus_seconds=focus, total_break_seconds=brk, alerts=alerts,
        avg_session_minutes=round(avg, 1), drowsy_share_pct=round(pct, 1), current_streak_days=streak,
        mood_counts=moods,
        per_day=[DayStat(date=k, focus_minutes=round(v[0], 1), sessions=v[1], alerts=v[2]) for k, v in per_day.items()],
        insight=_insight(counted, avg, alerts, pct, moods, streak),
    )


@router.get("/stats", response_model=StatsOut)
async def stats(request: Request, days: int = Query(14, ge=7, le=90)):
    items = await list_items(request.app, 1000, 0, current_user(request))
    return compute_stats(items, days)


@router.get("/me", response_model=MeOut)
async def me(request: Request):
    u, s = current_user(request), get_settings()
    return MeOut(authenticated=u is not None, user_id=u.id if u else None, email=u.email if u else None,
                 auth_enabled=auth_configured(s), auth_required=s.auth_required)
