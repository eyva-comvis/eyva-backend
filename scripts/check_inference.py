"""Uji model YOLO pada gambar sampel + ukur latensi (NFR-07).

Jalankan dari folder backend/ (setelah `pip install -r requirements-ml.txt` dan best.pt tersedia):

    python scripts/check_inference.py sample1.jpg sample2.jpg --runs 30
    python scripts/check_inference.py sample.jpg --save out.jpg

Memakai build_engine() yang sama dengan server, jadi hasilnya mewakili perilaku API.
Latensi di sini = decode JPEG + inferensi (tanpa jaringan).
"""
import argparse
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("INFERENCE_BACKEND", "yolo")

from app.core.config import get_settings  # noqa: E402
from app.services.inference import build_engine  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="satu atau lebih gambar (jpg/png)")
    ap.add_argument("--runs", type=int, default=20, help="jumlah pengulangan untuk benchmark")
    ap.add_argument("--save", help="simpan gambar beranotasi untuk gambar pertama")
    args = ap.parse_args()

    settings = get_settings()
    print(f"Memuat engine ({settings.inference_backend}) ...")
    engine = build_engine(settings)
    print("Info:", engine.info())

    for p in args.images:
        data = Path(p).read_bytes()
        dets = engine.predict(data)
        print(f"\n{p}: {len(dets)} deteksi")
        for d in sorted(dets, key=lambda d: -d.confidence):
            print(f"  {d.label:<14} conf={d.confidence:.2f}  bbox={[round(v, 2) for v in d.bbox or []]}")

    first = Path(args.images[0]).read_bytes()
    times = []
    for _ in range(args.runs):
        t0 = time.perf_counter()
        engine.predict(first)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p95 = times[min(int(len(times) * 0.95), len(times) - 1)]
    print(f"\nLatensi {args.runs} run: rata-rata {statistics.mean(times):.0f} ms | "
          f"median {statistics.median(times):.0f} ms | p95 {p95:.0f} ms | maks {times[-1]:.0f} ms")
    print(f"Throughput maksimum kira-kira {1000 / statistics.mean(times):.1f} frame/dtk "
          "(frontend sebaiknya mengirim <= separuhnya)")

    if args.save:
        import cv2

        img = cv2.imdecode(__import__("numpy").frombuffer(first, "uint8"), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        for d in engine.predict(first):
            if d.bbox:
                x1, y1, x2, y2 = (int(d.bbox[0] * w), int(d.bbox[1] * h), int(d.bbox[2] * w), int(d.bbox[3] * h))
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(img, f"{d.label} {d.confidence:.2f}", (x1, max(y1 - 6, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.imwrite(args.save, img)
        print("Disimpan:", args.save)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
