"""Fine-tuning YOLO pretrained pada kantukv2 saja (PRD §3.2). Bukan dari bobot acak.

Pakai: python scripts/train_yolo.py datasets/kantukv2/data.yaml --model yolo11n.pt --epochs 50 --device 0
Hasil: models/best.pt (dipakai backend) + metadata/training_run.json
Test split TIDAK dipakai untuk memilih hyperparameter; hanya val.
"""
import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--model", default="yolo11n.pt")  # varian kecil: baseline cepat
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="")  # "" otomatis, "0" GPU, "cpu"
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--name", default="kantukv2_yolo")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fraction", type=float, default=1.0, help="pakai sebagian data train (uji cepat di CPU)")
    ap.add_argument("--strong-aug", action="store_true", help="augmentasi kuat untuk pergeseran domain (kamera mobil -> webcam laptop)")
    ap.add_argument("--lr0", type=float, default=None, help="learning rate awal; pakai kecil (mis. 0.002) saat fine-tune dari best.pt")
    ap.add_argument("--freeze", type=int, default=0, help="bekukan N layer pertama (backbone) saat fine-tune dengan data sedikit")
    a = ap.parse_args()

    import ultralytics
    from ultralytics import YOLO

    models_dir = Path("models").resolve()
    model = YOLO(a.model)
    extra: dict = {}
    if a.strong_aug:  # cahaya, jarak, posisi kepala, dan latar webcam berbeda dari kamera dashboard
        extra.update(hsv_h=0.02, hsv_s=0.7, hsv_v=0.5, degrees=8, translate=0.15, scale=0.6, mosaic=1.0, mixup=0.1, erasing=0.3)
    if a.lr0 is not None:
        extra["lr0"] = a.lr0
    if a.freeze:
        extra["freeze"] = a.freeze
    res = model.train(
        data=str(a.data.resolve()), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device or None,
        patience=a.patience, fraction=a.fraction, project=str(models_dir / "runs"), name=a.name, seed=a.seed, exist_ok=True,
        fliplr=0.5, flipud=0.0,  # flip horizontal aman; vertikal merusak orientasi kepala
        **extra,
    )
    best = Path(res.save_dir) / "weights" / "best.pt"
    shutil.copy2(best, models_dir / "best.pt")

    meta = {
        "trained_on": datetime.now().isoformat(timespec="seconds"), "dataset": "kantukv2 (satu-satunya)",
        "data_yaml": str(a.data), "base_model": a.model, "ultralytics": ultralytics.__version__,
        "args": {k: v for k, v in vars(a).items() if k != "data"} | {"data": str(a.data)},
        "val_metrics": {k: float(v) for k, v in res.results_dict.items()},
        "weights": "models/best.pt",
    }
    Path("metadata").mkdir(exist_ok=True)
    Path("metadata/training_run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Selesai. Bobot: {models_dir / 'best.pt'}")


if __name__ == "__main__":
    main()
