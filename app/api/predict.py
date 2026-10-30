"""Inferensi frame + respons alert."""
import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.api.deps import get_session_or_404, persist, require_active
from app.api.sessions import _close_block
from app.core.auth import attach_user
from app.schemas.models import (
    AlertAction, AlertOut, AlertRespondRequest, AlertRespondResponse,
    DrowsinessStatus, PredictRequest, PredictResponse,
)
from app.services.inference import decode_image
from app.services.session_store import Alert, Session, mono, new_id, now_dt

router = APIRouter(prefix="/sessions", tags=["predict"], dependencies=[Depends(attach_user)])

ADVICE = [
    "Stand up and stretch for a moment.",
    "Drink some water.",
    "Look away from the screen for a bit.",
    "Adjust your posture and lighting.",
]
MAX_DT = 2.0  # celah antar frame yang lebih besar dianggap data hilang
METRIC_INTERVAL = 2.0  # detik antar sampel session_metrics
METRIC_FLUSH_BATCH = 10  # tulis ke DB tiap 10 sampel (~20 detik)


def _alert_out(a: Alert) -> AlertOut:
    return AlertOut(
        id=a.id, level=a.level, type=f"DROWSINESS_ALERT_{a.level}", requires_response=True,
        actions=[AlertAction.ACKNOWLEDGE] if a.level == 1
        else [AlertAction.CONTINUE, AlertAction.END_SESSION],
    )


def _response(s: Session, status: DrowsinessStatus, score: int, face: bool) -> PredictResponse:
    pending = s.pending_alert
    b = s.active_block
    return PredictResponse(
        session_id=s.id, block_id=b.id if b else None, status=status, drowsiness_score=score,
        face_detected=face, blink_count=s.tracker.blink_count, yawn_count=s.tracker.yawn_count,
        eye_closure_count=s.tracker.eye_closure_count,
        alert=_alert_out(pending) if pending else None, timer_paused=s.machine.paused,
    )


@router.post("/{session_id}/predict", response_model=PredictResponse)
async def predict(session_id: str, body: PredictRequest, request: Request):
    from app.services.decision_engine import decide

    s = require_active(get_session_or_404(request, session_id))
    block = s.active_block
    if block is None:
        raise HTTPException(409, "Tidak ada blok belajar aktif (monitoring hanya saat belajar)")

    try:
        image = decode_image(body.image_b64)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "image_b64 tidak valid")

    async with s.lock:
        if body.request_id:  # request ganda tidak memproses ulang
            if body.request_id in s.seen_requests:
                return _response(s, DrowsinessStatus.UNCERTAIN, 0, False)
            s.seen_requests.add(body.request_id)

        if s.machine.paused:  # alert/saran terbuka: tidak ada deteksi baru
            return _response(s, DrowsinessStatus.UNCERTAIN, 0, False)

        detections = await run_in_threadpool(request.app.state.engine.predict, image)

        m = mono()
        dt = min(m - s.last_predict_mono, MAX_DT) if s.last_predict_mono else 0.0
        s.last_predict_mono = m

        fs = s.tracker.update(m, detections)
        status, score = decide(fs, s.settings)
        if status == DrowsinessStatus.DROWSY_NEED_REST:
            s.drowsy_seconds += dt

        level = s.machine.step(m, dt, status)
        if level:
            alert = Alert(new_id(), level, block.id, now_dt())
            s.alerts[alert.id] = alert
            block.pause(m)
            s.log(f"DROWSINESS_ALERT_{level}", block.id, alert_id=alert.id, score=score)
            persist(request, s)

        # Metrik di-sample tiap METRIC_INTERVAL detik (bukan per frame), flush per batch.
        if m - s.last_metric_mono >= METRIC_INTERVAL:
            s.last_metric_mono = m
            s.pending_metrics.append({
                "block_id": block.id, "timestamp": now_dt().isoformat(),
                "drowsiness_score": score, "drowsiness_status": status.value,
                "face_detected": fs.face_detected,
                "eye_state": "closed" if fs.eye_closed else "open" if fs.face_detected else None,
                "yawn_state": "yawn" if fs.yawning else "no_yawn" if fs.face_detected else None,
                "head_state": "dropped" if fs.head_dropped else "straight" if fs.face_detected else None,
            })
            if len(s.pending_metrics) >= METRIC_FLUSH_BATCH:
                persist(request, s)
        return _response(s, status, score, fs.face_detected)


@router.post("/{session_id}/alerts/{alert_id}/respond", response_model=AlertRespondResponse)
async def respond_alert(session_id: str, alert_id: str, body: AlertRespondRequest, request: Request):
    s = get_session_or_404(request, session_id)
    a = s.alerts.get(alert_id)
    if a is None:
        raise HTTPException(404, "Alert tidak ditemukan")

    allowed = {1: {AlertAction.ACKNOWLEDGE}, 2: {AlertAction.CONTINUE, AlertAction.END_SESSION}}[a.level]
    if a.response is not None:  # idempoten (AT-16)
        return AlertRespondResponse(alert_id=a.id, action=body.action, already_processed=True)
    if body.action not in allowed:
        raise HTTPException(422, f"Aksi {body.action.value} tidak berlaku untuk alert level {a.level}")

    async with s.lock:
        a.response = body.action.value
        block = s.blocks.get(a.block_id) if a.block_id else None
        s.log("ALERT_ACKNOWLEDGED" if a.level == 1 else
              "CONTINUE_SELECTED" if body.action == AlertAction.CONTINUE else "END_SELECTED",
              a.block_id, alert_id=a.id)

        if body.action == AlertAction.ACKNOWLEDGE:
            s.machine.ack_alert1()
            if block and block.status == "ACTIVE":
                block.resume(mono())  # timer lanjut, monitoring recheck
            persist(request, s)
            return AlertRespondResponse(alert_id=a.id, action=body.action)

        if body.action == AlertAction.CONTINUE:
            s.machine.continue_after_alert2()  # timer TETAP dijeda sampai /resume
            s.log("ADVICE_SHOWN", a.block_id)
            persist(request, s)
            return AlertRespondResponse(alert_id=a.id, action=body.action, show_advice=True, advice=ADVICE)

        # END_SESSION -> frontend langsung ke summary
        if block and block.status == "ACTIVE":
            _close_block(s, block, "STOPPED_EARLY", "ENDED_AFTER_SECOND_ALERT")
        s.end("ENDED_AFTER_SECOND_ALERT")
        persist(request, s)
        return AlertRespondResponse(alert_id=a.id, action=body.action, session_ended=True)
