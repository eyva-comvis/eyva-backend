"""Kontrak API (PRD bagian 10-11). Ubah di sini lalu kabari tim frontend."""
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DrowsinessStatus(str, Enum):
    NORMAL = "NORMAL"
    POSSIBLE_DROWSINESS = "POSSIBLE_DROWSINESS"
    DROWSY_NEED_REST = "DROWSY_NEED_REST"
    UNCERTAIN = "UNCERTAIN"  # termasuk NO_FACE


class AlertAction(str, Enum):
    ACKNOWLEDGE = "ACKNOWLEDGE"  # Alert 1: "Mengerti"
    CONTINUE = "CONTINUE"  # Alert 2: "Lanjutkan sesi"
    END_SESSION = "END_SESSION"  # Alert 2: "Akhiri sesi"


class SessionConfig(BaseModel):
    configured_study_seconds: int = Field(25 * 60, ge=60, le=180 * 60)
    configured_break_seconds: int = Field(5 * 60, ge=60, le=60 * 60)
    title: str = Field("Study Session", min_length=1, max_length=80)
    mandatory_break: bool = True
    soundtrack: str | None = Field(None, max_length=40)


class Detection(BaseModel):
    label: str
    confidence: float
    bbox: list[float] | None = None  # xyxy, ternormalisasi 0-1


class PredictRequest(BaseModel):
    image_b64: str  # JPEG base64 (tanpa prefix data:)
    client_ts: datetime | None = None
    request_id: str | None = None  # idempotensi (NFR-06)


class AlertOut(BaseModel):
    id: str
    level: int
    type: str  # DROWSINESS_ALERT_1 | DROWSINESS_ALERT_2
    requires_response: bool
    actions: list[AlertAction]


class PredictResponse(BaseModel):
    session_id: str
    block_id: str | None
    status: DrowsinessStatus
    drowsiness_score: int
    face_detected: bool
    blink_count: int
    yawn_count: int
    eye_closure_count: int
    alert: AlertOut | None = None
    timer_paused: bool = False


class AlertRespondRequest(BaseModel):
    action: AlertAction


class AlertRespondResponse(BaseModel):
    alert_id: str
    action: AlertAction
    already_processed: bool = False
    show_advice: bool = False
    advice: list[str] = []
    session_ended: bool = False


class SessionOut(BaseModel):
    id: str
    status: str
    configured_study_seconds: int
    configured_break_seconds: int
    started_at: datetime
    title: str = "Study Session"
    mandatory_break: bool = True
    soundtrack: str | None = None


class BlockOut(BaseModel):
    id: str
    session_id: str
    sequence_number: int
    planned_duration_seconds: int
    started_at: datetime
    status: str


class BreakOut(BaseModel):
    id: str
    session_id: str
    planned_duration_seconds: int
    started_at: datetime
    status: str


class EndRequest(BaseModel):
    reason: str = "MANUAL"  # MANUAL | ENDED_AFTER_SECOND_ALERT | COMPLETED


class SummaryOut(BaseModel):
    session_id: str
    status: str
    title: str = "Study Session"
    reflection: str | None = None  # good | okay | tough
    started_at: datetime | None = None
    end_reason: str | None
    total_study_seconds: int
    total_break_seconds: int
    total_pause_seconds: int
    blocks_completed: int
    blocks_stopped_early: int
    blink_count: int
    yawn_count: int
    eye_closure_count: int
    estimated_drowsy_seconds: int
    alert_1_count: int
    alert_2_count: int
    events: list[dict]


class SessionListItem(BaseModel):
    id: str
    title: str = "Study Session"
    reflection: str | None = None
    status: str  # ACTIVE | ENDED | INTERRUPTED (server restart saat sesi berjalan)
    started_at: datetime
    ended_at: datetime | None
    end_reason: str | None
    total_study_seconds: int
    total_break_seconds: int
    estimated_drowsy_seconds: int
    blink_count: int
    yawn_count: int
    eye_closure_count: int
    alert_1_count: int
    alert_2_count: int


class SessionListOut(BaseModel):
    items: list[SessionListItem]
    limit: int
    offset: int


class InsightOut(BaseModel):
    source: str  # llm | fallback
    text: str
    model: str | None = None  # model LLM yang menjawab (hanya bila source == llm)



class ReflectionRequest(BaseModel):
    mood: Literal["good", "okay", "tough"]


class DayStat(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    focus_minutes: float
    sessions: int
    alerts: int


class StatsOut(BaseModel):
    days: int
    sessions: int
    total_focus_seconds: int
    total_break_seconds: int
    alerts: int
    avg_session_minutes: float
    drowsy_share_pct: float  # estimasi waktu indikasi kantuk / waktu fokus
    current_streak_days: int
    mood_counts: dict[str, int]
    per_day: list[DayStat]
    insight: str


class MeOut(BaseModel):
    authenticated: bool
    user_id: str | None = None
    email: str | None = None
    auth_enabled: bool
    auth_required: bool
