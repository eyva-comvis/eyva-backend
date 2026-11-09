"""Lapisan inferensi. Antarmuka tetap sama untuk mock, YOLO lokal, dan remote API.

Kelas yang dipakai pipeline temporal (verifikasi dengan data.yaml kantukv2):
eye_open, eye_closed, yawn, no_yawn, head_straight, head_dropped
"""
import base64
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol

import httpx

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


class RemoteInference:
    """Inferensi via REST API model Afin (misal di Railway).

    Mengirim gambar mentah (JPEG/PNG) ke POST /v1/predict.
    Konversi hasil deteksi ke format backend Eyva (normalisasi bbox 0..1, filter EXPECTED_CLASSES).
    Toleran terhadap kegagalan jaringan atau worker model sibuk (skip frame, return []).
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.predict_url = f"{self.api_url}/v1/predict"
        self._custom_client = client is not None
        self._client = client or httpx.Client(timeout=timeout)

    def predict(self, image_bytes: bytes, imgsz: int | None = None) -> list[Detection]:
        if not image_bytes:
            return []

        # Deteksi content type dari magic bytes (default image/jpeg)
        content_type = "image/png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": content_type,
        }

        try:
            resp = self._client.post(self.predict_url, content=image_bytes, headers=headers)
        except httpx.TimeoutException as exc:
            log.warning("Timeout saat memanggil remote model (%s): %s", self.predict_url, exc)
            return []
        except httpx.RequestError as exc:
            log.warning("Koneksi gagal ke remote model (%s): %s", self.predict_url, exc)
            return []
        except Exception as exc:
            log.error("Error tak terduga saat request remote model: %s", exc)
            return []

        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception as exc:
                log.warning("Gagal parsing JSON dari remote model: %s", exc)
                return []

            w = float(data.get("image_width") or 0)
            h = float(data.get("image_height") or 0)
            detections: list[Detection] = []

            for item in data.get("detections", []):
                raw_name = str(item.get("class_name") or "")
                label = _norm(raw_name)
                if label not in EXPECTED_CLASSES:
                    continue

                conf = float(item.get("confidence") or 0.0)
                raw_bbox = item.get("bbox_xyxy")
                bbox: list[float] | None = None
                if raw_bbox and len(raw_bbox) == 4 and w > 0 and h > 0:
                    x1, y1, x2, y2 = [float(v) for v in raw_bbox]
                    norm_x1 = max(0.0, min(1.0, x1 / w))
                    norm_y1 = max(0.0, min(1.0, y1 / h))
                    norm_x2 = max(0.0, min(1.0, x2 / w))
                    norm_y2 = max(0.0, min(1.0, y2 / h))
                    bbox = [norm_x1, norm_y1, norm_x2, norm_y2]

                detections.append(Detection(label=label, confidence=conf, bbox=bbox))

            return detections

        if resp.status_code == 401:
            log.error("Autentikasi model API gagal (401 Unauthorized). Periksa MODEL_API_KEY.")
            return []
        if resp.status_code == 422:
            log.warning("Model API mengembalikan 422: format gambar tidak valid atau rusak.")
            return []
        if resp.status_code == 503:
            log.warning("Model API mengembalikan 503: worker model sedang sibuk.")
            return []
        if resp.status_code == 408:
            log.warning("Model API mengembalikan 408: timeout inferensi.")
            return []

        log.warning("Model API mengembalikan HTTP status %d: %s", resp.status_code, resp.text[:200])
        return []

    def info(self) -> dict:
        # Keamanan: JANGAN PERNAH menyertakan self.api_key di dictionary info!
        return {
            "backend": "remote",
            "url": self.api_url,
            "timeout": self.timeout,
        }

    def close(self) -> None:
        if self._client and not self._custom_client:
            self._client.close()


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
    if settings.inference_backend == "remote":
        if not settings.model_api_url or not settings.model_api_url.strip():
            raise RuntimeError(
                "INFERENCE_BACKEND=remote membutuhkan MODEL_API_URL yang valid. "
                "Set di .env atau environment variables."
            )
        if not settings.model_api_key or not settings.model_api_key.strip():
            raise RuntimeError(
                "INFERENCE_BACKEND=remote membutuhkan MODEL_API_KEY yang valid. "
                "Set di .env atau environment variables."
            )
        log.info("Remote inference engine diinisialisasi: url=%s, timeout=%.1fs", settings.model_api_url, settings.model_api_timeout)
        return RemoteInference(
            api_url=settings.model_api_url,
            api_key=settings.model_api_key,
            timeout=settings.model_api_timeout,
        )
    return MockInference(settings.mock_scenario)
