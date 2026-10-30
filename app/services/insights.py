"""Rekomendasi AI untuk Summary dan halaman Break.

LLM TIDAK dilatih ulang: ia diberi konteks produk Loopa (LOOPA_CONTEXT) dan metrik terstruktur hasil
kamera (YOLO kantukv2 -> analisis temporal -> decision engine). Tidak pernah ada frame/video yang dikirim.
Bila LLM tidak tersedia, kembali ke teks aturan (fallback) agar sesi tetap bisa selesai.
"""
import json

from app.core.config import Settings
from app.schemas.models import InsightOut, SummaryOut
from app.services import llm
from app.services.session_store import Session, mono

LOOPA_CONTEXT = """You are the study coach inside Loopa, a Pomodoro web app that watches for visual signs of drowsiness.

How Loopa works (so you can explain things accurately):
- The user sets a custom study duration and break duration. The webcam is analysed ONLY during study blocks.
- A YOLO model fine-tuned on the Roboflow "kantukv2" dataset detects per frame: eye_open / eye_closed, no_yawn / yawn, head_straight / head_dropped.
- A temporal engine turns frames into events: blinks, yawns, prolonged eye closures, head dropped.
- A rule-based engine gives a heuristic drowsiness status (Normal, Possible drowsiness, Drowsy, Uncertain). The score is NOT a medical probability.
- Two alerts: Alert 1 is informative; if signs persist, Alert 2 lets the user continue (after a short reset) or end the session.

Hard rules:
- These are visual indications, never a diagnosis. Give no medical advice and do not name causes (sleep disorders, illness).
- Loopa does NOT measure focus, concentration, attention or productivity. Never claim or imply it does.
- Use only the numbers provided. If the data is thin (short session, few events, no camera), say so plainly instead of guessing.
- Tone: warm, calm, specific. Plain text only, no markdown, no emojis, no headings. English.
- Suggestions must be concrete and small: stand and stretch, drink water, look away from the screen (20-20-20), adjust posture or lighting, take the break earlier, shorten the next study block, or sleep earlier tonight.
"""


def _summary_context(s: SummaryOut) -> dict:
    minutes = max(s.total_study_seconds / 60, 0.001)
    kinds: dict[str, int] = {}
    for e in s.events:
        kinds[e["event_type"]] = kinds.get(e["event_type"], 0) + 1
    return {
        "study_minutes": round(s.total_study_seconds / 60, 1),
        "break_minutes": round(s.total_break_seconds / 60, 1),
        "paused_minutes": round(s.total_pause_seconds / 60, 1),
        "blocks_completed": s.blocks_completed,
        "blocks_stopped_early": s.blocks_stopped_early,
        "ended": s.end_reason or s.status,
        "blinks": s.blink_count,
        "blinks_per_minute": round(s.blink_count / minutes, 1),
        "yawns": s.yawn_count,
        "prolonged_eye_closures": s.eye_closure_count,
        "estimated_drowsy_minutes": round(s.estimated_drowsy_seconds / 60, 1),
        "alert_1": s.alert_1_count,
        "alert_2": s.alert_2_count,
        "event_counts": kinds,
    }


def fallback_insight(s: SummaryOut) -> InsightOut:
    study_min = round(s.total_study_seconds / 60)
    parts = [f"You studied for about {study_min} minute(s)."]
    alerts = s.alert_1_count + s.alert_2_count
    if alerts or s.eye_closure_count or s.yawn_count:
        parts.append(
            f"During the session there were {alerts} alert(s), {s.yawn_count} yawn indication(s) and "
            f"{s.eye_closure_count} prolonged eye closure(s). These are visual indications only, not a diagnosis. "
            "Consider a short break and adjust your study length to what feels comfortable."
        )
    else:
        parts.append("No notable signs of drowsiness showed up in this session.")
    return InsightOut(source="fallback", text=" ".join(parts))


async def generate_insight(summary: SummaryOut, settings: Settings) -> InsightOut:
    user = (
        "Write a recommendation for the user's Summary page: 3 to 5 sentences. Start with what the session data "
        "shows, then give 2 or 3 concrete suggestions for the next session.\n\nSession metrics (JSON):\n"
        + json.dumps(_summary_context(summary))
    )
    res = await llm.chat(settings, LOOPA_CONTEXT, user, max_tokens=600)
    return InsightOut(source="llm", text=res.text, model=res.model) if res else fallback_insight(summary)


def break_context(s: Session) -> dict:
    """Metrik blok belajar yang baru selesai + total sesi sejauh ini (untuk tip di halaman break)."""
    blocks = list(s.blocks.values())
    last = blocks[-1] if blocks else None
    m = mono()
    in_last = [a for a in s.alerts.values() if last and a.block_id == last.id]
    study_min = round((last.active_seconds(m) if last else 0) / 60, 1)
    return {
        "block_number": last.sequence_number if last else 0,
        "last_block_study_minutes": study_min,
        "last_block_alert_1": sum(a.level == 1 for a in in_last),
        "last_block_alert_2": sum(a.level == 2 for a in in_last),
        "last_block_ended_by": last.end_reason if last else None,
        "session_blinks": s.tracker.blink_count,
        "session_yawns": s.tracker.yawn_count,
        "session_prolonged_eye_closures": s.tracker.eye_closure_count,
        "session_drowsy_minutes": round(s.drowsy_seconds / 60, 1),
        "planned_break_minutes": round(s.break_seconds / 60, 1),
        "camera_data_available": bool(s.tracker.blink_count or s.tracker.yawn_count or s.tracker.eye_closure_count or in_last),
    }


def fallback_break_tip(ctx: dict) -> InsightOut:
    if ctx["last_block_alert_2"]:
        text = ("You hit two alerts in that block, so this break matters. Stand up, drink some water and look at "
                "something far away. Consider a shorter next block.")
    elif ctx["last_block_alert_1"] or ctx["session_yawns"] or ctx["session_prolonged_eye_closures"]:
        text = "A few signs of tiredness showed up. Use this break to stretch, drink water and rest your eyes away from the screen."
    else:
        text = "Nice block. Use the break to stand up, stretch and look away from the screen for a bit."
    return InsightOut(source="fallback", text=text)


async def generate_break_tip(ctx: dict, settings: Settings) -> InsightOut:
    user = (
        "The user just finished a study block and is starting a break. Write ONE short tip for the Break page: "
        "2 to 3 sentences, one or two concrete things to do during this break, and (only if the data supports it) "
        "one hint for the next block.\n\nBlock metrics (JSON):\n" + json.dumps(ctx)
    )
    res = await llm.chat(settings, LOOPA_CONTEXT, user, max_tokens=400)
    return InsightOut(source="llm", text=res.text, model=res.model) if res else fallback_break_tip(ctx)
