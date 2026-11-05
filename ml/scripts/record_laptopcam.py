"""Perekam dataset webcam laptop (versi skrip dari halaman /collect; protokol dan aturan label sama).

Webcam -> model YOLO yang ada memberi kotak (kepala/mata/mulut); protokol terpandu menentukan kelasnya. Frame tanpa kotak
yang layak dibuang. Hasil: datasets/laptopcam/{train,valid,test}/{images,labels} + meta/<take>.json.

Pakai (jendela pratinjau muncul; tekan SPASI untuk memulai tiap take, Q untuk berhenti):
  python scripts/record_laptopcam.py --plan "lampu-terang:train:Lampu menyala terang" "redup:train:Redupkan lampu"
Cek kamera/model saja tanpa menyimpan:  python scripts/record_laptopcam.py --check
"""
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import cv2

CLASSES = ["eye_closed", "eye_open", "head_dropped", "head_straight", "no_yawn", "yawn"]  # urutan = data.yaml kantukv2
GROUPS = {"eye": ["eye_open", "eye_closed"], "mouth": ["no_yawn", "yawn"], "head": ["head_straight", "head_dropped"]}
# (id, judul, petunjuk, detik, override kelas)
STEPS = [
    ("neutral", "Lihat layar", "Mata terbuka, mulut tertutup, kepala lurus", 8, {"eye": "eye_open", "mouth": "no_yawn", "head": "head_straight"}),
    ("eyes-closed", "Pejamkan mata", "Mata terpejam, kepala lurus, mulut tertutup", 7, {"eye": "eye_closed", "mouth": "no_yawn", "head": "head_straight"}),
    ("yawn", "Menguap lebar", "Buka mulut lebar seperti menguap, tahan, ulangi", 9, {"mouth": "yawn", "head": "head_straight"}),
    ("talk", "Bicara / senyum", "Bicara atau senyum mulut terbuka (BUKAN menguap)", 8, {"eye": "eye_open", "mouth": "no_yawn", "head": "head_straight"}),
    ("head-down", "Kepala menunduk", "Tunduk seperti mengantuk, wajah tetap terlihat", 7, {"head": "head_dropped", "mouth": "no_yawn"}),
]
FRAME_S = 0.35


