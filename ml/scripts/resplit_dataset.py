"""Split ulang kantukv2 berbasis KELOMPOK sumber (PRD §3.1: perbaiki split dari gambar kantukv2 yang sama).

Masalah: kantukv2 v2 berisi varian augmentasi (_aug0, _to_high_light, enh_) dari gambar sumber yang sama, dan
varian itu tersebar antar train/test (kebocoran). Skrip ini menyatukan train+test bawaan, mengelompokkan varian
berdasarkan kunci nama sumber, lalu membagi KELOMPOK (bukan gambar) ke train/valid/test.

Pakai: python scripts/resplit_dataset.py datasets/kantukv2 datasets/kantukv2_split --valid 0.15 --test 0.05 --seed 0
Kunci kelompok berbasis nama file, jadi hanya perkiraan; subjek yang sama dengan nama berbeda tetap bisa lolos.
"""
import argparse
import json
import random
import re
import shutil
from pathlib import Path

import yaml


def group_key(name: str) -> str:
    n = re.sub(r"_jpg\.rf\..*$", "", name)
    n = re.sub(r"(_to_high_light)+", "", n)
    n = re.sub(r"_aug\d+", "", n)
    return re.sub(r"^enh_", "", n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--valid", type=float, default=0.15)
    ap.add_argument("--test", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    items: dict[str, list[tuple[Path, Path]]] = {}
    for sp in ("train", "valid", "test"):
        d = a.src / sp
        if not (d / "images").is_dir():
            continue
        for p in sorted((d / "images").iterdir()):
            lp = d / "labels" / f"{p.stem}.txt"
            if lp.exists():
                items.setdefault(group_key(p.name), []).append((p, lp))

    groups = list(items.items())
    random.Random(a.seed).shuffle(groups)
    total = sum(len(v) for _, v in groups)
    quota = {"test": a.test * total, "valid": a.valid * total}
    assign: dict[str, list] = {"train": [], "valid": [], "test": []}
    counts = {"train": 0, "valid": 0, "test": 0}
    for key, files in groups:
        sp = "test" if counts["test"] < quota["test"] else "valid" if counts["valid"] < quota["valid"] else "train"
        assign[sp].append((key, files))
        counts[sp] += len(files)

    if a.dst.exists():
        raise SystemExit(f"{a.dst} sudah ada; hapus dulu bila ingin mengulang.")
    for sp, gl in assign.items():
        (a.dst / sp / "images").mkdir(parents=True)
        (a.dst / sp / "labels").mkdir(parents=True)
        for _, files in gl:
            for p, lp in files:
                shutil.copy2(p, a.dst / sp / "images" / p.name)
                shutil.copy2(lp, a.dst / sp / "labels" / lp.name)

    src_cfg = yaml.safe_load((a.src / "data.yaml").read_text(encoding="utf-8"))
    cfg = {"path": str(a.dst.resolve()), "train": "train/images", "val": "valid/images", "test": "test/images",
           "nc": src_cfg["nc"], "names": src_cfg["names"]}
    (a.dst / "data.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    meta = {
        "source": str(a.src), "seed": a.seed, "method": "group-aware split by source key (nama file)",
        "groups": len(groups), "images": counts, "ratios_target": {"valid": a.valid, "test": a.test},
        "note": "Hanya gambar kantukv2 v2 (train+test bawaan digabung). Kunci kelompok adalah perkiraan dari nama file.",
    }
    Path("metadata").mkdir(exist_ok=True)
    Path("metadata/resplit.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
