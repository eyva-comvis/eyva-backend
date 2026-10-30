"""Lapisan inferensi. Antarmuka tetap sama untuk mock dan YOLO asli.

Kelas yang dipakai pipeline temporal (verifikasi dengan data.yaml kantukv2):
eye_open, eye_closed, yawn, no_yawn, head_straight, head_dropped
"""
import base64
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from app.core.config import Settings
from app.schemas.models import Detection

log = logging.getLogger("inference")

BACKEND_DIR = Path(__file__).resolve().parents[2]
EXPECTED_CLASSES = {"eye_open", "eye_closed", "yawn", "no_yawn", "head_straight", "head_dropped"}


class InferenceEngine(Protocol):
    def predict(self, image_bytes: bytes, imgsz: int | None = None) -> list[Detection]: ...
    def info(self) -> dict: ...


class MockInference:
    """Pengganti model sampai best.pt tersedia. Tidak membaca gambar."""

    def __init__(self, scenario: str = "normal"):
        self.scenario = scenario

    def predict(self, image_bytes: bytes, imgsz: int | None = None) -> list[Detection]:
        if self.scenario == "drowsy":
            return [
                Detection(label="eye_closed", confidence=0.9),
                Detection(label="head_straight", confidence=0.8),
            ]
        return [
            Detection(label="eye_open", confidence=0.9),
            Detection(label="head_straight", confidence=0.8),
        ]

    def info(self) -> dict:
        return {"backend": "mock", "scenario": self.scenario}


def _norm(label: str) -> str:
    return label.strip().lower().replace(" ", "_").replace("-", "_")


def _cv2_decode(image_bytes: bytes) -> Any:
    import cv2
    import numpy as np  # butuh requirements-ml.txt

    return cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)


class YoloInference:
    """Membungkus model Ultralytics YOLO.

    `model` dan `decoder` bisa disuntik agar logika ini bisa diuji tanpa torch/opencv.
    """

    def __init__(self, model: Any, *, conf: float = 0.25, imgsz: int = 640, device: str = "",
                 aliases: dict[str, str] | None = None, decoder: Callable[[bytes], Any] = _cv2_decode,
                 model_path: str = "", warmup: Any = None):
        self.model, self.conf, self.imgsz, self.device = model, conf, imgsz, device
        self.decoder, self.model_path = decoder, model_path
        self._lock = threading.Lock()  # satu model tidak aman dipanggil paralel dari banyak thread

        aliases = {_norm(k): _norm(v) for k, v in (aliases or {}).items()}
        raw_names = model.names if isinstance(model.names, dict) else dict(enumerate(model.names))
        self.class_map = {int(i): aliases.get(_norm(n), _norm(n)) for i, n in raw_names.items()}
        self._validate_classes()

        if warmup is not None:  # inferensi pertama lambat; lakukan sebelum request pertama
            self._predict_raw(warmup)

    @classmethod
    def from_path(cls, model_path: str, settings: Settings) -> "YoloInference":
        path = Path(model_path)
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        if not path.exists():  # cek dulu agar pesan jelas walau requirements-ml belum terpasang
            raise RuntimeError(
                f"Model YOLO tidak ditemukan di {path}. Letakkan best.pt di sana, atau set "
                "INFERENCE_BACKEND=mock untuk pengembangan tanpa model."
            )
        from ultralytics import YOLO  # butuh requirements-ml.txt
        import numpy as np

        return cls(
            YOLO(str(path)), conf=settings.yolo_conf, imgsz=settings.yolo_imgsz,
            device=settings.yolo_device, aliases=settings.yolo_label_aliases, model_path=str(path),
            warmup=np.zeros((settings.yolo_imgsz, settings.yolo_imgsz, 3), dtype=np.uint8),
        )

    def _validate_classes(self) -> None:
        got = set(self.class_map.values())
        missing = EXPECTED_CLASSES - got
        if not (got & EXPECTED_CLASSES):
            raise RuntimeError(
                f"Tidak ada kelas model yang dikenali pipeline. Kelas model: {sorted(got)}. "
                f"Diharapkan: {sorted(EXPECTED_CLASSES)}. Atur YOLO_LABEL_ALIASES atau periksa model/data.yaml."
            )
        if missing:
            log.warning("Kelas berikut tidak ada di model dan tidak akan pernah terdeteksi: %s", sorted(missing))
        extra = got - EXPECTED_CLASSES
        if extra:
            log.warning("Kelas model di luar pipeline (diabaikan): %s", sorted(extra))

    def _predict_raw(self, img: Any, imgsz: int | None = None) -> list[Detection]:
        kwargs: dict[str, Any] = {"conf": self.conf, "imgsz": imgsz or self.imgsz, "verbose": False}
        if self.device:
            kwargs["device"] = self.device
        with self._lock:
            result = self.model.predict(img, **kwargs)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        out: list[Detection] = []
        for cls_id, conf, box in zip(boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxyn.tolist()):
            label = self.class_map.get(int(cls_id))
            if label in EXPECTED_CLASSES:  # kelas asing dibuang, bukan dikirim ke temporal
                out.append(Detection(label=label, confidence=float(conf), bbox=[float(v) for v in box]))
        return out

    def predict(self, image_bytes: bytes, imgsz: int | None = None) -> list[Detection]:
        img = self.decoder(image_bytes)
        if img is None:  # JPEG rusak: sama dengan "tidak ada wajah", bukan error 500
            return []
        return self._predict_raw(img, imgsz)

    def info(self) -> dict:
        return {"backend": "yolo", "model_path": self.model_path, "classes": sorted(set(self.class_map.values())),
                "conf": self.conf, "imgsz": self.imgsz, "device": self.device or "auto"}


def decode_image(image_b64: str) -> bytes:
    if "," in image_b64[:50]:  # toleransi prefix data:image/jpeg;base64,
        image_b64 = image_b64.split(",", 1)[1]
    return base64.b64decode(image_b64)


def build_engine(settings: Settings) -> InferenceEngine:
    if settings.inference_backend == "yolo":
        t0 = time.perf_counter()
        engine = YoloInference.from_path(settings.model_path, settings)
        log.info("Model YOLO dimuat dalam %.1f dtk: %s", time.perf_counter() - t0, engine.info())
        return engine
    return MockInference(settings.mock_scenario)
