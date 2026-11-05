"""Putar ulang video webcam melalui pipeline asli (YOLO -> temporal -> decision -> state machine alert).

Dipakai untuk kalibrasi threshold (PRD §17, Brief §16.2): rekam video uji, anotasi kejadian manual, lalu bandingkan
hitungan/alert hasil pipeline dengan kenyataan, dan coba beberapa nilai threshold tanpa harus mengulang uji webcam.

Pakai:
  python scripts/replay_video.py rekaman.mp4 --weights models/best.pt --sample-fps 2 --truth truth.csv --out metadata/replay
  python scripts/replay_video.py rekaman.mp4 --sweep         # coba grid eye_closure_seconds x min_conf

truth.csv (opsional), kolom: event,start_s,end_s   event in {blink, eye_closure, yawn, head_dropped, no_face}
  - blink: satu baris per kedipan (start_s saja cukup); eye_closure/yawn/head_dropped/no_face: rentang detik.

--sample-fps meniru laju frame produksi (web mengirim ~1-2 frame/detik). Kedipan normal (0,1-0,4 dtk) hampir
tidak tertangkap pada laju itu; kualitas hitungan blink dibatasi oleh laju sampling, bukan hanya oleh model.
"""
import argparse
import csv
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # root repo backend
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.schemas.models import Detection, DrowsinessStatus  # noqa: E402
from app.services import temporal  # noqa: E402
from app.services.alert_machine import AlertMachine  # noqa: E402
from app.services.decision_engine import decide  # noqa: E402
from app.services.temporal import TemporalTracker  # noqa: E402

MAX_DT = 2.0  # sama dengan backend/app/api/predict.py


def detect_all(model, video: Path, sample_fps: float, imgsz: int, conf: float):
    """Jalankan YOLO sekali per frame sampel; hasilnya dipakai ulang untuk semua kombinasi threshold."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Tidak bisa membuka video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(int(round(fps / sample_fps)), 1)
    frames, idx = [], 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if idx % step == 0:
            r = model.predict(img, imgsz=imgsz, conf=conf, verbose=False)[0]
            dets = [Detection(label=model.names[int(b.cls)], confidence=float(b.conf)) for b in r.boxes]
            frames.append((idx / fps, dets))
        idx += 1
    cap.release()
    return frames, fps


def run_pipeline(frames, settings: Settings, min_conf: float):
    temporal.MIN_CONF = min_conf
    tracker, machine = TemporalTracker(settings), AlertMachine(settings)
    timeline, alerts, drowsy_s, last_t = [], [], 0.0, None
    for t, dets in frames:
        dt = min(t - last_t, MAX_DT) if last_t is not None else 0.0
        last_t = t
        fs = tracker.update(t, dets)
        status, score = decide(fs, settings)
        if status == DrowsinessStatus.DROWSY_NEED_REST:
            drowsy_s += dt
        level = machine.step(t, dt, status)
        if level == 1:
            alerts.append({"t": round(t, 2), "level": 1})
            machine.ack_alert1()  # asumsi: pengguna langsung menekan "Got it"
        elif level == 2:
            alerts.append({"t": round(t, 2), "level": 2})
            machine.continue_after_alert2()
            machine.resume(t)  # asumsi: pengguna memilih lanjut -> cooldown dimulai
        timeline.append({"t": round(t, 2), "status": status.value, "score": score, "face": fs.face_detected,
                         "eye_closed": fs.eye_closed, "yawning": fs.yawning, "head_dropped": fs.head_dropped,
                         "closed_s": round(fs.closed_seconds, 2), "blinks": tracker.blink_count,
                         "yawns": tracker.yawn_count, "closures": tracker.eye_closure_count})
    summary = {"blinks": tracker.blink_count, "yawns": tracker.yawn_count, "eye_closures": tracker.eye_closure_count,
               "drowsy_seconds": round(drowsy_s, 1), "alerts": alerts,
               "no_face_frames": sum(1 for r in timeline if not r["face"]), "frames": len(timeline)}
    return timeline, summary


def load_truth(path: Path | None):
    if not path:
        return None
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    count = lambda ev: sum(1 for r in rows if r["event"].strip() == ev)  # noqa: E731
    return {"blinks": count("blink"), "yawns": count("yawn"), "eye_closures": count("eye_closure")}


def compare(summary: dict, truth: dict | None) -> dict | None:
    if not truth:
        return None
    return {k: {"truth": truth[k], "pipeline": summary[k], "diff": summary[k] - truth[k]} for k in truth}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--weights", type=Path, default=ROOT / "models" / "best.pt")
    ap.add_argument("--sample-fps", type=float, default=2.0)
    ap.add_argument("--imgsz", type=int, default=320)
    ap.add_argument("--yolo-conf", type=float, default=0.25)
    ap.add_argument("--eye-closure-seconds", type=float, default=1.5)
    ap.add_argument("--alert1-confirm-seconds", type=float, default=3.0)
    ap.add_argument("--alert2-recheck-seconds", type=float, default=5.0)
    ap.add_argument("--alert-cooldown-seconds", type=float, default=30.0)
    ap.add_argument("--min-conf", type=float, default=0.4)
    ap.add_argument("--truth", type=Path)
    ap.add_argument("--out", type=Path, help="prefiks keluaran: <out>_timeline.csv dan <out>_summary.json")
    ap.add_argument("--sweep", action="store_true", help="coba grid eye_closure_seconds x min_conf")
    a = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(str(a.weights))
    frames, fps = detect_all(model, a.video, a.sample_fps, a.imgsz, a.yolo_conf)
    print(f"{a.video.name}: {len(frames)} frame sampel (video {fps:.1f} fps, sampel {a.sample_fps} fps)")
    truth = load_truth(a.truth)

    def settings(ecs: float) -> Settings:
        return Settings(_env_file=None, eye_closure_seconds=ecs, alert1_confirm_seconds=a.alert1_confirm_seconds,
                        alert2_recheck_seconds=a.alert2_recheck_seconds, alert_cooldown_seconds=a.alert_cooldown_seconds)

    if a.sweep:
        print("\neye_closure_s  min_conf  blinks yawns closures alerts(t) drowsy_s")
        for ecs, mc in itertools.product([1.0, 1.5, 2.0, 2.5], [0.3, 0.4, 0.5, 0.6]):
            _, s = run_pipeline(frames, settings(ecs), mc)
            print(f"{ecs:>13}  {mc:>8}  {s['blinks']:>6} {s['yawns']:>5} {s['eye_closures']:>8} "
                  f"{[(x['level'], x['t']) for x in s['alerts']]} {s['drowsy_seconds']}")
        return

    timeline, summary = run_pipeline(frames, settings(a.eye_closure_seconds), a.min_conf)
    report = {"video": str(a.video), "params": {k: v for k, v in vars(a).items() if k not in ("video", "weights", "truth", "out", "sweep")},
              "summary": summary, "vs_truth": compare(summary, truth)}
    print(json.dumps(report, indent=2))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with open(f"{a.out}_timeline.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(timeline[0].keys()))
            w.writeheader()
            w.writerows(timeline)
        Path(f"{a.out}_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Tersimpan: {a.out}_timeline.csv, {a.out}_summary.json")


if __name__ == "__main__":
    main()
