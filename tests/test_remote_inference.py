"""Unit tests untuk RemoteInference (model Afin di Railway).

Memverifikasi:
- Header X-API-Key dan Content-Type (magic bytes png/jpeg).
- Body dikirim sebagai raw bytes.
- Konversi response Afin ke Detection: label filter EXPECTED_CLASSES & bbox_xyxy ternormalisasi 0..1.
- Toleransi error Afin: 422, 503, 408/timeout, 401, error jaringan -> return [] tanpa 500.
- Validasi startup build_engine saat MODEL_API_URL / MODEL_API_KEY kosong.
- Keamanan: API key tidak bocor di info() atau log.
- Integrasi E2E dengan endpoint /sessions/{id}/predict dan /detect.
"""
import base64
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.services.inference import (
    EXPECTED_CLASSES,
    RemoteInference,
    build_engine,
)

SAMPLE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
SAMPLE_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"


def test_remote_predict_success_and_bbox_normalized():
    afin_response = {
        "model_version": "ssa-yolo11n-v2",
        "image_width": 640,
        "image_height": 480,
        "detections": [
            {
                "class_id": 0,
                "class_name": "eye_closed",
                "confidence": 0.95,
                "bbox_xyxy": [64.0, 48.0, 128.0, 96.0],
            },
            {
                "class_id": 5,
                "class_name": "head_straight",
                "confidence": 0.88,
                "bbox_xyxy": [0.0, 0.0, 640.0, 480.0],
            },
        ],
    }

    captured_request = {}

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_request["method"] = request.method
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = request.read()
        return httpx.Response(200, json=afin_response)

    transport = httpx.MockTransport(handle_request)
    client = httpx.Client(transport=transport)
    engine = RemoteInference(
        api_url="https://model-test.example.com",
        api_key="secret-afin-key-123",
        timeout=5.0,
        client=client,
    )

    dets = engine.predict(SAMPLE_JPEG)

    # Verifikasi request
    assert captured_request["method"] == "POST"
    assert captured_request["url"] == "https://model-test.example.com/v1/predict"
    assert captured_request["headers"]["x-api-key"] == "secret-afin-key-123"
    assert captured_request["headers"]["content-type"] == "image/jpeg"
    assert captured_request["body"] == SAMPLE_JPEG

    # Verifikasi hasil deteksi
    assert len(dets) == 2
    assert dets[0].label == "eye_closed"
    assert dets[0].confidence == 0.95
    # [64/640, 48/480, 128/640, 96/480] -> [0.1, 0.1, 0.2, 0.2]
    assert dets[0].bbox == pytest.approx([0.1, 0.1, 0.2, 0.2])

    assert dets[1].label == "head_straight"
    assert dets[1].confidence == 0.88
    assert dets[1].bbox == pytest.approx([0.0, 0.0, 1.0, 1.0])


def test_remote_detects_png_content_type():
    captured_content_type = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_content_type.append(request.headers.get("content-type"))
        return httpx.Response(200, json={"image_width": 100, "image_height": 100, "detections": []})

    transport = httpx.MockTransport(handle_request)
    client = httpx.Client(transport=transport)
    engine = RemoteInference(
        api_url="https://model-test.example.com",
        api_key="secret-key",
        client=client,
    )

    engine.predict(SAMPLE_PNG)
    assert captured_content_type[-1] == "image/png"

    engine.predict(SAMPLE_JPEG)
    assert captured_content_type[-1] == "image/jpeg"


def test_remote_filters_unknown_classes():
    afin_response = {
        "model_version": "ssa-yolo11n-v2",
        "image_width": 100,
        "image_height": 100,
        "detections": [
            {"class_id": 99, "class_name": "person", "confidence": 0.99, "bbox_xyxy": [0, 0, 10, 10]},
            {"class_id": 1, "class_name": "eye_open", "confidence": 0.85, "bbox_xyxy": [10, 10, 20, 20]},
        ],
    }

    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=afin_response))
    client = httpx.Client(transport=transport)
    engine = RemoteInference(
        api_url="https://model-test.example.com",
        api_key="secret-key",
        client=client,
    )

    dets = engine.predict(SAMPLE_JPEG)
    assert len(dets) == 1
    assert dets[0].label == "eye_open"
    assert dets[0].label in EXPECTED_CLASSES


