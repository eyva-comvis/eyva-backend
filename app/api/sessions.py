"""Siklus Pomodoro: sessions, blocks, breaks, end, summary, insights."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import current_user, get_session_or_404, get_store, persist, require_active
from app.core.auth import attach_user
from app.core.config import get_settings
from app.schemas.models import (
    BlockOut, BreakOut, EndRequest, InsightOut, ReflectionRequest, SessionConfig, SessionListOut, SessionOut, SummaryOut,
)
from app.services.history import list_items, load_summary
from app.services.insights import break_context, generate_break_tip, generate_insight
from app.services.session_store import Block, Break, Session, mono, new_id, now_dt
from app.services.summary import build_summary

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(attach_user)])


def _close_block(s: Session, block: Block, status: str, reason: str) -> None:
    block.resume(mono())
    block.status = status
    block.ended_mono = mono()
    block.ended_at = now_dt()
    block.end_reason = reason
    s.log("STUDY_COMPLETED" if status == "COMPLETED" else "STUDY_STOPPED",
          block.id, block.active_seconds(mono()), reason=reason)


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(cfg: SessionConfig, request: Request):
    user = current_user(request)
    s = get_store(request).create(
        cfg.configured_study_seconds, cfg.configured_break_seconds, get_settings(),
        user_id=user.id if user else None, title=cfg.title.strip() or "Study Session",
        mandatory_break=cfg.mandatory_break, soundtrack=cfg.soundtrack,
    )
    persist(request, s)
    return SessionOut(id=s.id, status=s.status, configured_study_seconds=s.study_seconds,
                      configured_break_seconds=s.break_seconds, started_at=s.started_at, title=s.title,
                      mandatory_break=s.mandatory_break, soundtrack=s.soundtrack)


@router.post("/{session_id}/blocks", response_model=BlockOut, status_code=201)
async def start_block(session_id: str, request: Request):
    s = require_active(get_session_or_404(request, session_id))
    if s.active_block or s.active_break:
        raise HTTPException(409, "Masih ada blok belajar atau istirahat yang aktif")
    b = Block(new_id(), len(s.blocks) + 1, s.study_seconds, now_dt(), mono())
    s.blocks[b.id] = b
    s.machine.__init__(s.settings)  # episode baru per blok
    s.last_predict_mono = None
    s.log("STUDY_STARTED", b.id, planned_seconds=b.planned_seconds)
    persist(request, s)
    return BlockOut(id=b.id, session_id=s.id, sequence_number=b.sequence_number,
                    planned_duration_seconds=b.planned_seconds, started_at=b.started_at, status=b.status)


@router.post("/{session_id}/blocks/{block_id}/complete")
async def complete_block(session_id: str, block_id: str, request: Request):
    s = require_active(get_session_or_404(request, session_id))
    b = s.blocks.get(block_id)
    if b is None:
        raise HTTPException(404, "Block tidak ditemukan")
    if b.status != "ACTIVE":  # idempoten
        return {"block_id": b.id, "status": b.status, "already_processed": True}
    _close_block(s, b, "COMPLETED", "TIMER_DONE")
    persist(request, s)
    return {"block_id": b.id, "status": b.status, "active_seconds": round(b.active_seconds(mono()))}


@router.post("/{session_id}/blocks/{block_id}/pause")
async def pause_block(session_id: str, block_id: str, request: Request):
    """Jeda manual oleh pengguna (tombol Pause). Frontend berhenti mengirim frame selama dijeda."""
    s = require_active(get_session_or_404(request, session_id))
    b = s.blocks.get(block_id)
    if b is None or b.status != "ACTIVE":
        raise HTTPException(404, "Block aktif tidak ditemukan")
    b.pause(mono())
    s.log("PAUSED_BY_USER", b.id)
    persist(request, s)
    return {"block_id": b.id, "timer_paused": True}


@router.post("/{session_id}/blocks/{block_id}/resume")
async def resume_block(session_id: str, block_id: str, request: Request):
    """'Saya siap melanjutkan' setelah saran tindakan (tambahan di luar daftar PRD)."""
    s = require_active(get_session_or_404(request, session_id))
    b = s.blocks.get(block_id)
    if b is None or b.status != "ACTIVE":
        raise HTTPException(404, "Block aktif tidak ditemukan")
    s.machine.resume(mono())
    b.resume(mono())
    s.log("RESUMED_AFTER_ADVICE", b.id)
    persist(request, s)
    return {"block_id": b.id, "timer_paused": False}


@router.post("/{session_id}/breaks", response_model=BreakOut, status_code=201)
async def start_break(session_id: str, request: Request):
    s = require_active(get_session_or_404(request, session_id))
    if s.active_block or s.active_break:
        raise HTTPException(409, "Selesaikan blok belajar terlebih dahulu")
    last = list(s.blocks.values())[-1] if s.blocks else None
    if last is None:
        raise HTTPException(409, "Belum ada blok belajar")
    br = Break(new_id(), s.break_seconds, now_dt(), mono(), after_block_id=last.id)
    s.breaks[br.id] = br
    s.log("BREAK_STARTED", last.id, planned_seconds=br.planned_seconds)
    persist(request, s)
    return BreakOut(id=br.id, session_id=s.id, planned_duration_seconds=br.planned_seconds,
                    started_at=br.started_at, status=br.status)


@router.post("/{session_id}/breaks/{break_id}/complete")
async def complete_break(session_id: str, break_id: str, request: Request):
    s = require_active(get_session_or_404(request, session_id))
    br = s.breaks.get(break_id)
    if br is None:
        raise HTTPException(404, "Break tidak ditemukan")
    if br.status != "ACTIVE":
        return {"break_id": br.id, "status": br.status, "already_processed": True}
    br.status, br.ended_mono, br.ended_at = "COMPLETED", mono(), now_dt()
    s.log("BREAK_COMPLETED", None, br.actual_seconds(mono()))
    persist(request, s)
    return {"break_id": br.id, "status": br.status}


@router.post("/{session_id}/end", response_model=SummaryOut)
async def end_session(session_id: str, request: Request, body: EndRequest | None = None):
    s = get_session_or_404(request, session_id)
    if s.status == "ACTIVE":  # idempoten: panggilan kedua hanya mengembalikan summary
        reason = (body or EndRequest()).reason
        if (b := s.active_block):
            _close_block(s, b, "STOPPED_EARLY", reason)
        if (br := s.active_break):
            br.status, br.ended_mono, br.ended_at = "COMPLETED", mono(), now_dt()
        s.end(reason)
        persist(request, s)
    return build_summary(s)


@router.get("", response_model=SessionListOut)
async def list_sessions(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    """Riwayat sesi (FR-16), terbaru dulu. Belum ada autentikasi: daftar ini global."""
    return SessionListOut(items=await list_items(request.app, limit, offset, current_user(request)), limit=limit, offset=offset)


async def _summary_or_404(request: Request, session_id: str) -> SummaryOut:
    sm = await load_summary(request.app, session_id, current_user(request))
    if sm is None:
        raise HTTPException(404, "Session tidak ditemukan")
    return sm


@router.get("/{session_id}/summary", response_model=SummaryOut)
async def get_summary(session_id: str, request: Request):
    return await _summary_or_404(request, session_id)


@router.post("/{session_id}/insights", response_model=InsightOut)
async def create_insight(session_id: str, request: Request):
    return await generate_insight(await _summary_or_404(request, session_id), get_settings())


@router.post("/{session_id}/break-tip", response_model=InsightOut)
async def create_break_tip(session_id: str, request: Request):
    """Tip singkat AI di halaman Break, berdasarkan blok belajar yang baru selesai (sesi harus masih di memori)."""
    s = get_session_or_404(request, session_id)
    return await generate_break_tip(break_context(s), get_settings())


@router.post("/{session_id}/reflection")
async def save_reflection(session_id: str, body: ReflectionRequest, request: Request):
    """Refleksi pengguna di halaman Session Wrap (Good / Okay / Tough). Boleh diubah setelah sesi berakhir."""
    s = get_session_or_404(request, session_id)
    s.reflection = body.mood
    s.log("REFLECTION_SAVED", None, mood=body.mood)
    persist(request, s)
    return {"session_id": s.id, "reflection": s.reflection}
