# TASKLIST — Smart Study Assistant (Loopa)

Acuan: `SMART_STUDY_ASSISTANT_PRD_v1.md` (PRD) dan `SMART_STUDY_ASSISTANT_Project_Brief_v2.md` (Brief).
Terakhir diperbarui: 30 Oktober 2026. Target MVP: 13 November 2026.

Legenda: ✅ sudah dan diuji · 🟡 ada tetapi belum diuji penuh / masih sementara · ⬜ belum dikerjakan

## Pembaruan terbaru (30 Okt, sore)

- ✅ **Supabase:** proyek `loopa` dibuat, skema + RLS dijalankan, Site URL/Redirect URLs diatur (lihat `docs/SETUP_AUTH_SUPABASE.md`). ⬜ Masih perlu: aktifkan provider Google (Client ID/secret dari Anda), isi `SUPABASE_SERVICE_KEY` di Railway, dan env `NEXT_PUBLIC_SUPABASE_*` di Vercel.
- ✅ **Auth (kode):** login Google/email via Supabase, verifikasi JWT di backend, sesi/riwayat/statistik per pengguna, profil (username/avatar) di `/profile`. 🟡 Belum diuji dengan akun Google sungguhan (menunggu provider Google).
- ✅ **UI mengikuti Figma:** Start Session + izin kamera, Focus Session (ring timer, Pause, panel musik), modal saran, **Mandatory Break**, **Session Wrap** (refleksi Good/Okay/Tough), History (tabel), Statistics (grafik, streak, insight), Login.
- ✅ **Musik latar** generatif (4 soundtrack; sedikit lebih cerah saat ada indikasi kantuk; volume turun saat alert).
- ✅ **Alat dataset webcam laptop:** `/collect`, `scripts/prepare_laptopcam.py`, opsi `--strong-aug` (lihat `docs/DATASET_LAPTOPCAM.md`). ⬜ Data webcam belum direkam; model belum dilatih ulang.
- ✅ **Hosting dari GitHub** (`Admrlrdj/loopa`): lihat bagian 3 di `docs/SETUP_AUTH_SUPABASE.md`.
- ✅ Backend 50 tes lulus.

Alamat produksi: web https://loopa-smart-study.vercel.app · backend https://loopa-backend-production-44f3.up.railway.app

---

## 1. Yang sudah dilaksanakan

### Dataset dan model
- [x] ✅ Dataset tunggal kantukv2 **v2** (3.841 gambar, 6 kelas, CC BY 4.0), versi dan lisensi dicatat di `metadata/dataset_manifest.json`.
- [x] ✅ Audit dataset (kelas, distribusi, label rusak, duplikat persis, sampel visual).
- [x] ✅ Temuan kebocoran: 109 dari 192 gambar test punya varian dari gambar sumber yang sama di train. Split ulang berbasis kelompok: train 3.069 / valid 577 / test 195 (`scripts/resplit_dataset.py`, `metadata/resplit.json`).
- [x] ✅ Fine-tuning YOLO11n pretrained (12 epoch, `imgsz` 320, 35% data, CPU).
- [x] ✅ Evaluasi test set: precision 0,885 · recall 0,920 · mAP50 0,959 · mAP50-95 0,622, plus per kelas dan latensi (`metadata/eval_report.json`).
- [x] ✅ `models/best.pt` terpasang di backend lokal dan Railway.
- [x] ✅ Skrip: `download_dataset`, `audit_dataset`, `resplit_dataset`, `train_yolo`, `evaluate_yolo`, dan **`replay_video`** (kalibrasi dari video, baru). Notebook Colab tersedia.

### Backend (FastAPI)
- [x] ✅ Semua endpoint PRD §10, ditambah `blocks/{id}/resume`, `break-tip`, dan `GET /`.
- [x] ✅ Analisis temporal (blink, yawn, eye closure, head dropped) dengan timestamp nyata.
- [x] ✅ Decision engine: `NORMAL`, `POSSIBLE_DROWSINESS`, `DROWSY_NEED_REST`, `UNCERTAIN` (tanpa wajah tidak dianggap Normal).
- [x] ✅ State machine alert dua tahap (recheck, cooldown, reset episode).
- [x] ✅ Idempotensi `request_id` dan respons alert (AT-16 sisi backend).
- [x] ✅ Skema DB PRD §11 (`schema.sql`), CORS untuk localhost/127.0.0.1 di port mana pun.
- [x] ✅ 36 tes otomatis lulus.