@pytest.mark.parametrize(
    "status_code",
    [422, 503, 408, 401, 500],
)
def test_remote_http_errors_return_empty_list(status_code, caplog):
    transport = httpx.MockTransport(lambda req: httpx.Response(status_code, text="error occurred"))
    client = httpx.Client(transport=transport)
    engine = RemoteInference(
        api_url="https://model-test.example.com",
        api_key="secret-key",
        client=client,
    )

    dets = engine.predict(SAMPLE_JPEG)
    assert dets == []
    if status_code == 401:
        assert any("autentikasi" in rec.message.lower() or "401" in rec.message for rec in caplog.records)


def test_remote_timeout_and_network_error_returns_empty_list():
    def handle_timeout(request: httpx.Request):
        raise httpx.ReadTimeout("Timeout connecting to model server")

    transport = httpx.MockTransport(handle_timeout)
    client = httpx.Client(transport=transport)
    engine = RemoteInference(
        api_url="https://model-test.example.com",
        api_key="secret-key",
        client=client,
    )

    dets = engine.predict(SAMPLE_JPEG)
    assert dets == []


def test_remote_info_never_exposes_api_key():
    engine = RemoteInference(
        api_url="https://model-test.example.com",
        api_key="SUPER_SECRET_KEY_NEVER_LOG",
        timeout=8.0,
    )
    info = engine.info()
    assert info["backend"] == "remote"
    assert info["url"] == "https://model-test.example.com"
    assert "SUPER_SECRET_KEY_NEVER_LOG" not in str(info)
    assert "api_key" not in info
    engine.close()


def test_build_engine_fails_on_missing_remote_env():
    s_no_key = Settings(
        inference_backend="remote",
        model_api_url="https://model-production-eyva.up.railway.app",
        model_api_key="",
    )
    with pytest.raises(RuntimeError, match="MODEL_API_KEY"):
        build_engine(s_no_key)

    s_no_url = Settings(
        inference_backend="remote",
        model_api_url="",
        model_api_key="valid-key",
    )
    with pytest.raises(RuntimeError, match="MODEL_API_URL"):
        build_engine(s_no_url)


def test_e2e_predict_endpoint_with_remote_engine():
    afin_response = {
        "model_version": "ssa-yolo11n-v2",
        "image_width": 640,
        "image_height": 480,
        "detections": [
            {
                "class_id": 1,
                "class_name": "eye_open",
                "confidence": 0.92,
                "bbox_xyxy": [100.0, 100.0, 200.0, 200.0],
            },
            {
                "class_id": 5,
                "class_name": "head_straight",
                "confidence": 0.89,
                "bbox_xyxy": [50.0, 50.0, 300.0, 300.0],
            },
        ],
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=afin_response))
    mock_client = httpx.Client(transport=transport)
    engine = RemoteInference(
        api_url="https://model-test.example.com",
        api_key="secret-key",
        client=mock_client,
    )

    with TestClient(app) as test_client:
        app.state.engine = engine

        # Buat sesi & blok belajar aktif
        s_res = test_client.post("/sessions", json={"configured_study_seconds": 1500, "configured_break_seconds": 300})
        assert s_res.status_code == 201
        sid = s_res.json()["id"]

        b_res = test_client.post(f"/sessions/{sid}/blocks")
        assert b_res.status_code == 201

        # Kirim frame prediksi
        b64_img = base64.b64encode(SAMPLE_JPEG).decode("ascii")
        p_res = test_client.post(f"/sessions/{sid}/predict", json={"image_b64": b64_img})

        assert p_res.status_code == 200
        body = p_res.json()
        assert body["session_id"] == sid
        assert body["face_detected"] is True
        assert body["status"] in ["NORMAL", "POSSIBLE_DROWSINESS", "DROWSY_NEED_REST", "UNCERTAIN"]


def test_e2e_detect_endpoint_with_remote_engine(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "enable_detect", True)

    afin_response = {
        "model_version": "ssa-yolo11n-v2",
        "image_width": 640,
        "image_height": 480,
        "detections": [
            {
                "class_id": 0,
                "class_name": "eye_closed",
                "confidence": 0.95,
                "bbox_xyxy": [64.0, 48.0, 128.0, 96.0],
            }
        ],
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=afin_response))
    mock_client = httpx.Client(transport=transport)
    engine = RemoteInference(
        api_url="https://model-test.example.com",
        api_key="secret-key",
        client=mock_client,
    )

    with TestClient(app) as test_client:
        app.state.engine = engine
        b64_img = base64.b64encode(SAMPLE_JPEG).decode("ascii")
        res = test_client.post("/detect", json={"image_b64": b64_img})
        assert res.status_code == 200
        dets = res.json()["detections"]
        assert len(dets) == 1
        assert dets[0]["label"] == "eye_closed"
        assert dets[0]["bbox"] == pytest.approx([0.1, 0.1, 0.2, 0.2])
