"""Audit dataset YOLO (kantukv2) sebelum training. PRD §3.1 / Brief §4.3.

Memeriksa: data.yaml, jumlah gambar/anotasi per split dan kelas, label hilang/kosong/rusak,
gambar korup, duplikat persis (hash) di dalam dan ANTAR split (kebocoran), lalu menulis
metadata/dataset_manifest.json dan metadata/audit_samples.jpg.

Pakai: python scripts/audit_dataset.py datasets/kantukv2 [--version 1 --license "CC BY 4.0"]
"""
import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import cv2
import yaml

EXPECTED = ["eye_closed", "eye_open", "head_dropped", "head_straight", "no_yawn", "yawn"]
SPLITS = ["train", "valid", "test"]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def split_dir(root: Path, split: str) -> Path | None:
    for name in ([split, "val"] if split == "valid" else [split]):
        if (root / name / "images").is_dir():
            return root / name
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--version", default="?")
    ap.add_argument("--license", default="?")
    ap.add_argument("--url", default="https://universe.roboflow.com/testproject-8jvqn/kantukv2")
    ap.add_argument("--out", type=Path, default=Path("metadata"))
    a = ap.parse_args()

    cfg = yaml.safe_load((a.dataset / "data.yaml").read_text(encoding="utf-8"))
    names = cfg["names"]
    names = [names[k] for k in sorted(names)] if isinstance(names, dict) else list(names)
    report: dict = {
        "url": a.url, "version": a.version, "license": a.license, "audited_on": date.today().isoformat(),
        "classes": names, "missing_expected_classes": sorted(set(EXPECTED) - set(names)),
        "unexpected_classes": sorted(set(names) - set(EXPECTED)), "splits": {}, "issues": [],
    }
    hashes: dict[str, list[str]] = defaultdict(list)
    samples: list[tuple[Path, Path]] = []

    for sp in SPLITS:
        d = split_dir(a.dataset, sp)
        if d is None:
            report["splits"][sp] = None
            report["issues"].append(f"split '{sp}' tidak ada")
            continue
        imgs = sorted(p for p in (d / "images").iterdir() if p.suffix.lower() in IMG_EXT)
        cls_count: Counter = Counter()
        no_label = empty = bad_label = corrupt = 0
        for p in imgs:
            lp = d / "labels" / f"{p.stem}.txt"
            if cv2.imread(str(p)) is None:
                corrupt += 1
                continue
            hashes[hashlib.md5(p.read_bytes()).hexdigest()].append(f"{sp}/{p.name}")
            if not lp.exists():
                no_label += 1
                continue
            lines = [ln.split() for ln in lp.read_text().splitlines() if ln.strip()]
            if not lines:
                empty += 1
                continue
            ok = True
            for ln in lines:
                try:
                    c, *xywh = int(ln[0]), *map(float, ln[1:5])
                    assert 0 <= c < len(names) and len(ln) >= 5 and all(0 <= v <= 1 for v in xywh)
                    cls_count[names[c]] += 1
                except Exception:
                    ok = False
            bad_label += not ok
            if ok:
                samples.append((p, lp))
        report["splits"][sp] = {
            "images": len(imgs), "annotations": sum(cls_count.values()), "per_class": dict(cls_count),
            "images_without_label_file": no_label, "empty_label_files": empty, "invalid_label_files": bad_label,
            "corrupt_images": corrupt,
        }

    dup_within = [v for v in hashes.values() if len(v) > 1 and len({x.split("/")[0] for x in v}) == 1]
    leaks = [v for v in hashes.values() if len({x.split("/")[0] for x in v}) > 1]
    report["duplicates_within_split"] = len(dup_within)
    report["cross_split_leakage_exact"] = len(leaks)
    report["leakage_examples"] = leaks[:10]
    report["note"] = ("Hash hanya mendeteksi duplikat PERSIS. Frame berurutan/subjek sama tetap perlu dicek "
                      "visual (Roboflow augmentasi dapat membuat varian mirip di split berbeda).")
    tot = Counter()
    for s in report["splits"].values():
        if s:
            tot.update(s["per_class"])
    report["total_per_class"] = dict(tot)
    if tot:
        report["imbalance_ratio_max_min"] = round(max(tot.values()) / max(1, min(tot.values())), 2)
    if leaks:
        report["issues"].append(f"{len(leaks)} gambar identik ada di lebih dari satu split (kebocoran)")
    for c in report["missing_expected_classes"]:
        report["issues"].append(f"kelas diharapkan tidak ada di data.yaml: {c} (isi YOLO_LABEL_ALIASES di backend)")

    a.out.mkdir(exist_ok=True)
    (a.out / "dataset_manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    random.seed(0)
    tiles = []
    for p, lp in random.sample(samples, min(12, len(samples))):
        im = cv2.resize(cv2.imread(str(p)), (320, 320))
        for ln in lp.read_text().splitlines():
            c, x, y, w, h = int(ln.split()[0]), *map(float, ln.split()[1:5])
            x1, y1, x2, y2 = int((x - w / 2) * 320), int((y - h / 2) * 320), int((x + w / 2) * 320), int((y + h / 2) * 320)
            cv2.rectangle(im, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(im, names[c], (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
        tiles.append(im)
    if tiles:
        while len(tiles) % 4:
            tiles.append(tiles[0] * 0)
        rows = [cv2.hconcat(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
        cv2.imwrite(str(a.out / "audit_samples.jpg"), cv2.vconcat(rows))

    print(json.dumps({k: report[k] for k in ("classes", "splits", "total_per_class", "cross_split_leakage_exact", "issues")},
                     indent=2, ensure_ascii=False))
    print(f"\nManifest: {a.out / 'dataset_manifest.json'}  |  Sampel visual: {a.out / 'audit_samples.jpg'}")


if __name__ == "__main__":
    main()
