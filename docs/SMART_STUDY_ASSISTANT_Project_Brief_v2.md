# SMART STUDY ASSISTANT
## Sistem Deteksi Kantuk dan Manajemen Waktu Istirahat Berbasis Web

**Project Brief — Versi 2.0**  
**Tanggal revisi:** 25 Oktober 2026  
**Target penyelesaian:** 13 November 2026  
**Status:** Rencana implementasi MVP; dataset dan performa model belum divalidasi.

---

# 1. Project Brief

## 1.1 Nama dan Judul

**Nama:** SMART STUDY ASSISTANT  
**Judul:** SMART STUDY ASSISTANT: Sistem Deteksi Kantuk dan Manajemen Waktu Istirahat Berbasis Web

## 1.2 Konsep

SMART STUDY ASSISTANT adalah aplikasi web yang menggunakan webcam untuk **memantau indikator visual kantuk** selama sesi belajar atau mengerjakan proyek. Sistem mendeteksi kondisi mata, indikasi menguap, dan posisi kepala; menggabungkan hasilnya sepanjang waktu; memberikan saran istirahat ketika indikator kantuk muncul secara konsisten; serta menyediakan ringkasan dan rekomendasi setelah sesi berakhir.

**Perubahan utama dari versi 1.0:** analisis konsentrasi, fokus, *focus score*, *focused duration*, dan *distraction detection* **dihapus dari scope**. Aplikasi **tidak mengklaim** mengetahui apakah pengguna sedang berkonsentrasi atau mendiagnosis kondisi medis.

## 1.3 Alur utama

```text
WEBCAM
   ↓
Frame Capture
   ↓
YOLO Drowsiness Indicator Detection
   ├── eye_open / eye_closed
   ├── yawn / no_yawn
   └── head_straight / head_dropped
   ↓
Temporal Analysis (tracking status lintas frame)
   ↓
Drowsiness Decision Engine
   ├── Normal
   ├── Possible Drowsiness
   └── Drowsy — Need Rest
   ↓
Rest Notification + Session Metrics
   ↓
Supabase → Session Analytics → AI Recommendation
```

> Kelas di atas merupakan label kandidat dataset **kantukv2**; ejaan, ketersediaan, dan kualitas anotasi harus diverifikasi dalam audit dataset. Kategori status kantuk adalah keluaran *decision engine*, bukan label asli model YOLO.

---

# 2. Scope MVP

## 2.1 Indikator visual

| Indikator | Tujuan | Implementasi MVP |
|---|---|---|
| Eye open / closed | Mengenali kondisi mata | Prediksi YOLO per frame dan penyaringan prediksi |
| Blink | Menghitung transisi buka–tutup–buka yang singkat | State machine + timestamp |
| Prolonged eye closure | Mendeteksi penutupan mata yang relatif lama | Durasi kondisi tertutup yang stabil |
| Yawning | Mendeteksi dugaan menguap | Deteksi `yawn` yang bertahan dan *cooldown* antar kejadian |
| Head dropped | Indikator pendukung kepala menunduk | Deteksi `head_dropped` yang konsisten |
| Drowsiness | Mengestimasi tingkat indikasi kantuk | Aturan temporal multiindikator |

**Batasan:** *head dropped* saja tidak membuktikan kantuk; pengguna bisa sedang membaca atau menunduk. Mata tertutup dalam satu gambar juga tidak otomatis berarti kantuk.

## 2.2 Output real-time

- Status: **Normal**, **Possible Drowsiness**, atau **Drowsy — Need Rest**.
- Estimasi *drowsiness score* (skor heuristik, bukan probabilitas klinis).
- Blink count, yawn count, long eye-closure events.
- Session timer dan notifikasi istirahat.
- Status **Face Not Detected / Uncertain** saat bukti visual tidak memadai; jangan paksa klasifikasi Normal.

## 2.3 Output setelah sesi

- Total session duration.
- Estimated drowsy duration dan jumlah drowsiness events.
- Blink count, yawn count, prolonged eye-closure events.
- Timeline indikasi kantuk dan notifikasi istirahat.
- Riwayat sesi serta AI-generated summary/recommendation.

## 2.4 Di luar scope MVP

