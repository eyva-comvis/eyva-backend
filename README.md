# Backend — Smart Study Assistant (FastAPI)

## Menjalankan

```bash
cd backend
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
- `INFERENCE_BACKEND=mock` (default): tanpa model. `MOCK_SCENARIO=drowsy` memicu alert untuk uji frontend.
- `INFERENCE_BACKEND=yolo`: lihat bagian "Memakai model YOLO" di bawah.

## Memakai model YOLO
1. `pip install -r requirements-ml.txt` (menarik torch, besar), taruh `best.pt` di `models/` (root repo).
2. Set `INFERENCE_BACKEND=yolo` di `.env`. Jika nama kelas di `data.yaml` beda, isi `YOLO_LABEL_ALIASES`.
3. Uji dulu tanpa server: `python scripts/check_inference.py sample.jpg --runs 30 --save out.jpg`
   (cetak deteksi, latensi rata-rata/p95, dan gambar beranotasi).
4. Jalankan server; `GET /health` menampilkan kelas model yang dimuat.

Perilaku: server **gagal start dengan pesan jelas** bila `best.pt` tidak ada atau tidak satu pun kelas model dikenali
(tidak diam-diam jatuh ke mock). Kelas di luar enam kelas pipeline dibuang. JPEG rusak dianggap tanpa deteksi.
Model dipanggil dengan lock (tidak paralel), jadi **frontend harus menunggu respons sebelum mengirim frame berikutnya**.
`YOLO_CONF` (0.25) hanya batas bawah deteksi; ambang keputusan sebenarnya `MIN_CONF` di `temporal.py` (0.4, sementara).

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