def slug(s: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", s.strip().lower())) or "take"


def detect(model, frame, imgsz: int, conf: float):
    r = model.predict(frame, imgsz=imgsz, conf=conf, verbose=False)[0]
    out = []
    for b, c, k in zip(r.boxes.xyxyn.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
        out.append((r.names[int(k)], float(c), b))
    return out


def build_labels(dets, override, min_conf=0.3, min_unsure=0.5):
    boxes = []
    for group, names in GROUPS.items():
        best = None
        for label, conf, bbox in dets:
            if label in names and conf >= min_conf and (best is None or conf > best[1]):
                best = (label, conf, bbox)
        if best is None:
            return None
        forced = override.get(group)
        if forced is None and best[1] < min_unsure:
            return None
        x1, y1, x2, y2 = (min(max(v, 0.0), 1.0) for v in best[2])
        if x2 - x1 < 0.01 or y2 - y1 < 0.01:
            return None
        boxes.append((forced or best[0], (x1, y1, x2, y2)))
    lines = [f"{CLASSES.index(c)} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}" for c, (x1, y1, x2, y2) in boxes]
    return lines, boxes


def beep(freq=880, ms=150):
    try:
        import winsound
        winsound.Beep(freq, ms)
    except Exception:
        pass


def draw(frame, title, hint, remaining, boxes, saved, skipped):
    h, w = frame.shape[:2]
    img = frame.copy()
    for cls, (x1, y1, x2, y2) in boxes or []:
        cv2.rectangle(img, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), (34, 197, 94), 2)
        cv2.putText(img, cls, (int(x1 * w) + 3, max(14, int(y1 * h) - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (34, 197, 94), 1)
    cv2.rectangle(img, (0, 0), (w, 70), (0, 0, 0), -1)
    cv2.putText(img, title, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.putText(img, hint, (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    cv2.putText(img, f"{remaining}   saved {saved}  skipped {skipped}", (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return img


def wait_auto(cap, win, text, hint, seconds):
    """Mode otomatis: beri waktu untuk mengatur cahaya/posisi, lalu mulai sendiri. Q = berhenti."""
    beep(520, 300)
    t_end = time.time() + seconds
    while time.time() < t_end:
        ok, frame = cap.read()
        if ok:
            cv2.imshow(win, draw(frame, text, hint, f"mulai dalam {t_end - time.time():.0f}s", [], 0, 0))
        if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
            return False
    return True


def wait_key(cap, win, text, hint):
    """Tampilkan pratinjau sampai SPASI (mulai) atau Q (berhenti)."""
    while True:
        ok, frame = cap.read()
        if ok:
            cv2.imshow(win, draw(frame, text, hint + "  |  SPASI = mulai, Q = berhenti", "", [], 0, 0))
        k = cv2.waitKey(30) & 0xFF
        if k == ord(" "):
            return True
        if k in (ord("q"), 27):
            return False


def run_take(cap, model, win, out: Path, take: str, split: str, imgsz: int, conf: float) -> dict:
    name = slug(take)
    for sub in ("images", "labels"):
        (out / split / sub).mkdir(parents=True, exist_ok=True)
    (out / "meta").mkdir(parents=True, exist_ok=True)
    saved, classes, skipped = {}, {}, 0
    for sid, title, hint, secs, override in STEPS:
        beep(660, 200)
        for c in (3, 2, 1):  # hitung mundur
            t_end = time.time() + 1.0
            while time.time() < t_end:
                ok, frame = cap.read()
                if ok:
                    cv2.imshow(win, draw(frame, f"{title}  ({c})", hint, "bersiap", [], sum(saved.values()), skipped))
                cv2.waitKey(1)
        beep(1100, 250)
        t0, n = time.time(), 0
        while time.time() - t0 < secs:
            tick = time.time()
            ok, frame = cap.read()
            if not ok:
                continue
            lab = build_labels(detect(model, frame, imgsz, conf), override)
            boxes = lab[1] if lab else []
            cv2.imshow(win, draw(frame, title, hint, f"{secs - (time.time() - t0):.0f}s", boxes, sum(saved.values()), skipped))
            if lab:
                fid = f"{name}_{sid}_{n:03d}"
                n += 1
                cv2.imwrite(str(out / split / "images" / f"{fid}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                (out / split / "labels" / f"{fid}.txt").write_text("\n".join(lab[0]) + "\n", encoding="utf-8")
                saved[sid] = saved.get(sid, 0) + 1
                for c, _ in lab[1]:
                    classes[c] = classes.get(c, 0) + 1
            else:
                skipped += 1
            if cv2.waitKey(max(1, int((FRAME_S - (time.time() - tick)) * 1000))) & 0xFF in (ord("q"), 27):
                raise KeyboardInterrupt
    beep(880, 400)
    meta = {"take": name, "split": split, "date": datetime.now().isoformat(timespec="seconds"), "saved": saved,
            "classes": classes, "skipped": skipped, "steps": [{"id": s[0], "override": s[4]} for s in STEPS], "source": "record_laptopcam.py"}
    (out / "meta" / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", nargs="*", default=[], help="take:split[:catatan kondisi] ...")
    ap.add_argument("--out", type=Path, default=Path("datasets/laptopcam"))
    ap.add_argument("--model", default="models/best.pt")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--imgsz", type=int, default=416)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--auto-wait", type=int, default=0, help="detik jeda sebelum tiap take lalu mulai otomatis (tanpa tombol)")
    ap.add_argument("--check", action="store_true", help="hanya uji kamera + model, tidak menyimpan")
    a = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(a.model)
    cap = cv2.VideoCapture(a.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit("Kamera tidak bisa dibuka (dipakai aplikasi lain, atau izin kamera untuk aplikasi desktop dimatikan).")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    for _ in range(45):  # buang frame awal (auto-exposure butuh ~1,5 detik)
        cap.read()
    ok, frame = cap.read()
    if not ok:
        raise SystemExit("Kamera terbuka tetapi tidak menghasilkan frame.")
    print(f"Kamera OK: {frame.shape[1]}x{frame.shape[0]}, kecerahan rata-rata {frame.mean():.0f}/255 (idealnya >70)")

    if a.check:
        dets = detect(model, frame, a.imgsz, a.conf)
        print("Deteksi:", [(n, round(c, 2)) for n, c, _ in dets] or "tidak ada wajah/objek terdeteksi")
        cv2.imwrite(str(Path("logs") / "camera_check.jpg"), frame)
        print("Cuplikan: logs/camera_check.jpg")
        cap.release()
        return

    win = "Loopa - rekam data webcam"
    cv2.namedWindow(win)
    results = []
    try:
        for item in a.plan:
            take, split, *rest = item.split(":", 2)
            if split not in ("train", "valid", "test"):
                raise SystemExit(f"split tidak valid di '{item}'")
            title, note = f"Take '{take}' ({split})", (rest[0] if rest else "Atur posisi & cahaya")
            if not (wait_auto(cap, win, title, note, a.auto_wait) if a.auto_wait else wait_key(cap, win, title, note)):
                break
            results.append(run_take(cap, model, win, a.out, take, split, a.imgsz, a.conf))
            print(f"Take {take}: {sum(results[-1]['saved'].values())} gambar, {results[-1]['skipped']} dibuang, kelas {results[-1]['classes']}")
    except KeyboardInterrupt:
        print("Dihentikan pengguna; frame yang sudah tersimpan dipertahankan.")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