- Focus score, concentration analysis, attention scoring, distraction detection.
- Pengenalan emosi/ekspresi wajah yang kompleks.
- Diagnosis medis atau penentuan kantuk yang pasti.
- Person identification dan penyimpanan video webcam mentah secara default.
- Pelatihan YOLO dari bobot acak; gunakan bobot pretrained.

---

# 3. Tech Stack

| Lapisan | Teknologi | Fungsi |
|---|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS, shadcn/ui | Webcam UI, timer, dashboard, halaman sesi |
| Chart | Recharts | Timeline dan statistik sesi |
| Computer Vision | YOLO pretrained + fine-tuning | Deteksi indikator visual dari dataset Roboflow |
| Video processing | OpenCV / Python | Pembacaan video dan uji inferensi |
| Temporal processing | Python | Blink, durasi eye closure, yawning events |
| Decision engine | Python, aturan berbasis waktu | Drowsiness score dan status |
| Backend | FastAPI | API inferensi dan layanan sesi |
| Database | Supabase / PostgreSQL | Sessions, metrics, events |
| AI recommendation | LLM API | Saran setelah sesi dari ringkasan terstruktur |
| Training | Google Colab | Fine-tuning, evaluasi, ekspor model |

**MediaPipe Face Landmarker:** tidak wajib untuk MVP. Dapat ditambahkan pada tahap lanjutan bila membutuhkan EAR/MAR atau landmark numerik. **Random Forest:** tidak wajib karena klasifikasi indikator visual dilakukan oleh YOLO dan keputusan kantuk menggunakan aturan temporal.

---

# 4. Dataset

## 4.1 Dataset kandidat utama

**Roboflow Universe — kantukv2**  
https://universe.roboflow.com/testproject-8jvqn/kantukv2

Dataset ini dipilih sebagai **kandidat utama**, menggantikan UTA-RLDD untuk jalur MVP karena lebih praktis untuk *fine-tuning object detection*. Kelas kandidat yang akan diverifikasi:

```text
eye_closed
eye_open
head_dropped
head_straight
no_yawn
yawn
```

**Penting:** jumlah gambar, pembagian train/valid/test, lisensi, distribusi kelas, dan konsistensi label harus dicek pada versi dataset yang benar-benar diunduh. Angka di halaman Roboflow dapat berubah menurut versi; jangan menetapkan jumlah sebagai fakta sebelum audit.

## 4.2 UTA-RLDD

UTA-RLDD **tidak digunakan sebagai dataset utama MVP**. Dataset video tersebut tetap dapat menjadi referensi atau sumber evaluasi tambahan apabila waktu memungkinkan. Jangan memasukkannya ke pipeline training wajib karena target pengerjaan singkat.

## 4.3 Audit dataset wajib

1. Unduh satu versi dataset Roboflow dalam format YOLO yang sesuai dengan framework training.
2. Catat URL, versi, lisensi, tanggal unduh, dan struktur direktori.
3. Periksa `data.yaml`, jumlah gambar, jumlah anotasi dan distribusi tiap kelas.
4. Visualisasikan sampel gambar beserta bounding box; cek label keliru, duplikasi, gambar rusak, dan kondisi wajah yang sulit.
5. Pastikan tidak ada kebocoran antar split, khususnya gambar berurutan atau subjek sama bila identitas/sumber dapat ditelusuri.
6. Pertahankan test set yang tidak dipakai memilih hyperparameter.
7. Siapkan video webcam **terpisah** untuk uji temporal, karena gambar statis tidak cukup untuk mengevaluasi blink count dan event duration.

## 4.4 Risiko generalisasi

Data wajah pengemudi dapat dipakai untuk mempelajari indikator visual kantuk, tetapi kondisi kamera dashboard berbeda dari webcam laptop. Lakukan uji pada beberapa pengguna, pencahayaan, posisi kepala, dan jarak kamera; laporkan keterbatasan apabila data uji terbatas.

---

# 5. Arsitektur Sistem