### Frontend (Next.js)
- [x] ✅ Setup Pomodoro (belajar 1–180, istirahat 1–60), timer berbasis timestamp dengan akuntansi jeda.
- [x] ✅ Webcam hanya di fase belajar, fallback bila kamera ditolak, penanganan sesi hilang (404) tanpa membanjiri backend.
- [x] ✅ Alert 1, Alert 2 (Lanjutkan/Akhiri), modal saran, konfirmasi akhiri sesi, tombol suara.
- [x] ✅ Break timer, Summary, History, Statistics.
- [x] ✅ Desain Figma: Inter, Tabler Icons, aset SVG resmi, palet Loopa; teks UI berbahasa Inggris.

### AI
- [x] ✅ Rekomendasi di Summary dan tip di halaman Break (OpenRouter: nemotron-3-ultra, cadangan Gemma). Hanya metrik terstruktur yang dikirim. Fallback teks aturan bila LLM gagal. Label sementara `[temp] AI model`.

### Infrastruktur dan dokumentasi
- [x] ✅ Struktur folder sesuai Brief §17, `README.md`, deploy Vercel + Railway terhubung.

---

## 2. Yang belum dilaksanakan atau masih sebagian

### Wajib PRD / Definition of Done (§18)
- [ ] ⬜ **Kalibrasi temporal analysis** dari uji webcam (PRD §17). → Panduan **P1**.
- [ ] 🟡 **Penanganan NO_FACE** diuji di kamera asli (AT-12). → **P2**.
- [ ] 🟡 **Suara Alert 1/2** dipastikan terdengar di browser asli (AT-13, FR-06). → **P3**.
- [ ] 🟡 **Break timer sesuai konfigurasi** (AT-10, AT-11). → **P4**.
- [ ] ⬜ **UAT AT-01…AT-16 dan demo end-to-end**. → **P5**.
- [ ] ⬜ **Supabase asli** (PRD §9). → **P6.2**.
- [ ] ⬜ **Evaluasi temporal pada video** dengan anotasi manual (Brief §16.2). → **P1** (memakai `replay_video.py`).
- [ ] ⬜ Notebook terpisah `01_dataset_audit`, `02_yolo_training`, `03_model_evaluation` (baru satu notebook gabungan) dan laporan audit dataset tertulis.

### Model
- [ ] 🟡 Latih penuh di GPU (saat ini 35% data, 12 epoch, CPU). → **P6.4**.
- [ ] 🟡 Uji generalisasi ke webcam laptop beberapa pengguna/cahaya/jarak (Brief §4.4). → **P1**.

### Ketahanan dan UX
- [ ] 🟡 Refresh/tab ditutup dan tab di background (PRD §6.3). → **P6.1**.
- [ ] 🟡 Aksesibilitas modal: focus trap, Esc (NFR-08). → **P6.3**.
- [ ] 🟡 Anti klik ganda di frontend (AT-16 sisi UI).
- [ ] ⬜ Cek visual Break, History, Statistics, Summary setelah restyle; badge tren dan panel suara latar dari Figma.

### Keamanan, proses, dokumentasi
- [ ] 🟡 Tanpa autentikasi; riwayat global (NFR-02). Login, username, avatar, riwayat per pengguna adalah bagian PM.
- [ ] ⬜ Kunci versi library (`requirements.txt` masih `>=`) dan unggah artefak ke Drive. → **P6.5**, **P6.6**.
- [ ] ⬜ Ukur latensi end-to-end Vercel→Railway (NFR-07). → **P6.7**.
- [ ] ⬜ Hapus label `[temp] AI model` sebelum final. → **P6.8**.

