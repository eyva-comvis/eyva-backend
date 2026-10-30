"""Analisis temporal: deteksi per frame -> blink / yawn / eye closure / head dropped.

Durasi dihitung dari timestamp nyata (bukan jumlah frame). Semua angka ambang
berasal dari Settings dan bersifat sementara.
"""
from dataclasses import dataclass

from app.core.config import Settings
from app.schemas.models import Detection

MIN_CONF = 0.4
YAWN_MIN_SECONDS = 1.0
HEAD_DROPPED_MIN_SECONDS = 2.0


@dataclass
class FrameState:
    face_detected: bool
    eye_closed: bool
    yawning: bool
    head_dropped: bool
    closed_seconds: float
    head_dropped_seconds: float
    yawn_recent: bool


class TemporalTracker:
    def __init__(self, settings: Settings):
        self.s = settings
        self.blink_count = 0
        self.yawn_count = 0
        self.eye_closure_count = 0
        self._closed_since: float | None = None
        self._closure_counted = False
        self._yawn_since: float | None = None
        self._yawn_counted = False
        self._last_yawn_ts: float | None = None
        self._head_since: float | None = None

    def update(self, now: float, detections: list[Detection]) -> FrameState:
        best: dict[str, float] = {}
        for d in detections:
            if d.confidence >= MIN_CONF:
                best[d.label] = max(best.get(d.label, 0.0), d.confidence)

        face = any(k in best for k in ("eye_open", "eye_closed"))
        closed = face and best.get("eye_closed", 0) > best.get("eye_open", 0)
        yawning = best.get("yawn", 0) > best.get("no_yawn", 0)
        head_dropped = best.get("head_dropped", 0) > best.get("head_straight", 0)

        if not face:
            # Bukti tidak cukup: jangan anggap mata tertutup, reset penghitung durasi.
            self._closed_since = None
            self._closure_counted = False
            self._yawn_since = None
            self._head_since = None
            return FrameState(False, False, False, False, 0.0, 0.0, self._yawn_in_window(now))

        # --- mata ---
        closed_seconds = 0.0
        if closed:
            if self._closed_since is None:
                self._closed_since = now
                self._closure_counted = False
            closed_seconds = now - self._closed_since
            if closed_seconds >= self.s.eye_closure_seconds and not self._closure_counted:
                self.eye_closure_count += 1
                self._closure_counted = True
        else:
            if self._closed_since is not None and not self._closure_counted:
                self.blink_count += 1  # buka-tutup-buka singkat
            self._closed_since = None
            self._closure_counted = False

        # --- menguap ---
        if yawning:
            if self._yawn_since is None:
                self._yawn_since = now
                self._yawn_counted = False
            if now - self._yawn_since >= YAWN_MIN_SECONDS and not self._yawn_counted:
                self.yawn_count += 1
                self._yawn_counted = True
                self._last_yawn_ts = now
        else:
            self._yawn_since = None

        # --- kepala ---
        head_seconds = 0.0
        if head_dropped:
            if self._head_since is None:
                self._head_since = now
            head_seconds = now - self._head_since
        else:
            self._head_since = None

        return FrameState(
            True, closed, yawning, head_dropped, closed_seconds, head_seconds,
            self._yawn_in_window(now),
        )

    def _yawn_in_window(self, now: float, window: float = 60.0) -> bool:
        return self._last_yawn_ts is not None and now - self._last_yawn_ts <= window
