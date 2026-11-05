"""Dashboard admin: halaman /dashboard dan data ringkasan /admin/overview.

Halaman HTML-nya publik (hanya kerangka, tanpa data). Semua data lewat /admin/overview yang hanya dapat dibuka
akun yang emailnya ada di ADMIN_EMAILS. Data pengguna diambil dari Supabase Auth Admin API (service key),
data sesi dari tabel `sessions`.
"""
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.api.deps import current_user, get_store
from app.core.auth import attach_user
from app.core.config import get_settings

log = logging.getLogger("admin")
STATIC = Path(__file__).resolve().parent.parent / "static"

page_router = APIRouter(include_in_schema=False)
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(attach_user)])


@page_router.get("/dashboard")
def dashboard_page():
    return FileResponse(STATIC / "dashboard.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


def require_admin(request: Request) -> None:
    user, admins = current_user(request), get_settings().admin_email_set
    if not admins or not user.email or user.email.lower() not in admins:
        raise HTTPException(403, "Akun ini bukan admin")


def _dt(v) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _fetch_users_sync(url: str, key: str, max_pages: int = 10) -> list[dict]:
    users: list[dict] = []
    with httpx.Client(timeout=10.0) as c:
        for page in range(1, max_pages + 1):
            r = c.get(f"{url.rstrip('/')}/auth/v1/admin/users", params={"page": page, "per_page": 200},
                      headers={"apikey": key, "Authorization": f"Bearer {key}"})
            r.raise_for_status()
            batch = r.json().get("users", [])
            users += batch
            if len(batch) < 200:
                break
    return users


async def _fetch_users() -> list[dict]:
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_key:
        return []
    try:
        raw = await run_in_threadpool(_fetch_users_sync, s.supabase_url, s.supabase_service_key)
    except Exception:
        log.exception("Gagal mengambil daftar pengguna dari Supabase")
        raise HTTPException(502, "Gagal mengambil data pengguna dari Supabase") from None
    return [{
        "id": u.get("id"), "email": u.get("email"),
        "provider": (u.get("app_metadata") or {}).get("provider") or "email",
        "created_at": u.get("created_at"), "last_sign_in_at": u.get("last_sign_in_at"),
        "confirmed": bool(u.get("email_confirmed_at") or u.get("confirmed_at")),
    } for u in raw]


def summarize(users: list[dict], sessions: list[dict], active_now: int, now: datetime | None = None, days: int = 14) -> dict:
    now = now or datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    by_user = Counter(s.get("user_id") for s in sessions if s.get("user_id"))
    email_of = {u["id"]: u["email"] for u in users}

    created = [(_dt(u["created_at"]), u) for u in users]
    new_7d = sum(1 for d, _ in created if d and d >= week_ago)
    active_7d = sum(1 for u in users if (d := _dt(u["last_sign_in_at"])) and d >= week_ago)
    recent_users = [{**u, "sessions": by_user.get(u["id"], 0)}
                    for _, u in sorted(created, key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:10]]

    today = now.date()
    day_keys = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    per_day = {d: {"date": d.isoformat(), "sessions": 0, "focus_minutes": 0.0} for d in day_keys}
    total_focus = alerts = 0
    status = Counter()
    mood = Counter()
    for s in sessions:
        total_focus += s.get("total_study_seconds") or 0
        alerts += (s.get("alert_1_count") or 0) + (s.get("alert_2_count") or 0)
        status[s.get("status") or "UNKNOWN"] += 1
        if s.get("reflection"):
            mood[s["reflection"]] += 1
        d = _dt(s.get("started_at"))
        if d and d.date() in per_day:
            per_day[d.date()]["sessions"] += 1
            per_day[d.date()]["focus_minutes"] += (s.get("total_study_seconds") or 0) / 60

    recent_sessions = [{
        "id": s["id"], "title": s.get("title"), "user_email": email_of.get(s.get("user_id")) or "(tanpa akun)",
        "status": s.get("status"), "started_at": s.get("started_at"),
        "study_minutes": round((s.get("total_study_seconds") or 0) / 60, 1),
        "alerts": (s.get("alert_1_count") or 0) + (s.get("alert_2_count") or 0),
    } for s in sessions[:20]]

    return {
        "users": {
            "total": len(users), "new_7d": new_7d, "active_7d": active_7d,
            "providers": dict(Counter(u["provider"] for u in users)),
            "unverified": sum(1 for u in users if not u["confirmed"]),
            "recent": recent_users,
        },
        "sessions": {
            "total": len(sessions), "active_now": active_now, "status": dict(status),
            "total_focus_hours": round(total_focus / 3600, 1), "alerts": alerts,
            "avg_session_minutes": round(total_focus / 60 / len(sessions), 1) if sessions else 0.0,
            "mood": dict(mood), "per_day": [{**v, "focus_minutes": round(v["focus_minutes"], 1)} for v in per_day.values()],
            "recent": recent_sessions,
        },
    }


@router.get("/overview", dependencies=[Depends(require_admin)])
async def overview(request: Request):
    s = get_settings()
    app = request.app
    users = await _fetch_users()
    repo = app.state.persister.repo
    sessions: list[dict] = []
    if repo.enabled:
        try:
            sessions = await run_in_threadpool(repo.list_sessions, 1000)
        except Exception:
            log.exception("Gagal membaca sesi dari database")
    active_now = sum(1 for x in get_store(request).all() if x.status == "ACTIVE")
    data = summarize(users, sessions, active_now)
    info = app.state.engine.info()
    data["system"] = {
        "version": app.version, "inference_backend": s.inference_backend, "model": info.get("model_path"),
        "classes": info.get("classes"), "device": info.get("device"), "imgsz": info.get("imgsz"),
        "persistence": repo.enabled, "auth_enabled": True, "session_max_hours": s.session_max_hours,
        "llm_enabled": bool(s.llm_api_key), "llm_model": s.llm_model, "admins": len(s.admin_email_set),
    }
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    return data