### Perbaikan kode yang disarankan (belum dikerjakan)
1. Durasi minimum/hysteresis untuk blink: satu frame `eye_closed` yang berkedip saat ini terhitung kedipan (terlihat di video sintetis; hilang saat `min_conf` 0,6).
2. Pindahkan `MIN_CONF`, `YAWN_MIN_SECONDS`, `HEAD_DROPPED_MIN_SECONDS` ke `Settings` (env) supaya bisa diubah di Railway tanpa edit kode.
3. Banner "Wajah tidak terlihat" di UI bila `NO_FACE` berlangsung > 10 detik.
4. Minta izin `Notification` (kode memakainya hanya bila sudah `granted`, tetapi tidak pernah meminta).
5. Focus trap dan tombol Esc pada modal; debounce tombol aksi.
6. Logging per-frame opsional untuk kalibrasi di produksi.

---

## 3. Panduan step-by-step

> Jalankan semua perintah dari folder `loopa`. Python backend: `backend\.venv\Scripts\python.exe`.

### P1. Kalibrasi temporal analysis

**Tujuan:** mengganti threshold sementara dengan nilai yang didukung data, sesuai PRD §17 dan Brief §16.2.

**Cara kerja pipeline saat ini (agar hasil bisa dibaca):**
- Frame dikirim ±1–2 per detik (`FRAME_INTERVAL_MS = 700` di `frontend/src/app/session/page.tsx`, ditambah waktu inferensi dan jaringan). Kedipan normal (0,1–0,4 dtk) hampir tidak tertangkap pada laju ini. Akurasi hitungan *blink* dibatasi laju sampling, bukan hanya model.
- `face_detected` = ada deteksi `eye_open` atau `eye_closed` dengan confidence ≥ `MIN_CONF` (0,4).
- *Eye closure* dihitung bila mata tertutup terus ≥ `EYE_CLOSURE_SECONDS` (1,5 dtk). Tertutup lebih singkat lalu terbuka dihitung *blink*.
- Skor = `min(closed_s / EYE_CLOSURE_SECONDS, 1) × 60` + 15 bila ada *yawn* dalam 60 dtk terakhir + 15 bila kepala menunduk ≥ 2 dtk. Status `DROWSY_NEED_REST` **hanya** bila mata tertutup ≥ `EYE_CLOSURE_SECONDS`; `POSSIBLE_DROWSINESS` bila skor ≥ 25. Yawn atau kepala menunduk saja tidak memicu alert.
- Alert 1 muncul setelah waktu `DROWSY` terakumulasi ≥ `ALERT1_CONFIRM_SECONDS` (3 dtk). Setelah "Got it", Alert 2 muncul bila `DROWSY` terakumulasi lagi ≥ `ALERT2_RECHECK_SECONDS` (5 dtk). Bila status kembali `NORMAL`, episode di-reset.
- Cooldown (`ALERT_COOLDOWN_SECONDS`, 30 dtk) hanya berlaku setelah memilih lanjut di Alert 2, bukan setelah Alert 1.

**Parameter:**

| Parameter | Nilai awal | Lokasi | Efek |
|---|---|---|---|
| `YOLO_CONF` | 0,25 | env | Batas bawah deteksi dari model |
| `MIN_CONF` | 0,4 | `backend/app/services/temporal.py` | Batas keputusan; naikkan untuk meredam deteksi palsu |
| `EYE_CLOSURE_SECONDS` | 1,5 | env | Lama mata tertutup = *closure* |
| `YAWN_MIN_SECONDS` | 1,0 | `temporal.py` | Lama menguap agar dihitung |
| `HEAD_DROPPED_MIN_SECONDS` | 2,0 | `temporal.py` | Lama menunduk agar menambah skor |
| `ALERT1_CONFIRM_SECONDS` | 3,0 | env | Kantuk berlanjut sebelum Alert 1 |
| `ALERT2_RECHECK_SECONDS` | 5,0 | env | Kantuk berlanjut sebelum Alert 2 |
| `ALERT_COOLDOWN_SECONDS` | 30 | env | Jeda setelah memilih lanjut |

**Langkah:**

