"""State sesi di memori. Jalankan 1 worker uvicorn (state tidak dibagi antar proses).

Persistensi ke Supabase ditambahkan lewat app/db/ pada tahap 10-11 Nov.
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config import Settings
from app.services.alert_machine import AlertMachine
from app.services.temporal import TemporalTracker


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Block:
    id: str
    sequence_number: int
    planned_seconds: int
    started_at: datetime
    started_mono: float
    status: str = "ACTIVE"  # ACTIVE | COMPLETED | STOPPED_EARLY
    paused_since: float | None = None
    paused_seconds: float = 0.0
    ended_mono: float | None = None
    ended_at: datetime | None = None
    end_reason: str | None = None

    def pause(self, mono: float) -> None:
        if self.paused_since is None:
            self.paused_since = mono

    def resume(self, mono: float) -> None:
        if self.paused_since is not None:
            self.paused_seconds += mono - self.paused_since
            self.paused_since = None

    def active_seconds(self, mono: float) -> float:
        end = self.ended_mono if self.ended_mono is not None else mono
        pausing = (end - self.paused_since) if self.paused_since is not None else 0.0
        return max(end - self.started_mono - self.paused_seconds - pausing, 0.0)

    def total_paused(self, mono: float) -> float:
        end = self.ended_mono if self.ended_mono is not None else mono
        return self.paused_seconds + ((end - self.paused_since) if self.paused_since is not None else 0.0)


@dataclass
class Break:
    id: str
    planned_seconds: int
    started_at: datetime
    started_mono: float
    after_block_id: str | None = None
    status: str = "ACTIVE"
    ended_mono: float | None = None
    ended_at: datetime | None = None

    def actual_seconds(self, mono: float) -> float:
        end = self.ended_mono if self.ended_mono is not None else mono
        return max(end - self.started_mono, 0.0)


@dataclass
class Alert:
    id: str
    level: int
    block_id: str | None
    created_at: datetime
    response: str | None = None  # None = masih menunggu respons


@dataclass
class Session:
    id: str
    study_seconds: int
    break_seconds: int
    started_at: datetime
    settings: Settings
    status: str = "ACTIVE"  # ACTIVE | ENDED
    end_reason: str | None = None
    user_id: str | None = None  # pemilik (Supabase auth.users.id); None = tamu
    title: str = "Study Session"
    mandatory_break: bool = True
    soundtrack: str | None = None
    reflection: str | None = None  # good | okay | tough
    blocks: dict[str, Block] = field(default_factory=dict)
    breaks: dict[str, Break] = field(default_factory=dict)
    alerts: dict[str, Alert] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    seen_requests: set[str] = field(default_factory=set)
    ended_at: datetime | None = None
    drowsy_seconds: float = 0.0
    last_predict_mono: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # --- write-behind ke database ---
    db_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    persisted_events: int = 0
    pending_metrics: list[dict] = field(default_factory=list)
    last_metric_mono: float = 0.0

    def __post_init__(self) -> None:
        self.tracker = TemporalTracker(self.settings)
        self.machine = AlertMachine(self.settings)

    def end(self, reason: str) -> None:
        self.status, self.end_reason, self.ended_at = "ENDED", reason, now_dt()
        self.log("SESSION_ENDED", reason=reason)

    @property
    def active_block(self) -> Block | None:
        return next((b for b in self.blocks.values() if b.status == "ACTIVE"), None)

    @property
    def active_break(self) -> Break | None:
        return next((b for b in self.breaks.values() if b.status == "ACTIVE"), None)

    @property
    def pending_alert(self) -> Alert | None:
        return next((a for a in self.alerts.values() if a.response is None), None)

    def log(self, event_type: str, block_id: str | None = None,
            duration: float | None = None, **metadata) -> None:
        self.events.append({
            "id": new_id(),
            "timestamp": now_dt().isoformat(),
            "event_type": event_type,
            "block_id": block_id,
            "duration_seconds": duration,
            "metadata": metadata,
        })


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, study: int, brk: int, settings: Settings, *, user_id: str | None = None,
               title: str = "Study Session", mandatory_break: bool = True, soundtrack: str | None = None) -> Session:
        s = Session(new_id(), study, brk, now_dt(), settings, user_id=user_id, title=title,
                    mandatory_break=mandatory_break, soundtrack=soundtrack)
        self._sessions[s.id] = s
        s.log("SESSION_CREATED")
        return s

    def add(self, s: Session) -> None:
        self._sessions[s.id] = s

    def all(self) -> list[Session]:
        return list(self._sessions.values())

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)


def mono() -> float:
    return time.monotonic()
