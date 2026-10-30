"""State machine peringatan dua tahap (PRD bagian 7).

MONITORING -> ALERT_1_PENDING -> RECHECK -> ALERT_2_PENDING -> (END | ADVICE -> MONITORING)

Murni logika (waktu dikirim dari luar) agar mudah di-unit-test tanpa webcam.
"""
from enum import Enum

from app.core.config import Settings
from app.schemas.models import DrowsinessStatus


class Phase(str, Enum):
    MONITORING = "MONITORING"
    ALERT_1_PENDING = "ALERT_1_PENDING"
    RECHECK = "RECHECK"
    ALERT_2_PENDING = "ALERT_2_PENDING"
    ADVICE = "ADVICE"


class AlertMachine:
    def __init__(self, settings: Settings):
        self.s = settings
        self.phase = Phase.MONITORING
        self.drowsy_run = 0.0
        self.cooldown_until = 0.0

    @property
    def paused(self) -> bool:
        """Timer belajar dijeda selama alert/saran terbuka (usulan MVP)."""
        return self.phase in (Phase.ALERT_1_PENDING, Phase.ALERT_2_PENDING, Phase.ADVICE)

    def step(self, now: float, dt: float, status: DrowsinessStatus) -> int | None:
        """Kembalikan level alert (1/2) yang baru harus dimunculkan, atau None."""
        if self.paused:
            return None

        if status == DrowsinessStatus.DROWSY_NEED_REST:
            self.drowsy_run += dt
        elif status == DrowsinessStatus.NORMAL:
            self.drowsy_run = 0.0
            if self.phase == Phase.RECHECK:
                self.phase = Phase.MONITORING  # pulih: reset episode
        # POSSIBLE / UNCERTAIN: tahan, jangan akumulasi dan jangan reset

        if self.phase == Phase.MONITORING:
            if now >= self.cooldown_until and self.drowsy_run >= self.s.alert1_confirm_seconds:
                self.phase = Phase.ALERT_1_PENDING
                return 1
        elif self.phase == Phase.RECHECK:
            if self.drowsy_run >= self.s.alert2_recheck_seconds:
                self.phase = Phase.ALERT_2_PENDING
                return 2
        return None

    def ack_alert1(self) -> None:
        if self.phase == Phase.ALERT_1_PENDING:
            self.phase = Phase.RECHECK
            self.drowsy_run = 0.0

    def continue_after_alert2(self) -> None:
        if self.phase == Phase.ALERT_2_PENDING:
            self.phase = Phase.ADVICE

    def resume(self, now: float) -> None:
        """'Saya siap melanjutkan' setelah saran tindakan."""
        if self.phase == Phase.ADVICE:
            self.phase = Phase.MONITORING
            self.drowsy_run = 0.0
            self.cooldown_until = now + self.s.alert_cooldown_seconds
