"""Deteksi stateless satu frame (kotak + kelas). Dipakai alat kumpul data webcam laptop (/collect di frontend)
untuk membuat kotak awal; kelas kemudian diperbaiki oleh protokol rekam terpandu.

Dimatikan secara default (ENABLE_DETECT=false) karena ini endpoint inferensi terbuka: aktifkan hanya di mesin lokal.
"""
import binascii

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.auth import attach_user
from app.core.config import get_settings
from app.schemas.models import Detection
from app.services.inference import decode_image

router = APIRouter(tags=["detect"], dependencies=[Depends(attach_user)])


class DetectRequest(BaseModel):
    image_b64: str
    imgsz: int | None = Field(None, ge=160, le=1280)


class DetectResponse(BaseModel):
    detections: list[Detection]


@router.post("/detect", response_model=DetectResponse)
async def detect(body: DetectRequest, request: Request):
    if not get_settings().enable_detect:
        raise HTTPException(404, "Not Found")
    try:
        image = decode_image(body.image_b64)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "image_b64 tidak valid") from None
    dets = await run_in_threadpool(request.app.state.engine.predict, image, body.imgsz)
    return DetectResponse(detections=dets)
