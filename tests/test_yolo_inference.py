"""Uji logika pembungkus YOLO dengan model tiruan (tanpa torch/opencv/best.pt).

Ini TIDAK membuktikan kompatibilitas dengan ultralytics asli; jalankan
scripts/check_inference.py setelah best.pt tersedia.
"""
import threading
import time
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.inference import EXPECTED_CLASSES, YoloInference, build_engine

NAMES = {0: "eye_closed", 1: "eye_open", 2: "no_yawn", 3: "yawn", 4: "head_dropped", 5: "head_straight"}


class FakeBoxes:
    def __init__(self, rows):  # rows: (cls, conf, (x1,y1,x2,y2))
        self.cls = SimpleNamespace(tolist=lambda: [r[0] for r in rows])
        self.conf = SimpleNamespace(tolist=lambda: [r[1] for r in rows])
        self.xyxyn = SimpleNamespace(tolist=lambda: [list(r[2]) for r in rows])
        self._n = len(rows)

    def __len__(self):
        return self._n


class FakeModel:
    def __init__(self, rows=(), names=None, delay=0.0):
        self.names, self.rows, self.delay = names or NAMES, rows, delay
        self.calls, self.kwargs, self.active, self.max_active = 0, None, 0, 0

    def predict(self, img, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(self.delay)
        self.active -= 1
        return [SimpleNamespace(boxes=FakeBoxes(self.rows))]


def make(model, **kw):
    return YoloInference(model, decoder=lambda b: object() if b != b"bad" else None, **kw)


def test_parses_detections_with_normalized_bbox():
    m = FakeModel(rows=[(0, 0.91, (0.1, 0.2, 0.3, 0.4)), (5, 0.8, (0, 0, 1, 1))])
    dets = make(m).predict(b"img")
    assert [(d.label, round(d.confidence, 2)) for d in dets] == [("eye_closed", 0.91), ("head_straight", 0.8)]
    assert dets[0].bbox == [0.1, 0.2, 0.3, 0.4]


def test_passes_config_to_model_and_omits_empty_device():
    m = FakeModel()
    make(m, conf=0.3, imgsz=320).predict(b"img")
    assert m.kwargs == {"conf": 0.3, "imgsz": 320, "verbose": False}
    make(m, device="cpu").predict(b"img")
    assert m.kwargs["device"] == "cpu"


def test_no_detections_and_bad_jpeg_return_empty_not_error():
    assert make(FakeModel(rows=[])).predict(b"img") == []
    m = FakeModel(rows=[(0, 0.9, (0, 0, 1, 1))])
    assert make(m).predict(b"bad") == [] and m.calls == 0


def test_label_normalization_and_aliases():
    names = {0: "Eye-Closed", 1: "closed eye?", 2: "Yawn"}
    eng = make(FakeModel(rows=[(0, .9, (0, 0, 1, 1)), (1, .9, (0, 0, 1, 1)), (2, .7, (0, 0, 1, 1))], names=names),
               aliases={"closed eye?": "eye_open"})
    assert {d.label for d in eng.predict(b"x")} == {"eye_closed", "eye_open", "yawn"}


def test_unknown_classes_are_dropped():
    names = {**NAMES, 6: "person"}
    eng = make(FakeModel(rows=[(6, 0.99, (0, 0, 1, 1)), (1, 0.5, (0, 0, 1, 1))], names=names))
    assert [d.label for d in eng.predict(b"x")] == ["eye_open"]


def test_wrong_model_fails_fast_with_clear_message():
    with pytest.raises(RuntimeError, match="Tidak ada kelas model yang dikenali"):
        make(FakeModel(names={0: "cat", 1: "dog"}))


def test_missing_classes_only_warn(caplog):
    make(FakeModel(names={0: "eye_open", 1: "eye_closed"}))
    assert "tidak akan pernah terdeteksi" in caplog.text


def test_concurrent_calls_are_serialized():
    m = FakeModel(delay=0.05)
    eng = make(m)
    ts = [threading.Thread(target=eng.predict, args=(b"x",)) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert m.calls == 4 and m.max_active == 1


def test_warmup_runs_once_at_startup():
    m = FakeModel()
    make(m, warmup="blank")
    assert m.calls == 1


def test_missing_weights_gives_actionable_error():
    s = Settings(inference_backend="yolo", model_path="../models/tidak_ada.pt")
    with pytest.raises(RuntimeError, match="Model YOLO tidak ditemukan.*tidak_ada.pt"):
        build_engine(s)


def test_expected_classes_match_prd():
    assert EXPECTED_CLASSES == {"eye_open", "eye_closed", "yawn", "no_yawn", "head_straight", "head_dropped"}
