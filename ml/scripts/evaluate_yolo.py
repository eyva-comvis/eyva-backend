"""Evaluasi YOLO pada TEST split kantukv2 + latensi (PRD §3.3, Brief §6.3).

Pakai: python scripts/evaluate_yolo.py datasets/kantukv2/data.yaml --weights models/best.pt
Hasil: metadata/eval_report.json, metadata/confusion_matrix*.png
Catatan: metrik deteksi tidak menilai kualitas hitungan blink/yawn; itu perlu uji video webcam terpisah.
"""
import argparse
import json
import shutil
import statistics
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--weights", type=Path, default=Path("models/best.pt"))
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="")
    ap.add_argument("--bench", type=int, default=30, help="jumlah gambar untuk ukur latensi")
    a = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(str(a.weights))
    m = model.val(data=str(a.data.resolve()), split="test", imgsz=a.imgsz, device=a.device or None,
                  plots=True, project="metadata", name="eval_plots", exist_ok=True)

    per_class = {}
    for i, c in enumerate(m.box.ap_class_index):
        p, r, ap50, ap = m.box.class_result(i)
        per_class[model.names[int(c)]] = {"precision": float(p), "recall": float(r), "mAP50": float(ap50), "mAP50_95": float(ap)}

    imgs = sorted((a.data.parent / "test" / "images").glob("*.*"))[: a.bench]
    lat = []
    for p in imgs:
        t = time.perf_counter()
        model.predict(str(p), imgsz=a.imgsz, device=a.device or None, verbose=False)
        lat.append((time.perf_counter() - t) * 1000)
    lat = lat[2:] or lat  # buang warm-up

    report = {
        "weights": str(a.weights), "split": "test",
        "overall": {"precision": float(m.box.mp), "recall": float(m.box.mr), "mAP50": float(m.box.map50), "mAP50_95": float(m.box.map)},
        "per_class": per_class,
        "latency_ms": {"mean": round(statistics.mean(lat), 1), "p95": round(sorted(lat)[int(len(lat) * .95) - 1], 1), "n": len(lat),
                       "device": a.device or "auto"} if lat else None,
        "limitations": ["Gambar statis; tidak menilai durasi blink/yawn", "Domain dataset bisa berbeda dari webcam laptop"],
    }
    Path("metadata").mkdir(exist_ok=True)
    Path("metadata/eval_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for f in Path("metadata/eval_plots").glob("confusion_matrix*.png"):
        shutil.copy2(f, Path("metadata") / f.name)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
