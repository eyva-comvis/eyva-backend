"""Unduh kantukv2 dari Roboflow ke datasets/kantukv2 (format YOLO).

API key dibaca dari environment, jangan ditulis di kode:
  PowerShell:  $env:ROBOFLOW_API_KEY = "<key-anda>"; python scripts/download_dataset.py --version 2
Butuh: pip install roboflow
"""
import argparse
import os
import sys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, required=True, help="nomor versi dataset (kantukv2 punya 2 versi)")
    ap.add_argument("--format", default="yolov11")
    ap.add_argument("--out", default="datasets/kantukv2")
    a = ap.parse_args()
    key = os.environ.get("ROBOFLOW_API_KEY")
    if not key:
        sys.exit("Set ROBOFLOW_API_KEY di environment dulu.")
    from roboflow import Roboflow

    ds = Roboflow(api_key=key).workspace("testproject-8jvqn").project("kantukv2").version(a.version).download(a.format, location=a.out)
    print("Tersimpan di:", ds.location)


if __name__ == "__main__":
    main()