1. **Siapkan perekaman.** Pakai aplikasi *Camera* Windows (mode video) atau OBS pada laptop yang sama dengan demo. Resolusi ≥ 640×480. Rekam di tempat dan cahaya demo. Minta minimal 2–3 orang jika bisa (Brief §4.4).
2. **Rekam 8 video**, tiap 60–90 detik. Buat skrip tertulis agar waktu kejadian jelas:

   | Video | Isi | Tujuan |
   |---|---|---|
   | V1 Normal | Membaca layar, berkedip alami, tidak menguap | Harus **0 alert** |
   | V2 Mata tertutup | Tutup mata 3 dtk × 3 kali, jeda 10 dtk | Eye closure & Alert 1 |
   | V3 Menguap | Menguap lebar 5 kali, jeda 15 dtk | Hitungan yawn, tanpa hitung ganda |
   | V4 Menunduk | Menunduk 3–5 dtk × 3 kali; juga membaca buku di meja | Head dropped; tidak langsung alert |
   | V5 Bicara | Bicara/ mengobrol 30 dtk | Tidak terhitung menguap |
   | V6 Tanpa wajah | Keluar frame / tutup lensa 5 dtk × 3 | `NO_FACE`, tanpa alert |
   | V7 Cahaya | Redup dan backlight | Ketahanan |
   | V8 Kacamata/ topi | Berkacamata atau topi | Ketahanan |
   | V9 Kantuk beruntun | Tutup mata terus ≥ 15 dtk | Alert 1 → Alert 2 |

3. **Catat kebenaran (ground truth).** Putar tiap video dan catat waktu kejadian ke `metadata/video/<nama>_truth.csv`:
   ```csv
   event,start_s,end_s
   eye_closure,12.0,15.2
   yawn,30.5,33.0
   no_face,50.0,55.0
   ```
   `event` ∈ `blink`, `eye_closure`, `yawn`, `head_dropped`, `no_face`.
4. **Putar ulang lewat pipeline asli:**
   ```bash
   backend\.venv\Scripts\python.exe -I scripts/replay_video.py metadata/video/V2.mp4 --sample-fps 2 --truth metadata/video/V2_truth.csv --out metadata/video/V2_replay
   ```
   Keluaran: ringkasan di layar, `V2_replay_timeline.csv` (status, skor, counter per frame) dan `V2_replay_summary.json` (hitungan vs kebenaran, daftar alert dengan waktunya). `--sample-fps` meniru laju kirim produksi; coba juga `1` dan `3`.
5. **Coba beberapa threshold sekaligus:**
   ```bash
   backend\.venv\Scripts\python.exe -I scripts/replay_video.py metadata/video/V1.mp4 --sweep
   ```
   Tabel menampilkan hitungan blink/yawn/closure dan waktu alert untuk kombinasi `eye_closure_seconds` × `min_conf`.
6. **Baca hasil dan putuskan** memakai tabel gejala berikut:

   | Gejala | Ubah | Arah |
   |---|---|---|
   | Eye closure nyata tidak terhitung | `EYE_CLOSURE_SECONDS`, `MIN_CONF` | Turunkan (≥ 1,0); pastikan ≥ 2 frame dalam rentang itu (cek `--sample-fps`) |
   | Blink/closure palsu (flicker 1 frame) | `MIN_CONF` | Naikkan (0,5–0,6) |
   | Alert pada V1 (normal) | `ALERT1_CONFIRM_SECONDS`, `EYE_CLOSURE_SECONDS` | Naikkan |
   | Alert terlalu lambat pada V2/V9 | `ALERT1_CONFIRM_SECONDS`, `ALERT2_RECHECK_SECONDS` | Turunkan |
   | Bicara terhitung menguap (V5) | `YAWN_MIN_SECONDS`, `MIN_CONF` | Naikkan (1,5–2,0) |
   | Yawn terhitung ganda (V3) | `YAWN_MIN_SECONDS` | Periksa timeline; naikkan |
   | Membaca (menunduk) menambah skor | `HEAD_DROPPED_MIN_SECONDS` | Naikkan |
   | Alert 1 berulang cepat setelah "Got it" | cooldown setelah Alert 1 | Perlu perubahan kode (belum ada) |

7. **Tentukan kriteria penerimaan** bersama tim dan tulis di `metadata/calibration.md`. Contoh usulan (bukan dari PRD): V1 = 0 alert; ≥ 80% eye closure di V2 terdeteksi; yawn ganda = 0 di V3; V6 = 0 alert.
8. **Terapkan nilai:**
   - Lokal: ubah `backend/.env` (parameter env) dan konstanta di `temporal.py`.
   - Produksi (Railway): `railway variables --service loopa-backend --set "EYE_CLOSURE_SECONDS=1.2"` (dst.), lalu `railway up --service loopa-backend --detach` bila ada perubahan kode.