```text
┌─────────────────────────────┐
│ Next.js Study Session       │
│ Webcam + Timer + Live UI    │
└──────────────┬──────────────┘
               │ frame terpilih / stream (desain final saat implementasi)
               ▼
┌─────────────────────────────┐
│ FastAPI Inference Service   │
│ YOLO pretrained fine-tuned  │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ Temporal Event Processor    │
│ Blink / Closure / Yawn      │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ Drowsiness Decision Engine  │
│ Score + Status + Smoothing  │
└──────────┬───────────┬──────┘
           │           │
           ▼           ▼
   Rest Notification   Session Metrics / Events
                       │
                       ▼
                 Supabase DB
                       │
                       ▼
                 Session Analytics
                       │
                       ▼
                LLM Recommendation
```

**Keputusan integrasi yang harus diuji:** frame dapat diproses pada backend FastAPI; batasi resolusi dan laju pengiriman, dan ukur latensi nyata. Alternatif deployment inference di browser dapat dipertimbangkan kemudian, tetapi bukan prasyarat MVP.

---

# 6. YOLO Model

## 6.1 Tugas model

Fine-tuning YOLO pretrained untuk mendeteksi objek/region yang diberi anotasi dalam dataset `kantukv2`. Model mengembalikan bounding box, kelas, dan confidence. **Output YOLO bukan diagnosis kantuk**; keputusan tingkat kantuk dibuat di tahap temporal.

## 6.2 Training

```text
Roboflow Dataset (YOLO format)
   ↓
Dataset Audit + Split Check
   ↓
Pretrained YOLO (varian kecil)
   ↓
Fine-tuning
   ↓
Validation + Best Weights
   ↓
Test Evaluation
   ↓
Model Artifact (.pt / format deployment yang sesuai)
```

Gunakan model berukuran kecil sebagai baseline agar waktu training dan inferensi lebih ringan. Pilih versi library/model yang kompatibel dan catat versinya dalam `requirements.txt`.

## 6.3 Evaluasi deteksi

- Precision dan recall per kelas.
- mAP@0.5 dan mAP@0.5:0.95.
- Confusion matrix dan contoh false positive/false negative.
- Waktu inferensi per frame, latensi API, dan penggunaan resource pada perangkat target.

Jangan hanya melaporkan accuracy, karena model utamanya merupakan object detector.

---

# 7. Temporal Analysis

Prediksi per frame perlu digabungkan berdasarkan timestamp. Jangan mengasumsikan FPS konstan, terutama bila frame dikirim melalui jaringan.

## 7.1 Blink detection

Transisi yang diharapkan:

```text
OPEN → CLOSED → OPEN
        │
        └─ hitung blink jika durasi berada dalam rentang yang
           ditetapkan dan prediksi cukup stabil
```

Simpan `blink_count`, `blink_duration`, dan timestamp. Ambang durasi harus dituning dari video uji, bukan dipatok sebagai angka universal.

## 7.2 Prolonged eye closure

Kondisi mata tertutup yang bertahan lebih lama daripada kedipan biasa dicatat sebagai `EYE_CLOSURE` event. Jika wajah tidak terdeteksi, hentikan/beri tanda *uncertain* alih-alih menganggap mata tertutup.

## 7.3 Yawning

Catat event ketika `yawn` muncul konsisten selama durasi minimum. Terapkan *cooldown* agar satu menguap tidak dihitung berkali-kali. Label `no_yawn` membantu membedakan kondisi, tetapi perlu diuji apakah mulut terbuka karena berbicara ikut terdeteksi.

## 7.4 Head dropped

Gunakan hanya sebagai indikator pendukung bila bertahan dan berulang. Jangan menyimpulkan kantuk dari satu frame kepala menunduk.

## 7.5 Stabilitas temporal

- Confidence threshold dan smoothing antar frame.
- Hysteresis / state machine untuk mencegah status berkedip-kedip.
- Timestamp nyata untuk pengukuran durasi.
- Penanganan kehilangan wajah dan prediksi saling bertentangan.

---

# 8. Drowsiness Decision Engine

## 8.1 Input

```text
recent_eye_closure_duration
blink_events / blink_pattern
yawn_events
head_dropped_duration
face_detection_quality
```

## 8.2 Output

