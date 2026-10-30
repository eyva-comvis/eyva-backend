"""Aturan status kantuk. Skor 0-100 adalah heuristik, BUKAN probabilitas medis."""
from app.core.config import Settings
from app.schemas.models import DrowsinessStatus
from app.services.temporal import HEAD_DROPPED_MIN_SECONDS, FrameState


def decide(fs: FrameState, s: Settings) -> tuple[DrowsinessStatus, int]:
    if not fs.face_detected:
        return DrowsinessStatus.UNCERTAIN, 0

    score = 0.0
    score += min(fs.closed_seconds / s.eye_closure_seconds, 1.0) * 60
    if fs.yawn_recent:
        score += 15
    if fs.head_dropped_seconds >= HEAD_DROPPED_MIN_SECONDS:
        score += 15  # indikator pendukung saja
    score = int(min(score, 100))

    if fs.closed_seconds >= s.eye_closure_seconds:
        return DrowsinessStatus.DROWSY_NEED_REST, score
    if score >= 25:
        return DrowsinessStatus.POSSIBLE_DROWSINESS, score
    return DrowsinessStatus.NORMAL, score