9. **Verifikasi di web asli** (langkah P5) dan ulangi replay dengan nilai baru. Simpan tabel sebelum/sesudah di `metadata/calibration.md`, lengkap dengan tanggal, laptop, orang, cahaya, dan jumlah video.
10. **Batasan yang wajib dilaporkan:** jumlah pengguna dan video terbatas, domain dataset (kamera mobil) berbeda dari webcam laptop, dan hitungan blink dibatasi laju sampling.

### P2. Penanganan NO_FACE

**Perilaku kode:** tanpa deteksi `eye_open`/`eye_closed` ≥ `MIN_CONF` ⇒ status `UNCERTAIN`, skor 0, durasi (closed, yawn, head) di-reset, dan akumulasi `drowsy_run` **ditahan** (tidak bertambah, tidak di-reset). Tidak ada alert dari frame tanpa wajah.

**Langkah uji:**
1. `backend\.venv\Scripts\python.exe -m pytest -q` (dari folder `backend`) harus lulus semua.
2. **Replay:** jalankan `replay_video.py` pada V6. Periksa `no_face_frames` di ringkasan dan kolom `face`/`status` di timeline CSV. Hasil yang benar: status `UNCERTAIN` saat wajah hilang, `alerts` kosong, counter tidak melonjak.
3. **Uji langsung di web** (https://loopa-smart-study.vercel.app, sesi 2 menit):
   - Tutup lensa atau keluar dari frame → badge berubah ke "Uncertain / no face detected", **tidak ada** alert, timer tetap berjalan.
   - Buka lagi → badge kembali ke Normal dalam beberapa detik.
   - Tutup mata **sambil** wajah terlihat → harus tetap terdeteksi mengantuk (jangan sampai dianggap no-face).
4. **Kasus tepi yang perlu diputuskan tim:**
   - Kepala menunduk penuh sehingga mata tidak terlihat → `UNCERTAIN`, tidak ada alert (batasan kode saat ini).
   - Menutup kamera di tengah episode `DROWSY` → akumulasi ditahan, lalu dilanjutkan saat wajah kembali.
   - Putus jaringan: UI menampilkan pesan error dan mempertahankan status terakhir (bisa basi); status tidak berubah ke "Normal" karena error.
   - Kamera ditolak/tidak ada: timer jalan, badge "Monitoring off".
5. **Kriteria lulus (AT-12):** tidak ada alert palsu pada V6, dan status bukan `NORMAL` saat wajah tidak terlihat.
6. Opsional (belum ada): banner "Wajah tidak terlihat" setelah 10 detik `NO_FACE` agar pengguna tahu monitoring tidak aktif.

### P3. Memastikan suara Alert 1 (dan Alert 2)

Bunyi dibuat dengan WebAudio (tanpa berkas): Alert 1 = 2 bip 660 Hz, Alert 2 = 3 bip 880 Hz. Browser memblokir audio sampai ada interaksi pengguna; aplikasi membuka kunci saat klik "Start study session", saat klik/tombol pertama di halaman sesi, dan saat menyalakan "Sound".

**Langkah uji (di Chrome laptop demo):**
1. **Perangkat:** volume Windows terdengar, perangkat output benar (speaker/headset). Tab tidak dibisukan (klik kanan tab → jangan "Mute site").
2. **Izin situs:** ikon gembok di address bar → *Site settings* → **Sound = Allow**.
3. Buka **Setup** → centang "Play a sound on alerts" → klik **Test audio**. Harus terdengar **dua bip** dan muncul teks "you should hear two beeps". Bila tertulis "audio blocked by the browser", klik sekali di halaman lalu ulangi.
4. Mulai sesi (kamera diizinkan). Picu **Alert 1** (tutup mata ≥ ±4,5 dtk, atau pakai mode demo `-Scenario drowsy` di P5). Harus ada modal "Take a tiny pause" **dan** dua bip.
5. Lanjutkan sampai **Alert 2**: modal "Let's listen to your body" dan **tiga bip** lebih tinggi.
6. **Matikan suara:** tombol "Sound off" → picu alert → modal tetap muncul dengan teks "Sound unavailable…", tanpa bunyi (AT-13).
7. **Nyalakan lagi:** tombol "Sound on" membunyikan satu bip uji.
8. **Kasus refresh:** refresh halaman sesi **tanpa mengklik apa pun**, lalu picu alert. Audio mungkin diblokir (modal menampilkan "Sound unavailable"). Klik/tekan tombol apa pun sekali, lalu alert berikutnya harus berbunyi.
9. **Tab di background:** pindah tab 20 detik lalu picu alert; catat apakah bunyi terdengar (pengiriman frame mungkin melambat di tab tersembunyi).
10. **Browser lain:** ulangi 3–5 di Edge/Firefox bila dipakai demo. Bluetooth headset bisa menunda bunyi pertama.
11. **Kriteria lulus:** bunyi terdengar di langkah 3–5; modal selalu muncul walau audio diblokir; tanggapan jelas saat suara mati. Catat browser dan perangkat yang diuji.
12. Opsional: ganti nada dengan berkas `frontend/public/sounds/alert.mp3` bila tim ingin suara khusus.

### P4. Break timer sesuai konfigurasi

Batas minimum belajar 1 menit, jadi untuk uji cepat pakai belajar **1 menit** dan istirahat **2 menit**.

1. Setup: belajar `1`, istirahat `2`, mulai sesi (dengan mock/normal agar tidak ada alert).
2. Tunggu timer belajar ke `00:00` → otomatis ke halaman break: "Study time is up", pilihan **Start break** dan **Finish**. Kamera berhenti.
3. Klik **Start break**. Mulai stopwatch. Tampilan harus `02:00` lalu turun. Bandingkan pada 30 dtk, 60 dtk, dan akhir (toleransi ±1 dtk).
4. **Tab di background:** pindah tab 60 detik, kembali → sisa waktu harus ±60 dtk berkurang (dihitung dari timestamp).
5. **Refresh di tengah break:** harus lanjut dengan sisa waktu benar (status break disimpan di sesi browser).
6. Saat `00:00`: tampil "Break is over" dengan **Next study session** dan **Finish**. (Notifikasi browser hanya muncul bila izin Notification sudah diberikan; aplikasi belum memintanya.)
7. **Verifikasi di backend** (ganti `<id>` dengan ID di URL halaman Summary):
   ```bash
   curl https://loopa-backend-production-44f3.up.railway.app/sessions/<id>/summary
   ```
   `total_break_seconds` harus ±120 untuk istirahat penuh; lebih kecil bila memakai **End break** lebih awal. `events` memuat `BREAK_STARTED` dan `BREAK_COMPLETED`.
8. **Klik Next study session:** kamera meminta izin lagi (tidak menyala otomatis), nomor blok menjadi 2, dan durasi belajar sama dengan konfigurasi sesi.
9. **Selesaikan** dari fase "Study time is up" tanpa break: Summary menampilkan break 0.
10. **Kriteria lulus:** AT-09, AT-10, AT-11 (PRD §14). Catat selisih terukur.

### P5. Uji end-to-end dan demo

**A. Persiapan (sebelum demo/UAT)**
1. Railway: status layanan *Success* dan saldo cukup (saldo free tinggal sedikit). Cek `https://loopa-backend-production-44f3.up.railway.app/health` → `status: ok`, `inference_backend: yolo`, `llm.enabled: true`.
2. Vercel: buka https://loopa-smart-study.vercel.app, Home menampilkan "Backend status: connected".
3. Chrome, kamera, cahaya cukup, wajah di tengah, volume nyala, tab lain ditutup.
4. Rekam layar sebagai cadangan. Siapkan rencana B: backend lokal `powershell -ExecutionPolicy Bypass -File start.ps1 -Scenario drowsy` (set `INFERENCE_BACKEND=mock` di `backend/.env`) agar alert muncul deterministik.

**B. Skenario UAT (PRD §14)** — isi kolom Hasil dengan ✅/❌ dan catatan.

| ID | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| AT-01 | Setup: belajar 20, istirahat 7, mulai | Timer 20:00 turun akurat; summary/konfigurasi 20 dan 7 menit | ☐ |
| AT-02 | Mulai sesi, duduk normal 2 menit | Tidak ada alert | ☐ |
| AT-03 | Tutup mata ≥ ±4,5 dtk | Bunyi + modal Alert 1, hanya tombol "Got it" | ☐ |
| AT-04 | Tutup Alert 1, buka mata dan pulih | Tidak ada Alert 2 untuk episode itu | ☐ |
| AT-05 | Setelah Alert 1, tutup mata terus ≥ ±5 dtk | Bunyi + Alert 2 dengan dua opsi | ☐ |
| AT-06 | Alert 2 → "End my session" | Timer dan kamera berhenti, langsung Summary | ☐ |
| AT-07 | Alert 2 → "I'll do a quick reset" | Modal saran muncul, timer masih dijeda | ☐ |
| AT-08 | "I'm ready to continue" | Kembali ke sesi dengan sisa waktu benar | ☐ |
| AT-09 | Biarkan timer belajar habis normal | Monitoring berhenti, pilihan break muncul | ☐ |
| AT-10 | Mulai break (lihat P4) | Break berjalan sesuai menit, kamera mati | ☐ |
| AT-11 | Biarkan break habis | "Break is over" + Next/Finish | ☐ |
| AT-12 | Tutup lensa (lihat P2) | `UNCERTAIN`, tanpa alert | ☐ |
| AT-13 | Matikan suara / blokir audio (lihat P3) | Modal tetap muncul + keterangan | ☐ |
| AT-14 | "End session" manual | Konfirmasi → Summary, data tersimpan | ☐ |
| AT-15 | Biarkan waktu habis saat tidak ada alert | Ke akhir fase belajar, tanpa Alert 2 terlambat | ☐ |
| AT-16 | Klik tombol alert dua kali cepat | Aksi hanya diproses sekali (cek `events` di Summary: tidak ada duplikat) | ☐ |

**C. Skrip demo (±8 menit)**
1. **Home** → jelaskan Loopa, klik *Start session*.
2. **Setup**: belajar 2 menit, istirahat 1 menit; klik *Test audio* (bunyikan dua bip).
3. Mulai sesi → izinkan kamera → tunjukkan status Normal dan counter.
4. Tutup mata → **Alert 1** (suara + modal) → "Got it".
5. Tutup mata lagi → **Alert 2** → "I'll do a quick reset" → modal saran → "I'm ready to continue".
6. Biarkan timer habis → **Break**: tunjukkan tip "Loopa coach" dan label model → timer break.
7. **Finish** → **Summary**: durasi, indikator, alert, rekomendasi AI.
8. Buka **History** dan **Statistics**.
9. Alternatif: ulangi dan pilih "End my session" di Alert 2 (langsung Summary).
10. Siapkan jawaban: ini indikasi visual, bukan diagnosis; tidak mengukur fokus; video tidak disimpan; metrik model dan batasannya (`metadata/eval_report.json`).

**D. Kriteria selesai:** semua AT-01…AT-16 terisi, temuan dicatat di `metadata/uat_results.md`, dan setiap ❌ punya tugas perbaikan.

### P6. Lainnya yang belum tercantum

**P6.1 Refresh, tab ditutup, dan background (PRD §6.3)**
1. Saat sesi berjalan, tekan F5. Harapan: halaman memulihkan sisa waktu; bila gagal, tidak boleh mengarang durasi. Catat apa yang pulih (timer ya; alert terbuka dan kamera perlu dipastikan).
2. Tutup tab lalu buka `/session` lagi dalam sesi yang sama → catat perilaku.
3. Pindah tab 60 dtk saat sesi → timer tetap benar; catat apakah frame tetap terkirim.
4. Restart backend (lokal) saat sesi berjalan → UI harus menampilkan "This session is no longer available" dan berhenti mengirim frame.

**P6.2 Aktifkan Supabase**
1. Buat proyek di supabase.com, buka SQL Editor, jalankan isi `backend/app/db/schema.sql`.
2. Isi `SUPABASE_URL` dan `SUPABASE_SERVICE_KEY` (service_role, hanya di backend) di `backend/.env` untuk lokal, dan di **dashboard Railway → Variables** untuk produksi. Jangan taruh di frontend atau chat.
3. Jalankan ulang backend; `GET /health` harus menampilkan `"persistence": true`.
4. Mainkan satu sesi, restart backend, lalu buka History: sesi harus masih ada (status baca dari DB).
5. Periksa tabel `sessions`, `events`, `session_metrics` di Supabase.

**P6.3 Aksesibilitas (NFR-08)**
1. Hanya dengan keyboard: Tab ke tombol modal, Enter untuk memilih, Shift+Tab untuk mundur. Catat apakah fokus bisa keluar dari modal (belum ada focus trap) dan apakah Esc menutup konfirmasi.
2. Cek kontras teks muted, ukuran target sentuh, dan teks alternatif ikon.

**P6.4 Latih model penuh di GPU**
1. Unggah `scripts/` dan `datasets/kantukv2_split/` ke Google Drive, buka `notebooks/kantukv2_audit_train_eval.ipynb` di Colab dengan runtime GPU.
2. Jalankan training penuh (mis. 50 epoch, `imgsz` 640) dan evaluasi di test set.
3. Bandingkan metrik dengan model CPU (mAP50 0,959). Bila lebih baik, salin ke `models/best.pt` dan `backend/models/best.pt`; ubah `YOLO_IMGSZ` sesuai ukuran training.
4. Deploy ulang: `railway up --service loopa-backend --detach` dari folder `backend`.

**P6.5 Kunci versi library**
```bash
backend\.venv\Scripts\python.exe -m pip freeze > backend/requirements.lock.txt
```
Catat versi `ultralytics`, `torch`, dan `fastapi` di dokumen eksperimen. `frontend/package.json` sudah memakai versi eksak.

**P6.6 Simpan artefak**
Unggah ke Drive: `models/best.pt`, `metadata/*.json`, `metadata/*.png`, notebook, dan `logs/`. Catat tautannya di README.

**P6.7 Latensi end-to-end (NFR-07)**
1. Chrome DevTools → Network → saring `predict`. Catat waktu per permintaan dan jumlah per 10 detik (≈ fps efektif).
2. Bandingkan lokal vs Vercel→Railway. Bila fps < 2, pertimbangkan menurunkan `FRAME_INTERVAL_MS` atau ukuran frame (480 px).
3. Tentukan target dari baseline, jangan dari asumsi (PRD §13 NFR-07).

**P6.8 Pembersihan sebelum final**
- Hapus `[temp] AI model` (`frontend/src/components/ui/AiModelNote.tsx` dan satu baris di `frontend/src/app/page.tsx`).
- Hapus artefak uji: `metadata/synthetic_test.mp4`, `synthetic_truth.csv`, `replay_synthetic_*`.
- Pastikan `.env` tidak ikut commit atau terunggah.

**P6.9 Keamanan dan pengguna (koordinasi PM)**
- Tentukan model autentikasi (login, username, avatar) dan filter riwayat per `user_id`. Sementara itu riwayat global.
- Batasi akses API atau tambahkan rate limit sebelum URL disebar.

**P6.10 Operasional**
- Pantau saldo Railway dan batas gratis OpenRouter (model gratis sering 429/504; ada teks fallback).
- Bila model utama sering gagal, tambah cadangan lain atau gunakan penyedia dengan batas lebih longgar.
- Selesaikan Figma yang masih "berantakan" dan halaman Register bersama tim desain.

---

## 4. Urutan kerja yang disarankan

1. P3 (suara) dan P4 (break) — cepat, tanpa data baru.
2. P1 (kalibrasi) bersama P2 (NO_FACE) — rekam video sekali untuk keduanya.
3. P5 (UAT dan latihan demo) memakai nilai hasil kalibrasi.
4. P6.2 (Supabase), P6.4 (model GPU), lalu P6.5–P6.8 menjelang 13 November.

## 5. Perintah rujukan

```bash
# lokal
powershell -ExecutionPolicy Bypass -File start.ps1
backend\.venv\Scripts\python.exe -m pytest -q          # jalankan dari folder backend
# kalibrasi
backend\.venv\Scripts\python.exe -I scripts/replay_video.py <video.mp4> --truth <truth.csv> --out metadata/video/<nama>
# deploy
vercel deploy --prod --yes                               # dari folder frontend
railway up --service loopa-backend --detach              # dari folder backend
railway variables --service loopa-backend --set "NAMA=nilai"
```