| Status | Interpretasi |
|---|---|
| `NORMAL` | Belum ada pola indikator kantuk yang signifikan |
| `POSSIBLE_DROWSINESS` | Muncul indikasi kantuk yang perlu diamati |
| `DROWSY_NEED_REST` | Beberapa indikator/durasi konsisten memenuhi aturan peringatan |
| `UNCERTAIN` | Bukti visual tidak cukup untuk menyimpulkan |

## 8.3 Skor

Drowsiness score 0–100 merupakan **skor heuristik internal**, bukan probabilitas seseorang benar-benar mengantuk. Bobot, ambang, dan durasi ditetapkan dari eksperimen dan dikalibrasi melalui video pengujian.

Contoh logika konseptual:

```text
IF face_not_detected:
    status = UNCERTAIN
ELIF sustained_eye_closure OR repeated_multi_indicator_pattern:
    status = DROWSY_NEED_REST
ELIF moderate_indicator_pattern:
    status = POSSIBLE_DROWSINESS
ELSE:
    status = NORMAL
```

Hindari memicu peringatan hanya karena satu prediksi atau satu kali menguap.

---

# 9. Rest Notification

Ketika `DROWSY_NEED_REST` bertahan sesuai aturan:

```text
⚠️ TIME FOR A BREAK

Indikator visual menunjukkan kemungkinan kantuk.
Pertimbangkan istirahat singkat sebelum melanjutkan belajar.

[Take a Break] [Dismiss]
```

Simpan waktu peringatan dan respons pengguna. Terapkan *cooldown* agar notifikasi tidak berulang terlalu sering. Hindari bahasa diagnosis medis.

---

# 10. Frontend Web

## 10.1 Home

- Identitas aplikasi, deskripsi singkat, dan tombol `Start Session`.

## 10.2 Study Session

- Webcam preview dan status akses kamera.
- Session timer dan kontrol `Start / Pause / End Session`.
- Status kantuk: Normal / Possible Drowsiness / Drowsy — Need Rest / Uncertain.
- Drowsiness score (diberi label estimasi).
- Blink counter, yawn counter, eye-closure events.
- Rest notification.

## 10.3 Session Analytics

- Total session duration.
- Estimated drowsy duration.
- Blink count, yawn count, prolonged eye closure, drowsiness events.
- Timeline status dan jumlah notifikasi.

## 10.4 Session History

- Daftar sesi, tanggal, durasi, dan ringkasan indikator kantuk.

## 10.5 AI Insights

- Ringkasan pola indikator visual selama sesi.
- Saran pengaturan jeda belajar dan istirahat.
- Hindari klaim penyebab medis atau diagnosis.

---

# 11. Backend API

Contoh rancangan endpoint (dapat disesuaikan saat integrasi):

| Endpoint | Metode | Fungsi |
|---|---|---|
| `/health` | GET | Health check |
| `/predict` | POST | Inferensi frame dan hasil deteksi |
| `/sessions` | POST | Membuat sesi |
| `/sessions/{id}/metrics` | POST | Menyimpan metrik/event terstruktur |
| `/sessions/{id}/end` | POST | Menutup sesi |
| `/sessions/{id}` | GET | Detail sesi |
| `/sessions/{id}/insights` | POST | Menghasilkan rekomendasi dari ringkasan sesi |

**Catatan:** state temporal harus konsisten per sesi. Jika `/predict` menerima frame stateless, temporal processing dilakukan pada service stateful per session ID atau pada frontend; pilih satu desain dan dokumentasikan. Jangan mengirim video mentah ke LLM.

Contoh respons ringkas:

```json
{
  "status": "POSSIBLE_DROWSINESS",
  "drowsiness_score": 47,
  "blink_count": 14,
  "yawn_count": 1,
  "eye_closure_events": 2,
  "timestamp": "2026-10-25T19:00:00+07:00"
}
```

Nilai tersebut hanya ilustrasi kontrak API, bukan hasil model nyata.

---

# 12. Database Design

## 12.1 `sessions`

```text
id
user_id (nullable jika mode tanpa login)
started_at
ended_at
duration_seconds
estimated_drowsy_seconds
blink_count
yawn_count
eye_closure_count
drowsiness_event_count
```

## 12.2 `session_metrics`

```text
id
session_id
timestamp
drowsiness_score
status
face_detected
eye_state
yawn_state
head_state
```

