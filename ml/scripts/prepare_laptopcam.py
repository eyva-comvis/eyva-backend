"""Validasi dataset webcam laptop (hasil halaman /collect) dan buat data.yaml untuk training/evaluasi.

Struktur yang diharapkan di datasets/laptopcam/:  {train,valid,test}/{images,labels}/  (+ meta/*.json)

Keluaran:
  datasets/laptopcam/data.yaml        hanya domain webcam laptop (untuk mengukur performa di laptop)
  datasets/combined_data.yaml         kantukv2_split + laptopcam (untuk fine-tuning domain)

Pakai: python scripts/prepare_laptopcam.py [--laptop datasets/laptopcam] [--base datasets/kantukv2_split]
"""
import argparse
from collections import Counter, defaultdict
from pathlib import Path

import yaml

NAMES = ["eye_closed", "eye_open", "head_dropped", "head_straight", "no_yawn", "yawn"]
SPLITS = ["train", "valid", "test"]


def scan(root: Path) -> tuple[dict, list[str]]:
    info: dict = {}
    problems: list[str] = []
    take_splits: dict[str, set[str]] = defaultdict(set)
    for sp in SPLITS:
        imgs = sorted((root / sp / "images").glob("*.jpg")) if (root / sp / "images").is_dir() else []
        cls_count: Counter = Counter()
        bad = 0
        for p in imgs:
            lab = root / sp / "labels" / f"{p.stem}.txt"
            if not lab.exists():
                problems.append(f"{sp}: label hilang untuk {p.name}")
                bad += 1
                continue
            take_splits[p.stem.split("_")[0]].add(sp)
            for ln in lab.read_text().splitlines():
                parts = ln.split()
                try:
                    c = int(parts[0])
                    vals = list(map(float, parts[1:5]))
                    assert 0 <= c < len(NAMES) and len(parts) == 5 and all(0 <= v <= 1 for v in vals)
                    cls_count[NAMES[c]] += 1
                except Exception:
                    problems.append(f"{sp}: baris label tidak valid di {lab.name}: {ln!r}")
                    bad += 1
        info[sp] = {"images": len(imgs), "per_class": dict(cls_count), "bad": bad}
    for take, sps in take_splits.items():
        if len(sps) > 1:
            problems.append(f"KEBOCORAN: take '{take}' ada di beberapa split {sorted(sps)}; satu take harus di satu split saja")
    return info, problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--laptop", type=Path, default=Path("datasets/laptopcam"))
    ap.add_argument("--base", type=Path, default=Path("datasets/kantukv2_split"))
    a = ap.parse_args()
    if not a.laptop.is_dir():
        raise SystemExit(f"{a.laptop} tidak ada. Rekam dulu lewat halaman /collect (lihat docs/DATASET_LAPTOPCAM.md).")

    info, problems = scan(a.laptop)
    print(f"Dataset {a.laptop}")
    for sp in SPLITS:
        i = info[sp]
        print(f"  {sp:5}: {i['images']:5} gambar | " + ", ".join(f"{k} {v}" for k, v in sorted(i["per_class"].items())))
    tot = sum(info[s]["images"] for s in SPLITS)
    for sp in ("train", "valid", "test"):
        if info[sp]["images"] == 0:
            problems.append(f"split '{sp}' kosong")
    if info["train"]["images"] < 300:
        problems.append(f"train hanya {info['train']['images']} gambar; sarankan >= 300 (beberapa take, kondisi berbeda)")
    counts = [sum(info["train"]["per_class"].get(n, 0) for n in pair) for pair in (("eye_open", "eye_closed"), ("no_yawn", "yawn"), ("head_straight", "head_dropped"))]
    for n in NAMES:
        if info["train"]["per_class"].get(n, 0) == 0:
            problems.append(f"kelas '{n}' tidak ada di train")

    own = {"path": str(a.laptop.resolve()), "train": "train/images", "val": "valid/images", "test": "test/images", "nc": len(NAMES), "names": NAMES}
    (a.laptop / "data.yaml").write_text(yaml.safe_dump(own, sort_keys=False), encoding="utf-8")
    base = a.base.resolve()
    combined = {
        "train": [str(base / "train" / "images"), str((a.laptop / "train" / "images").resolve())],
        "val": [str(base / "valid" / "images"), str((a.laptop / "valid" / "images").resolve())],
        "test": str((a.laptop / "test" / "images").resolve()),  # uji akhir di domain laptop
        "nc": len(NAMES), "names": NAMES,
    }
    out = Path("datasets/combined_data.yaml")
    out.write_text(yaml.safe_dump(combined, sort_keys=False), encoding="utf-8")
    print(f"\nDitulis: {a.laptop / 'data.yaml'} dan {out}  (total {tot} gambar laptop)")
    if problems:
        print("\nPERHATIAN:")
        for p in problems[:40]:
            print("  -", p)
    else:
        print("\nTidak ada masalah terdeteksi. Periksa juga pratinjau kotak di /collect sebelum training.")


if __name__ == "__main__":
    main()
