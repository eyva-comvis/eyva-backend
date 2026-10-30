from app.core.config import Settings
from app.schemas.models import DrowsinessStatus as S
from app.services.alert_machine import AlertMachine, Phase

S_ = Settings(alert1_confirm_seconds=3, alert2_recheck_seconds=5, alert_cooldown_seconds=30)


def run(m, start, seconds, status):
    """Simulasi 1 frame/detik; hentikan saat alert muncul."""
    t = start
    for _ in range(seconds):
        t += 1
        lvl = m.step(t, 1.0, status)
        if lvl:
            return t, lvl
    return t, None


def test_no_alert_from_sporadic_frames():
    m = AlertMachine(S_)
    t, lvl = run(m, 0, 2, S.DROWSY_NEED_REST)
    t, lvl = run(m, t, 5, S.NORMAL)
    assert lvl is None and m.phase == Phase.MONITORING


def test_uncertain_never_alerts():
    m = AlertMachine(S_)
    assert run(m, 0, 60, S.UNCERTAIN)[1] is None


def test_alert1_then_recovered_no_alert2():  # AT-04
    m = AlertMachine(S_)
    t, lvl = run(m, 0, 10, S.DROWSY_NEED_REST)
    assert lvl == 1 and m.paused
    m.ack_alert1()
    t, lvl = run(m, t, 3, S.NORMAL)
    assert lvl is None and m.phase == Phase.MONITORING


def test_alert2_only_after_ack_and_recheck():  # AT-05
    m = AlertMachine(S_)
    t, lvl = run(m, 0, 10, S.DROWSY_NEED_REST)
    assert lvl == 1
    assert run(m, t, 10, S.DROWSY_NEED_REST)[1] is None  # belum di-ack: tidak ada alert 2
    m.ack_alert1()
    t, lvl = run(m, t, 10, S.DROWSY_NEED_REST)
    assert lvl == 2


def test_continue_goes_to_advice_then_cooldown():  # AT-07, AT-08
    m = AlertMachine(S_)
    t, _ = run(m, 0, 10, S.DROWSY_NEED_REST)
    m.ack_alert1()
    t, lvl = run(m, t, 10, S.DROWSY_NEED_REST)
    m.continue_after_alert2()
    assert m.phase == Phase.ADVICE and m.paused
    m.resume(t)
    assert not m.paused
    assert run(m, t, 10, S.DROWSY_NEED_REST)[1] is None  # masih cooldown 30 dtk