## 12.3 `events`

```text
id
session_id
timestamp
event_type
duration_seconds
metadata
```

`event_type` contoh: `BLINK`, `YAWN`, `EYE_CLOSURE`, `DROWSINESS`, `REST_NOTIFICATION`, `REST_TAKEN`.

**Privasi:** simpan fitur, status, dan event secara default; tidak menyimpan frame/video mentah kecuali ada kebutuhan pengujian dengan persetujuan yang jelas. Atur retensi dan akses data sesuai implementasi.

---

# 13. AI Recommendation

LLM dipanggil **setelah sesi berakhir**, bukan untuk inferensi video real-time.

```text
Session Analytics
   ↓
Structured Summary (tanpa frame mentah)
   ↓
LLM API
   ↓
Personalized Rest Recommendation
```

Contoh input:

```json
{
  "session_duration_minutes": 90,
  "estimated_drowsy_minutes": 14,
  "blink_count": 81,
  "yawn_count": 4,
  "eye_closure_events": 6,
  "rest_notifications": 2
}
```

Contoh rekomendasi: “Selama sesi ini terdapat beberapa indikator kemungkinan kantuk. Pertimbangkan jeda singkat dan evaluasi waktu belajar yang paling nyaman.”

---

# 14. Functional Requirements

| ID | Requirement |
|---|---|
| FR-01 | Sistem meminta izin dan mengakses webcam |
| FR-02 | Sistem menjalankan inferensi indikator visual menggunakan YOLO |
| FR-03 | Sistem mendeteksi mata terbuka/tertutup |
| FR-04 | Sistem menghitung kedipan dari rangkaian frame |
| FR-05 | Sistem mendeteksi indikasi menguap dan menghitung event |
| FR-06 | Sistem mendeteksi head dropped sebagai indikator pendukung |
| FR-07 | Sistem menghitung durasi eye closure |
| FR-08 | Sistem menentukan status/estimasi kantuk dengan temporal analysis |
| FR-09 | Sistem memberi rekomendasi istirahat dan mencegah spam notifikasi |
| FR-10 | Sistem mencatat dan mengakhiri sesi belajar |
| FR-11 | Sistem menyimpan metrics/events dan menampilkan analytics |
| FR-12 | Sistem membuat AI recommendation setelah sesi |
| FR-13 | Sistem menangani kamera tidak tersedia/wajah tidak terdeteksi |

**Tidak ada FR untuk focus score, concentration, maupun distraction.**

---

# 15. Non-Functional Requirements

- Responsif untuk laptop dan browser desktop modern.
- Meminta izin webcam secara eksplisit; memberikan pesan saat akses ditolak.
- Latensi inferensi diuji pada perangkat target; target performa ditetapkan setelah baseline.
- Koneksi/API gagal tidak boleh membuat status kantuk palsu.
- Menyimpan data minimal dan tidak mengirim video mentah ke LLM.
- Model, dataset, versi library, dan hasil eksperimen terdokumentasi.
- API dan database menggunakan autentikasi/otorisasi sesuai fitur akun yang diterapkan.

---

# 16. Evaluasi dan Testing

## 16.1 Model YOLO

- Precision, recall, mAP@0.5, mAP@0.5:0.95.
- Confusion matrix dan evaluasi per kelas.
- Contoh kesalahan deteksi serta latensi inferensi.

## 16.2 Temporal events

- Uji video untuk blink count, yawn count, prolonged eye closure.
- Bandingkan jumlah/durasi prediksi dengan anotasi manual pada video uji.
- Laporkan false alarms dan missed events.

## 16.3 End-to-end

| Skenario | Ekspektasi |
|---|---|
| Mata terbuka normal | Tidak memicu peringatan |
| Kedipan singkat | Blink count bertambah satu kali |
| Mata tertutup lama | Eye-closure event terhitung |
| Menguap | Yawn event terhitung tanpa hitung ganda |
| Kepala menunduk sesaat | Tidak langsung diklasifikasikan mengantuk |
| Pola indikator kantuk konsisten | Status naik dan notifikasi muncul |
| Wajah tidak terdeteksi | Status `UNCERTAIN`, bukan `NORMAL` |
| Akhiri sesi | Metrik tersimpan dan analytics tampil |
| LLM/API gagal | Sesi tetap dapat selesai, UI menampilkan fallback |

