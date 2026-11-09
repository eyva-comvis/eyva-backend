# Eyva Backend — Smart Study Assistant (FastAPI + YOLO)

Repo backend + model. Frontend ada di repo terpisah (`eyva-frontend`) dan memakai API ini lewat `NEXT_PUBLIC_API_URL`.
Spesifikasi: `docs/SMART_STUDY_ASSISTANT_PRD_v1.md` dan `docs/SMART_STUDY_ASSISTANT_Project_Brief_v2.md`.

## Isi repo
- `app/`, `tests/`, `Dockerfile`: service FastAPI (deploy Railway, root repo = root service).
- `models/best.pt`: bobot YOLO11n yang dipakai produksi.
- `ml/`: skrip training/evaluasi (`ml/scripts`), notebook Colab (`ml/notebooks`), laporan (`ml/metadata`). Jalankan dari root repo, mis. `python ml/scripts/train_yolo.py ...`. Dataset tidak di-commit (`datasets/`).
- `docs/`: PRD, Project Brief, setup Supabase, tasklist.

## Menjalankan

```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Dokumentasi interaktif: http://localhost:8000/docs (dipakai tim frontend sebagai kontrak).
Tes: `pytest -q`

> Jalankan **1 worker** uvicorn: state sesi disimpan di memori proses.

## Mode inferensi
- `INFERENCE_BACKEND=mock` (default dev lokal tanpa model): tanpa model. `MOCK_SCENARIO=drowsy` memicu alert untuk uji frontend.
- `INFERENCE_BACKEND=remote`: memanggil API model eksternal (Afin di Railway) via `httpx`. Ringan, cepat, tidak memerlukan PyTorch/OpenCV lokal.
- `INFERENCE_BACKEND=yolo`: inferensi YOLO lokal dengan bobot model (membutuhkan PyTorch + `requirements-ml.txt`).

## Memakai model Remote (API Afin di Railway)
1. Cukup install dependensi ringan:
   ```bash
   pip install -r requirements.txt
   ```
2. Atur konfigurasi di `.env`:
   ```env
   INFERENCE_BACKEND=remote
   MODEL_API_URL=https://model-production-eyva.up.railway.app
   MODEL_API_KEY=<kunci-api-dari-tim-model>
   MODEL_API_TIMEOUT=10.0
   ```
3. Jalankan server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
4. Karakteristik & Kontrak:
   - Request dikirim sebagai raw bytes dengan header `X-API-Key` dan `Content-Type: image/jpeg` (atau `image/png` jika header PNG).
   - Bounding box piksel `[x1, y1, x2, y2]` dari model Afin dinormalisasi otomatis ke `[x1/W, y1/H, x2/W, y2/H]` (rentang 0..1) sesuai kontrak frontend Eyva.
   - Deteksi difilter terhadap 6 kelas yang dikenali pipeline: `eye_open`, `eye_closed`, `yawn`, `no_yawn`, `head_straight`, `head_dropped`.
   - Toleran terhadap error: status 422 (gambar rusak), 503 (worker model sibuk), 408/timeout, atau gangguan jaringan akan di-log dan mengembalikan `[]` (skip frame tanpa 500 ke frontend). Status 401 menghasilkan log error autentikasi yang jelas.
   - Nilai `MODEL_API_KEY` tidak pernah dibocorkan ke log maupun endpoint `GET /health` / `info()`.

## Memakai model YOLO Lokal
1. Install dependensi ML (menarik PyTorch CPU, Ultralytics, OpenCV):
   ```bash
   pip install -r requirements-ml.txt
   ```
2. Letakkan bobot model lokal:
   - Jika memiliki bobot `smartstudy_yolo11n_v2.pt`, letakkan di `models/` dan set:
     ```env
     INFERENCE_BACKEND=yolo
     MODEL_PATH=models/smartstudy_yolo11n_v2.pt
     ```
   - Atau letakkan bobot sebagai `models/best.pt` (default `MODEL_PATH=models/best.pt`).
3. Jika nama kelas di model berbeda, isi `YOLO_LABEL_ALIASES` di `.env`, misal `{"closed_eye":"eye_closed"}`.
4. Uji tanpa server:
   ```bash
   python scripts/check_inference.py sample.jpg --runs 30 --save out.jpg
   ```
5. Perilaku: server **gagal start dengan pesan jelas** (`RuntimeError`) bila file bobot tidak ditemukan atau kelas tidak cocok.

## Build Docker (Railway & Deployment)
Dockerfile didesain modular dan ramah mode `remote`:
- **Default (Ringan, ~150MB)**: Hanya menginstall `requirements.txt` tanpa PyTorch:
  ```bash
  docker build -t eyva-backend .
  ```
- **Mode Lokal ML (dengan PyTorch CPU + Ultralytics)**:
  ```bash
  docker build --build-arg INSTALL_ML=true -t eyva-backend .
  ```

## Struktur
```
app/
  main.py              app, CORS, lifespan (model dimuat sekali)
  core/config.py       Settings dari .env (threshold sementara)
  schemas/models.py    kontrak API (Pydantic)
  api/                 sessions.py (siklus Pomodoro), predict.py (frame + alert), deps.py
  services/
    inference.py       mock / YOLO
    temporal.py        blink, yawn, eye closure, head dropped
    decision_engine.py status + skor heuristik
    alert_machine.py   state machine 2 tahap
    session_store.py   state sesi in-memory
    insights.py        rekomendasi (fallback + LLM P1)
  db/schema.sql        skema Supabase (belum terhubung)
tests/
```

## Status
- [x] Kontrak API + semua endpoint PRD (in-memory), mock inference, state machine, tes
- [ ] Integrasi `best.pt` (setelah model selesai)
- [ ] Kalibrasi threshold dari uji webcam
- [x] Persistensi Supabase (write-behind, diuji dengan fake client; belum diuji ke proyek Supabase asli)
- [ ] LLM insight

## Mengaktifkan Supabase
1. Buat proyek di supabase.com, jalankan `app/db/schema.sql` di SQL Editor.
2. Isi `SUPABASE_URL` dan `SUPABASE_SERVICE_KEY` (service_role, **hanya di backend**, jangan ke frontend) di `.env`.
3. Jalankan server; `GET /health` harus menampilkan `"persistence": true`.
Tanpa kredensial, backend tetap jalan in-memory (persistence: false).

## Riwayat sesi (FR-16)
- `GET /sessions?limit=20&offset=0` — daftar sesi terbaru dulu (memori + DB digabung; memori menang karena lebih baru).
- `GET /sessions/{id}/summary` dan `POST /sessions/{id}/insights` — jika sesi tidak ada di memori (mis. setelah restart), dibaca dari DB.
- Status `INTERRUPTED` = tercatat ACTIVE di DB tetapi server restart di tengah sesi.
- Sesi lama hanya bisa dibaca; endpoint yang mengubah state (blocks, predict, dll.) menjawab 404.
- Belum ada autentikasi, jadi daftar ini **global** (semua sesi terlihat). Filter per `user_id` menyusul jika login dipakai.

Tambahan di luar daftar PRD: `POST /sessions/{id}/blocks/{block_id}/resume` ("Saya siap melanjutkan").