---

# 17. Folder Structure

```text
smart-study-assistant/
├── notebooks/
│   ├── 01_dataset_audit.ipynb
│   ├── 02_yolo_training.ipynb
│   └── 03_model_evaluation.ipynb
├── datasets/                # data lokal/Drive, tidak wajib commit
├── models/                  # best weights dan metadata
├── cv/
│   ├── inference.py
│   ├── temporal_analysis.py
│   └── decision_engine.py
├── backend/
│   ├── main.py
│   ├── routes/
│   └── services/
├── web/
│   ├── app/
│   ├── components/
│   └── lib/
├── metadata/
├── logs/
├── requirements.txt
└── README.md
```

Struktur dapat dipetakan ke direktori Google Drive yang telah dibuat pada setup sebelumnya. Jangan menghapus tracking atau metadata project lama sebelum dicadangkan.

---

# 18. Tahapan Pengembangan

## Phase 01 — Project Setup (sudah dikerjakan sebelumnya)

- Setup Google Drive, notebook, tracking, dependencies, dan validasi lingkungan.
- Periksa ulang file yang sebelumnya berada di temporary storage; hanya file persisten yang dapat diasumsikan masih tersedia.
- Perbarui metadata project dan requirements untuk pipeline YOLO.

## Phase 02 — Roboflow Dataset Audit

- Unduh `kantukv2` versi terpilih.
- Audit label, distribusi kelas, anotasi, duplikasi, dan split.
- Simpan audit report dan dataset manifest.

## Phase 03 — YOLO Training

- Pilih bobot pretrained kecil.
- Fine-tune pada dataset yang sudah diaudit.
- Simpan `best.pt`, konfigurasi eksperimen, dan metrik validasi.

## Phase 04 — Model Evaluation

- Uji test set yang terpisah.
- Uji prediksi webcam/video, termasuk false alarms.
- Ukur latensi dan dokumentasikan batasan.

## Phase 05 — Temporal & Decision Engine

- Blink detection, prolonged closure, yawning events.
- Drowsiness status dan smoothing.
- Notifikasi dengan cooldown.

## Phase 06 — Backend & Web

- FastAPI dan kontrak API.
- Next.js session UI, timer, status, analytics.
- Integrasi Supabase dan history.

## Phase 07 — AI & Final Testing

- AI insight setelah sesi.
- End-to-end testing, error handling, dokumentasi, dan demo.

---

# 19. Timeline dan Deliverables

| Deadline | Deliverables wajib | Kriteria selesai |
|---|---|---|
| **30 Oktober 2026** | Dataset final, audit, YOLO baseline trained, model artifact, LoFi | Model dapat inferensi sampel; weights dan notebook tersimpan; LoFi siap |
| **6 November 2026** | Evaluasi model, uji webcam, temporal baseline, API, HiFi | Metrik terdokumentasi; endpoint berjalan; desain HiFi tersedia |
| **13 November 2026** | Website, session analytics, notifikasi, database, AI insight, testing | Alur start → monitor → alert → end → analytics dapat didemokan |

### Rencana harian prioritas

- **25–26 Okt:** Audit Roboflow dan kunci versi dataset.
- **27–28 Okt:** Fine-tuning dan validasi awal YOLO.
- **29–30 Okt:** Simpan model, uji inferensi, selesaikan LoFi.
- **31 Okt–2 Nov:** Evaluasi test set dan video webcam.
- **3–4 Nov:** Temporal processing, decision engine, dan FastAPI.
- **5–6 Nov:** Integrasi awal API, HiFi, dokumentasi evaluasi.
- **7–9 Nov:** Next.js Study Session, timer, webcam, status.
- **10–11 Nov:** Supabase, analytics, history, rest notification, AI insights.
- **12–13 Nov:** Uji end-to-end, perbaikan bug, demo final.

**Jika waktu mepet:** prioritaskan alur webcam → deteksi → status → rest notification → session analytics. AI insight dan history dapat disederhanakan tanpa mengorbankan inti MVP.

---

# 20. Acceptance Criteria MVP

- [ ] Dataset `kantukv2` telah diaudit dan versi/kelas terdokumentasi.
- [ ] Model YOLO fine-tuned dapat mendeteksi indikator visual pada gambar uji.
- [ ] Precision, recall, mAP, dan confusion matrix tersedia.
- [ ] Inferensi video/webcam berfungsi dengan penanganan wajah tidak terdeteksi.
- [ ] Blink, yawn, dan eye-closure events dihitung dengan aturan temporal.
- [ ] Status kantuk tidak berubah hanya karena satu prediksi sporadis.
- [ ] Rest notification muncul sesuai aturan dan memiliki cooldown.
- [ ] Pengguna dapat memulai/mengakhiri sesi dan melihat durasi.
- [ ] Session metrics/events tersimpan dan analytics ditampilkan.
- [ ] AI recommendation menggunakan ringkasan terstruktur, bukan video mentah.
- [ ] Website dan API dapat didemokan end-to-end.
- [ ] Tidak ada fitur focus/concentration/distraction dalam MVP.

---

# 21. Risiko dan Mitigasi

| Risiko | Mitigasi |
|---|---|
| Label Roboflow tidak konsisten | Audit visual, perbaiki label bila perlu, batasi klaim |
| Dataset gambar tidak memuat informasi durasi | Gunakan video webcam terpisah untuk temporal testing |
| Kebocoran data train/test | Audit duplikasi dan sumber/subjek bila tersedia |
| Domain shift pengemudi → pelajar | Uji kamera laptop, pencahayaan, dan variasi pengguna |
| YOLO lambat di deployment | Gunakan model kecil, turunkan resolusi/frekuensi inferensi |
| False alarm saat membaca/berbicara | Multiindikator, smoothing, threshold berbasis waktu |
| Waktu implementasi sempit | Feature freeze dan prioritaskan jalur MVP |
| Penyimpanan Colab sementara hilang | Simpan weights, dataset manifest, notebook, logs di Google Drive |

---

# 22. Prinsip Pengembangan

1. **Fokus hanya pada indikasi kantuk**, bukan fokus/konsentrasi.
2. **Gunakan pretrained YOLO** untuk mempercepat training.
3. **Dataset Roboflow `kantukv2` adalah kandidat utama**, tetapi tetap wajib diaudit.
4. **Gunakan analisis temporal**, bukan keputusan dari satu gambar.
5. **Bedakan hasil deteksi visual dan keputusan kantuk**.
6. **Evaluasi dua level:** performa object detection dan performa event temporal.
7. **Jaga privasi:** simpan metrik/event, bukan video mentah secara default.
8. **AI hanya memberikan rekomendasi dari analytics**, bukan diagnosis.
9. **Prioritaskan MVP** yang dapat diuji dan didemokan sebelum fitur tambahan.
10. **Simpan artefak penting secara persisten** di Google Drive atau repositori yang sesuai.

---

# 23. Ringkasan Keputusan Versi 2.0

| Aspek | Keputusan |
|---|---|
| Tujuan | Deteksi indikasi kantuk selama belajar dan rekomendasi istirahat |
| Dataset | Roboflow `kantukv2` (setelah audit) |
| UTA-RLDD | Referensi/opsional, bukan dataset utama |
| Model utama | Fine-tuned YOLO pretrained |
| MediaPipe | Opsional, bukan dependensi inti MVP |
| Random Forest | Dihapus dari pipeline wajib MVP |
| Analisis temporal | Wajib untuk blink, yawn, closure duration |
| Status | Normal / Possible Drowsiness / Drowsy — Need Rest / Uncertain |
| Fitur dihapus | Focus, concentration, distraction, emotion analysis |
| Output akhir | Rest notification, session analytics, AI recommendations |
| Deadline | 13 November 2026 |

**Definisi keberhasilan:** SMART STUDY ASSISTANT mampu mendeteksi indikator visual kantuk secara real-time melalui webcam, mengolah pola temporal menjadi peringatan yang wajar, mencatat sesi belajar, dan memberikan ringkasan serta rekomendasi istirahat tanpa mengklaim pengukuran konsentrasi maupun diagnosis medis.
