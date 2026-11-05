# PRODUCT REQUIREMENTS DOCUMENT (PRD)
## SMART STUDY ASSISTANT — Deteksi Kantuk dan Manajemen Sesi Pomodoro

**Versi:** 1.0  
**Tanggal:** 25 Oktober 2026  
**Dasar:** `SMART_STUDY_ASSISTANT_Project_Brief_v2.md`  
**Target MVP:** 13 November 2026  
**Status:** Spesifikasi untuk implementasi; parameter deteksi dan usability perlu divalidasi.

> **Perubahan terhadap Project Brief v2:** dokumen ini menetapkan **kantukv2 sebagai satu-satunya dataset untuk training dan evaluasi berbasis dataset**; menambahkan sesi Pomodoro dengan durasi kustom, timer istirahat kustom, alert suara + pop-up, dan alur peringatan bertingkat. Detail perilaku yang tidak ditetapkan pengguna ditandai sebagai **usulan MVP** dan dapat disesuaikan sebelum implementasi.

---

# 1. Ringkasan Produk

SMART STUDY ASSISTANT adalah aplikasi web pendamping belajar berbasis webcam untuk mendeteksi **indikasi kantuk**, membantu pengguna mengelola waktu belajar dan istirahat melalui sesi **Pomodoro yang dapat dikustomisasi**, dan memberikan ringkasan sesi serta rekomendasi setelah sesi selesai.

Aplikasi **tidak** mengukur fokus, konsentrasi, produktivitas kognitif, atau kondisi medis. Deteksi kantuk merupakan estimasi berdasarkan indikator visual, bukan diagnosis.

## 1.1 Masalah

Pengguna yang belajar lama dapat mengalami kantuk tanpa segera mengambil jeda. Timer biasa tidak memperhitungkan indikator visual kantuk; sistem deteksi kantuk biasa tidak selalu terhubung dengan alur pengambilan keputusan untuk melanjutkan atau menghentikan sesi belajar.

## 1.2 Tujuan

1. Menyediakan sesi belajar Pomodoro dengan durasi belajar dan istirahat yang ditentukan pengguna.
2. Memantau indikator kantuk secara real-time selama **fase belajar** menggunakan webcam.
3. Memberikan peringatan pertama yang bersifat informatif dan peringatan kedua yang meminta keputusan pengguna jika kantuk tetap terdeteksi.
4. Mendukung alur **lanjut belajar**, **akhiri sesi**, dan **istirahat** yang jelas.
5. Menyajikan ringkasan durasi, indikator kantuk, peringatan, serta rekomendasi pascasesi.

## 1.3 Pengguna sasaran

Pelajar, mahasiswa, dan pengguna laptop/desktop yang ingin mengatur sesi belajar sekaligus menerima pengingat ketika muncul indikasi kantuk.

## 1.4 Ukuran keberhasilan MVP

- Alur `atur durasi → mulai belajar → deteksi → peringatan → keputusan → istirahat/akhir → summary` dapat didemokan.
- Tidak ada peringatan kedua yang dipicu hanya oleh satu frame atau tanpa peringatan pertama dalam satu episode kantuk.
- Timer belajar dan istirahat tetap konsisten saat pop-up tampil.
- Alert visual dan suara berfungsi ketika browser mengizinkan audio.
- Hasil evaluasi model dan uji alur pengguna terdokumentasi; **tidak menetapkan target akurasi yang belum didukung hasil eksperimen**.

---

# 2. Ruang Lingkup

## 2.1 Termasuk dalam MVP

- Konfigurasi durasi belajar dan istirahat kustom.
- Timer belajar dan timer istirahat dengan transisi yang jelas.
- Webcam monitoring **hanya pada fase belajar**.
- YOLO fine-tuned pada **dataset Roboflow kantukv2 saja**.
- Indikator `eye_open`, `eye_closed`, `yawn`, `no_yawn`, `head_straight`, `head_dropped` (nama kelas harus diverifikasi dari `data.yaml`).
- Analisis temporal: blink count, yawn count, prolonged eye closure, dan indikator head dropped.
- Status `NORMAL`, `POSSIBLE_DROWSINESS`, `DROWSY_NEED_REST`, dan `UNCERTAIN/NO_FACE`.
- Alert pertama dan kedua dengan suara dan pop-up.
- Pilihan pada peringatan kedua: **Lanjutkan sesi** atau **Akhiri sesi**.
- Saran tindakan singkat sebelum melanjutkan sesi setelah peringatan kedua.
- Summary, analytics, dan AI recommendations berdasarkan data terstruktur.
- Penyimpanan sesi dan event pada Supabase/PostgreSQL.

## 2.2 Tidak termasuk

- Dataset UTA-RLDD atau dataset eksternal lain untuk training/evaluasi dataset.
- Focus score, concentration analysis, distraction detection, emotion recognition kompleks.
- Diagnosis medis atau kepastian pengguna benar-benar mengantuk.
- Penyimpanan video webcam mentah sebagai default.
- Autentikasi/login wajib (opsional apabila waktu mencukupi).
- Pemaksaan akses audio/autoplay saat browser menolaknya.

**Catatan evaluasi:** pengujian webcam langsung dengan persetujuan pengguna tetap diperlukan untuk menguji timer, kestabilan inferensi, dan event temporal; ini **bukan penambahan dataset training**. Jika hasil pengujian tersebut direkam menjadi dataset, hal itu berada di luar batas dataset tunggal PRD ini.

---

# 3. Dataset dan Pendekatan AI

## 3.1 Sumber data tunggal

**Roboflow Universe — kantukv2:** https://universe.roboflow.com/testproject-8jvqn/kantukv2

- Dataset ini **satu-satunya dataset** yang diunduh untuk training/validation/test model pada MVP.
- Kunci satu versi dataset, format YOLO, tanggal unduh, lisensi, jumlah gambar, split, dan daftar kelas sebelum training.
- Jangan menggabungkan dataset lain, termasuk UTA-RLDD.
- Gunakan split bawaan hanya setelah memeriksa kemungkinan duplikasi atau kebocoran antar split; bila perlu, perbaiki split **dari gambar kantukv2 yang sama**.
- Dokumentasikan ketidakseimbangan kelas dan kualitas anotasi.

## 3.2 Model

- Fine-tuning model **YOLO pretrained** untuk deteksi indikator visual; bukan training dari bobot acak.
- Prediksi frame menghasilkan label, confidence, dan lokasi deteksi.
- Temporal processing menggabungkan prediksi lintas frame menjadi kejadian (`BLINK`, `YAWN`, `PROLONGED_EYE_CLOSURE`, `HEAD_DROPPED`).
- Decision engine berbasis aturan mengubah kejadian tersebut menjadi status indikasi kantuk.
- **MediaPipe dan Random Forest tidak wajib** untuk MVP.

## 3.3 Batasan ilmiah

- Gambar statis tidak menyediakan ground truth durasi kedipan, sehingga kualitas blink/yawn counting tidak dapat dinilai hanya dengan metrik deteksi YOLO.
- `head_dropped` adalah indikator pendukung, bukan bukti tunggal kantuk.
- `drowsiness_score` adalah skor heuristik, **bukan probabilitas medis**.
- Evaluasi mencakup precision, recall, mAP, confusion matrix pada test set kantukv2, ditambah uji fungsional webcam tanpa mengklaim generalisasi luas.

---

# 4. User Journey dan Siklus Pomodoro

```text
HOME
  ↓
SETUP POMODORO
  ├── Pilih durasi belajar (custom)
  └── Pilih durasi istirahat (custom)
  ↓
START STUDY SESSION → izin webcam & audio
  ↓
STUDY TIMER + DROWSINESS MONITORING
  ├── Tidak ada indikasi konsisten → lanjut timer
  ├── Indikasi kantuk pertama → ALERT 1 (suara + pop-up)
  │                                  ↓
  │                         pengguna menutup pop-up
  │                                  ↓
  │                       monitor apakah kantuk berlanjut
  │                                  ↓
  └── Indikasi tetap konsisten → ALERT 2 (suara + pop-up)
                                      ├── AKHIRI SESI → SUMMARY
                                      └── LANJUTKAN → SARAN TINDAKAN
                                                         ↓
                                                   KEMBALI BELAJAR
  ↓
STUDY TIMER HABIS (jika sesi tidak dihentikan)
  ↓
BREAK TIMER (durasi custom; webcam monitoring dijeda)
  ↓
BREAK SELESAI → [MULAI SESI BELAJAR BERIKUTNYA] / [SELESAI]
  ↓
SUMMARY (saat pengguna mengakhiri rangkaian atau memilih selesai)
```

**Definisi:** *sesi belajar* = satu blok timer belajar; *rangkaian Pomodoro* = satu atau lebih blok belajar yang diselingi istirahat. Summary akhir merangkum rangkaian dan, bila perlu, menampilkan rincian per blok.

---

# 5. Kebutuhan Fungsional

| ID | Prioritas | Kebutuhan | Kriteria penerimaan |
|---|---|---|---|
| FR-01 | P0 | Pengguna menentukan durasi belajar | Input menit valid, tersimpan untuk rangkaian aktif |
| FR-02 | P0 | Pengguna menentukan durasi istirahat | Input menit valid, digunakan saat break |
| FR-03 | P0 | Timer belajar berjalan | Countdown akurat berdasarkan waktu berlalu, bukan jumlah render |
| FR-04 | P0 | Webcam dan inferensi aktif selama belajar | Izin diminta; kondisi tanpa izin ditangani |
| FR-05 | P0 | Sistem memproses indikator kantuk | Status tidak ditentukan dari satu frame sporadis |
| FR-06 | P0 | Alert pertama berupa suara dan pop-up | Menampilkan peringatan informatif; tanpa pilihan berhenti/lanjut wajib |
| FR-07 | P0 | Alert kedua muncul jika kantuk masih konsisten | Muncul setelah Alert 1 dan verifikasi ulang, bukan karena timer habis |
| FR-08 | P0 | Alert kedua memberi pilihan tindakan | Tombol `Lanjutkan sesi` dan `Akhiri sesi` tersedia |
| FR-09 | P0 | Akhiri sesi dari Alert 2 | Timer berhenti; event tersimpan; navigasi langsung ke summary |
| FR-10 | P0 | Lanjutkan sesi dari Alert 2 | Saran tindakan muncul sebelum kembali ke monitoring |
| FR-11 | P0 | Timer istirahat | Dapat berjalan setelah waktu belajar selesai atau pengguna memilih break |
| FR-12 | P0 | Transisi akhir istirahat | Pengguna dapat memulai blok berikutnya atau mengakhiri rangkaian |
| FR-13 | P0 | Summary | Durasi belajar/istirahat dan jumlah peringatan ditampilkan |
| FR-14 | P1 | Analytics indikator kantuk | Blink, yawn, eye closure, dan drowsiness events ditampilkan bila tersedia |
| FR-15 | P1 | AI recommendation | Saran berdasarkan metrik terstruktur, bukan frame/video |
| FR-16 | P1 | Riwayat sesi | Pengguna dapat melihat sesi yang tersimpan |
| FR-17 | P0 | Status kamera tidak tersedia | `NO_FACE/UNCERTAIN` tidak dianggap `NORMAL` |
| FR-18 | P0 | Pencegahan alert berulang | Cooldown dan reset episode diterapkan |
| FR-19 | P0 | Kendali manual | Pengguna dapat mengakhiri sesi kapan pun dengan konfirmasi |
| FR-20 | P1 | Kontrol suara | Pengguna dapat mengaktifkan/menonaktifkan bunyi alert |

**Prioritas:** P0 = wajib untuk demo MVP; P1 = penting tetapi boleh disederhanakan bila deadline ketat.

---

# 6. Spesifikasi Timer Pomodoro

## 6.1 Konfigurasi

- Pengguna mengisi **durasi belajar** dan **durasi istirahat** dalam menit.
- **Usulan MVP:** default belajar 25 menit, istirahat 5 menit; masing-masing dapat dikustomisasi antara 1–180 menit untuk belajar dan 1–60 menit untuk istirahat. Rentang ini keputusan desain awal, **bukan ketentuan dari brief**.
- Durasi dikunci untuk blok yang sedang berjalan; perubahan konfigurasi berlaku untuk blok berikutnya agar analytics konsisten.
- Tidak ada kewajiban menjalankan empat siklus atau long break otomatis pada MVP.

## 6.2 Perilaku timer

- Saat `START`, catat timestamp mulai dan target selesai.
- Saat alert muncul, **usulan MVP: timer belajar otomatis dijeda** agar pengguna dapat membaca dan merespons tanpa kehilangan waktu; catat durasi jeda secara terpisah.
- Setelah Alert 1 ditutup, timer dilanjutkan dan monitoring aktif kembali.
- Saat Alert 2 dipilih `Lanjutkan`, timer tetap dijeda selama saran tindakan tampil; tombol `Saya siap melanjutkan` memulai timer kembali.
- Saat waktu belajar habis, hentikan monitoring, tampilkan notifikasi fase selesai, lalu tawarkan `Mulai istirahat`.
- Saat break dimulai, timer istirahat berjalan dan kamera/inferensi dihentikan atau dijeda.
- Saat break habis, tampilkan notifikasi selesai istirahat; **tidak otomatis memulai webcam** tanpa tindakan pengguna.
- Tombol `Akhiri sesi` manual tersedia sepanjang fase belajar dan istirahat, dengan konfirmasi.

## 6.3 Kondisi khusus

- Refresh/tab tertutup: simpan status timer dan timestamp agar dapat dipulihkan secara wajar; bila tidak bisa dipulihkan, tampilkan pilihan mengakhiri sesi, jangan mengarang durasi.
- Tab di background: countdown dihitung dari timestamp aktual, bukan interval JavaScript semata.
- Izin kamera ditolak: timer dapat dijalankan sebagai Pomodoro saja **dengan penanda monitoring nonaktif** (usulan fallback).
- Browser membatasi suara: pop-up tetap wajib muncul; tampilkan status `Suara tidak tersedia` dan tawarkan tombol uji suara.

---

# 7. Logika Dua Tahap Peringatan Kantuk

## 7.1 Definisi episode

Episode kantuk adalah periode ketika indikator visual memenuhi syarat temporal decision engine. Threshold, durasi konfirmasi, dan cooldown **ditentukan dari pengujian**, bukan diasumsikan sebagai angka akurasi ilmiah.

**Usulan state machine:**

```text
MONITORING
  ├── bukti tidak cukup → UNCERTAIN (tanpa alert)
  └── kantuk konsisten → ALERT_1
                            ↓
                      ALERT_1_ACKNOWLEDGED
                            ↓
                      RECHECK / COOLDOWN
                            ├── kondisi pulih → MONITORING (reset episode)
                            └── kantuk berlanjut secara konsisten → ALERT_2
                                                                    ├── END → SUMMARY
                                                                    └── CONTINUE → ADVICE
                                                                                     ↓
                                                                                 MONITORING
```

## 7.2 Peringatan pertama — informatif

**Trigger:** indikasi kantuk konsisten pertama pada blok belajar, ketika waktu belajar **belum habis**.

**Perilaku:**
1. Putar suara alert (jika diizinkan dan tidak dimatikan).
2. Tampilkan pop-up non-diagnostik.
3. Isi contoh: **“Kami mendeteksi tanda-tanda kamu mungkin mengantuk. Sesi belajarmu masih berlangsung. Coba ubah posisi duduk atau istirahatkan mata sejenak.”**
4. Tombol: **`Mengerti`**.
5. Simpan `DROWSINESS_ALERT_1` beserta timestamp dan respons.
6. Setelah ditutup, lakukan recheck; jangan langsung memunculkan Alert 2.

## 7.3 Peringatan kedua — meminta keputusan

**Trigger:** setelah Alert 1 diakui dan fase recheck, indikator kantuk **masih** memenuhi syarat temporal, dengan cooldown yang memadai.

**Perilaku:**
1. Putar suara alert dan tampilkan pop-up kedua.
2. Pesan contoh: **“Tanda-tanda kantuk masih terdeteksi. Apakah kamu ingin melanjutkan sesi belajar atau mengakhirinya sekarang?”**
3. Tombol **`Akhiri sesi`**: hentikan timer dan inferensi, simpan ringkasan dan alasan `ENDED_AFTER_SECOND_ALERT`, langsung buka halaman **Summary**.
4. Tombol **`Lanjutkan sesi`**: buka layar saran tindakan, **belum langsung melanjutkan timer**.
5. Simpan `DROWSINESS_ALERT_2` dan pilihan pengguna.

## 7.4 Saran tindakan setelah memilih lanjut

Tampilkan 2–4 saran ringan, misalnya:

- Berdiri dan melakukan peregangan singkat.
- Minum air putih.
- Mengalihkan pandangan dari layar sebentar.
- Memperbaiki posisi duduk dan pencahayaan.

Tombol: **`Saya siap melanjutkan`** untuk menutup saran dan melanjutkan countdown/monitoring. Saran bukan pengganti tidur yang cukup; jangan menyarankan memaksakan diri jika sangat mengantuk.

**Usulan penanganan episode berulang:** setelah memilih lanjut, aktifkan cooldown dan tunggu kondisi kembali normal secara stabil sebelum episode baru dapat menghasilkan Alert 1 lagi. Jika kondisi kantuk tidak pernah pulih, tampilkan pengingat non-spam dan opsi akhiri/istirahat, tanpa loop pop-up tanpa batas. Perilaku detail harus dikunci saat pengujian UX.

## 7.5 Prioritas kejadian

- Jika waktu belajar habis **sebelum** syarat alert terpenuhi, prioritaskan transisi akhir belajar, bukan membuat alert kantuk terlambat.
- Jika alert sedang terbuka, timer dalam status pause; jangan memicu transisi break secara bersamaan.
- Jika wajah tidak terdeteksi, jangan memicu Alert 1/2 berdasarkan data yang tidak memadai.

---

# 8. Halaman dan UX

| Halaman | Konten utama | Aksi utama |
|---|---|---|
| Home | Penjelasan singkat produk | Mulai |
| Setup Pomodoro | Input menit belajar dan istirahat, indikator izin webcam/audio | Mulai sesi |
| Study Session | Video webcam, countdown, status kantuk, blink/yawn, status monitoring | Akhiri sesi |
| Alert 1 Modal | Pesan indikasi kantuk + suara | Mengerti |
| Alert 2 Modal | Pesan indikasi kantuk berlanjut + suara | Lanjutkan / Akhiri sesi |
| Advice Modal | Saran singkat sebelum lanjut | Saya siap melanjutkan |
| Break Timer | Countdown istirahat, monitoring off | Selesaikan istirahat / Akhiri |
| Summary | Total belajar, istirahat, alert, metrik kantuk, keputusan pengguna | Selesai / Sesi berikutnya |
| History / AI Insights | Riwayat dan rekomendasi berbasis analytics | Lihat detail |

**Prinsip UX:** pop-up mudah dipahami, tindakan utama eksplisit, suara tidak menjadi satu-satunya indikator, dan pengguna tidak terjebak dalam modal.

---

# 9. Arsitektur Teknis

```text
NEXT.JS + TYPESCRIPT
  ├── Pomodoro setup / timer / session state
  ├── Webcam UI
  ├── Alert sound + modal
  ├── Break timer / Summary
  └── Recharts analytics
          │
          ▼
FASTAPI
  ├── YOLO inference (kantukv2 fine-tuned)
  ├── Per-session temporal state
  ├── Drowsiness decision engine
  ├── Two-stage alert state machine
  └── Session/event services
          │
          ▼
SUPABASE / POSTGRESQL
  ├── sessions
  ├── pomodoro_blocks
  ├── breaks
  ├── session_metrics
  └── events
          │
          ▼
LLM API (optional P1)
  └── Structured summary → AI recommendation
```

**Desain yang dipilih untuk MVP:** state temporal dan keputusan alert dikelola **di backend per session ID**, agar tidak bergantung pada hasil satu frame. Frontend mengelola tampilan timer dan mengirim aksi pengguna; backend menyimpan event dan status resmi. Perlu mekanisme sinkronisasi timestamp saat jaringan terputus.

---

# 10. API yang Dibutuhkan (Usulan Kontrak)

| Metode | Endpoint | Fungsi |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/sessions` | Buat rangkaian Pomodoro dengan konfigurasi durasi |
| POST | `/sessions/{id}/blocks` | Mulai blok belajar |
| POST | `/sessions/{id}/predict` | Kirim frame untuk inferensi dan update state temporal |
| POST | `/sessions/{id}/alerts/{alert_id}/respond` | Simpan respons Alert 1/2 |
| POST | `/sessions/{id}/blocks/{block_id}/complete` | Akhiri blok belajar |
| POST | `/sessions/{id}/breaks` | Mulai break dengan durasi yang dikonfigurasi |
| POST | `/sessions/{id}/breaks/{break_id}/complete` | Selesaikan break |
| POST | `/sessions/{id}/end` | Akhiri rangkaian, termasuk dari Alert 2 |
| GET | `/sessions/{id}/summary` | Ambil summary |
| POST | `/sessions/{id}/insights` | Buat AI insight dari data terstruktur |

Contoh respons alert dari backend:

```json
{
  "session_id": "example-session-id",
  "status": "DROWSY_NEED_REST",
  "face_detected": true,
  "alert": {
    "id": "example-alert-id",
    "level": 2,
    "type": "DROWSINESS_ALERT_2",
    "requires_response": true,
    "actions": ["CONTINUE", "END_SESSION"]
  }
}
```

Contoh ini adalah rancangan antarmuka API, **bukan hasil inferensi aktual**.

---

# 11. Model Data

## 11.1 `sessions`

`id`, `user_id` (nullable), `started_at`, `ended_at`, `status`, `configured_study_seconds`, `configured_break_seconds`, `total_study_seconds`, `total_break_seconds`, `total_pause_seconds`, `estimated_drowsy_seconds`, `blink_count`, `yawn_count`, `eye_closure_count`, `drowsiness_event_count`, `alert_1_count`, `alert_2_count`, `end_reason`.

## 11.2 `pomodoro_blocks`

`id`, `session_id`, `sequence_number`, `planned_duration_seconds`, `actual_active_seconds`, `paused_seconds`, `started_at`, `ended_at`, `status`, `end_reason`.

## 11.3 `breaks`

`id`, `session_id`, `after_block_id`, `planned_duration_seconds`, `actual_duration_seconds`, `started_at`, `ended_at`, `status`.

## 11.4 `session_metrics`

`id`, `session_id`, `block_id`, `timestamp`, `drowsiness_score`, `drowsiness_status`, `face_detected`, `eye_state`, `yawn_state`, `head_state`.

## 11.5 `events`

`id`, `session_id`, `block_id` (nullable), `timestamp`, `event_type`, `duration_seconds` (nullable), `metadata`.

Contoh `event_type`: `BLINK`, `YAWN`, `EYE_CLOSURE`, `HEAD_DROPPED`, `DROWSINESS`, `DROWSINESS_ALERT_1`, `DROWSINESS_ALERT_2`, `ALERT_ACKNOWLEDGED`, `CONTINUE_SELECTED`, `END_SELECTED`, `ADVICE_SHOWN`, `STUDY_STARTED`, `STUDY_COMPLETED`, `BREAK_STARTED`, `BREAK_COMPLETED`, `SESSION_ENDED`.

---

# 12. Summary dan AI Recommendation

Summary minimal menampilkan:

- Durasi belajar yang benar-benar berjalan (tidak termasuk pause/modal).
- Durasi istirahat yang sudah dijalankan.
- Jumlah blok Pomodoro selesai dan blok yang dihentikan lebih awal.
- Jumlah Alert 1 dan Alert 2.
- Apakah sesi berakhir normal, manual, atau karena pilihan `Akhiri sesi` pada Alert 2.
- Blink count, yawn count, prolonged eye closure, dan estimasi waktu indikasi kantuk (jika tersedia).
- Timeline peringatan dan keputusan pengguna.

AI recommendation (P1) menerima **hanya ringkasan metrik dan event**, lalu menghasilkan saran istirahat/belajar dengan bahasa hati-hati. AI tidak menerima video mentah dan tidak mengklaim diagnosis.

---

# 13. Non-Functional Requirements

| ID | Kategori | Kebutuhan |
|---|---|---|
| NFR-01 | Privasi | Webcam digunakan dengan izin eksplisit; frame tidak disimpan secara default |
| NFR-02 | Keamanan | Akses API, penyimpanan data, dan konfigurasi secret dilindungi |
| NFR-03 | Ketahanan | Kamera gagal, wajah tidak terdeteksi, API timeout, dan browser menolak audio ditangani dengan pesan jelas |
| NFR-04 | Responsivitas | UI dapat digunakan di desktop/laptop; mobile bukan target utama webcam MVP |
| NFR-05 | Keterlacakan | Alert, pilihan pengguna, durasi timer, dan alasan akhir sesi dicatat |
| NFR-06 | Konsistensi | Tidak ada duplikasi alert akibat request berulang; gunakan event ID/idempotency |
| NFR-07 | Kinerja | Latensi inferensi dan kelancaran timer diukur pada perangkat demo; angka target ditetapkan setelah baseline |
| NFR-08 | Aksesibilitas | Alert disertai teks dan tombol; suara dapat dinonaktifkan; fokus keyboard modal terkelola |
| NFR-09 | Akurasi komunikasi | Status disampaikan sebagai indikasi, bukan diagnosis |

---

# 14. Acceptance Tests / Skenario UAT

| ID | Skenario | Hasil yang diharapkan |
|---|---|---|
| AT-01 | Isi durasi belajar 20 menit dan break 7 menit | Konfigurasi tersimpan dan countdown sesuai |
| AT-02 | Mulai sesi, tidak ada indikasi kantuk konsisten | Timer berjalan tanpa alert kantuk |
| AT-03 | Indikasi kantuk pertama konsisten | Bunyi (jika diizinkan) + pop-up Alert 1; hanya `Mengerti` |
| AT-04 | Pengguna menutup Alert 1, kondisi pulih | Tidak muncul Alert 2 untuk episode tersebut |
| AT-05 | Setelah Alert 1, kantuk tetap konsisten | Bunyi + Alert 2 dengan `Lanjutkan` dan `Akhiri` |
| AT-06 | Pada Alert 2 pilih `Akhiri sesi` | Timer dan inferensi berhenti; langsung ke Summary |
| AT-07 | Pada Alert 2 pilih `Lanjutkan sesi` | Saran tindakan muncul sebelum timer aktif lagi |
| AT-08 | Klik `Saya siap melanjutkan` | Kembali ke sesi dengan sisa waktu yang benar |
| AT-09 | Timer belajar selesai normal | Monitoring berhenti; pilihan mulai break muncul |
| AT-10 | Mulai break 7 menit | Timer break berjalan tanpa deteksi kantuk |
| AT-11 | Timer break selesai | Notifikasi akhir break + pilihan sesi berikutnya/selesai |
| AT-12 | Wajah tidak terdeteksi | Status `UNCERTAIN/NO_FACE`, tidak memicu alert palsu |
| AT-13 | Audio diblokir browser | Pop-up tetap terlihat; pengguna diberi penjelasan |
| AT-14 | Klik tombol akhir sesi manual | Konfirmasi, simpan data, buka Summary |
| AT-15 | Waktu belajar habis saat alert tidak aktif | Transisi ke fase akhir belajar tanpa Alert 2 terlambat |
| AT-16 | Klik respons dua kali / request berulang | Event dan transisi hanya diproses sekali |

**Pengujian model terpisah:** evaluasi YOLO pada test split kantukv2 dan dokumentasikan confusion matrix, precision, recall, mAP, serta kesalahan per kelas. UAT tidak boleh dipakai untuk mengklaim akurasi medis.

---

# 15. Prioritas Pengembangan dan Deadline

| Deadline | Deliverables | Kriteria selesai |
|---|---|---|
| **30 Oktober 2026** | Audit **kantukv2 saja**, fine-tuning YOLO, bobot model, notebook, LoFi termasuk setup Pomodoro dan dua alert | Model dapat inferensi sampel; LoFi mencakup seluruh user journey |
| **6 November 2026** | Evaluasi YOLO, uji webcam/temporal, decision engine, API dasar, HiFi | Metrik terdokumentasi; alur Alert 1 → Alert 2 → keputusan dapat diuji lewat API |
| **13 November 2026** | Website Next.js, timer belajar/break, alert suara+pop-up, Supabase, summary, pengujian end-to-end | Demo utuh dari konfigurasi sampai summary |

## 15.1 Urutan kerja disarankan

1. **25–26 Okt:** Audit kantukv2 dan kunci versi dataset; LoFi untuk Setup, Study, Alert 1, Alert 2, Advice, Break, Summary.
2. **27–30 Okt:** Fine-tuning YOLO dan baseline inference; selesaikan LoFi.
3. **31 Okt–2 Nov:** Evaluasi deteksi, uji webcam dan event temporal; tetapkan threshold sementara berdasarkan hasil.
4. **3–6 Nov:** Backend, state machine alert, kontrak API, HiFi.
5. **7–9 Nov:** Frontend timer, webcam, modal alert, suara, dan break.
6. **10–11 Nov:** Penyimpanan data, summary, analytics; AI insights jika waktu memungkinkan.
7. **12–13 Nov:** End-to-end UAT, bug fixing, dokumentasi dan demo.

## 15.2 Pengurangan scope jika waktu sempit

**Tidak boleh dipotong:** dataset tunggal kantukv2, deteksi, timer belajar custom, timer break custom, dua tahap alert, audio+pop-up (dengan fallback), pilihan lanjut/akhiri, saran sebelum lanjut, summary.

**Boleh disederhanakan:** riwayat sesi mendetail, visualisasi timeline kompleks, AI recommendation, login, multi-device sync.

---

# 16. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Label kantukv2 kurang konsisten | Salah deteksi | Audit visual dan per-kelas sebelum training |
| Kebocoran train/test karena gambar mirip | Metrik terlalu optimistis | Periksa duplikasi dan sumber frame; perbaiki split dari kantukv2 |
| Dataset gambar tidak melabeli blink duration | Penghitung event tidak teruji oleh test set | Uji fungsional langsung pada webcam, laporkan batasannya |
| Kamera laptop berbeda dari domain dataset | Generalisasi lemah | Uji webcam pada kondisi demo; jangan menjanjikan akurasi luas |
| Pop-up muncul terlalu sering | Mengganggu belajar | State machine, cooldown, recheck, reset episode |
| Timer tidak sinkron saat modal/background tab | Durasi salah | Timestamp monotonic/elapsed-time dan pause accounting |
| Browser memblokir audio | Peringatan tidak terdengar | Aktivasi audio lewat interaksi pengguna, fallback visual |
| Pengguna memilih lanjut meski terus mengantuk | Intervensi tidak efektif | Saran tindakan, cooldown, opsi istirahat/akhiri selalu tersedia |
| Waktu pengerjaan sangat singkat | Integrasi terlambat | P0 lebih dulu; AI/history kompleks menjadi P1 |

---

# 17. Keputusan Terbuka Sebelum Implementasi

Berikut merupakan **usulan MVP**, belum keputusan eksplisit pengguna:

1. **Durasi default/rentang:** belajar 25 menit (1–180), istirahat 5 menit (1–60).
2. **Pause otomatis:** timer belajar dijeda ketika Alert 1, Alert 2, atau layar saran terbuka.
3. **Break manual:** setelah timer belajar habis, pengguna menekan `Mulai istirahat`; break tidak dimulai otomatis.
4. **Kamera selama break:** monitoring dijeda demi privasi dan efisiensi.
5. **Pemulihan episode:** Alert 2 hanya setelah Alert 1 diakui dan indikasi tetap ada; episode baru perlu kondisi pulih + cooldown.
6. **Fallback tanpa webcam:** Pomodoro tetap berjalan tetapi fitur kantuk dinonaktifkan.
7. **Siklus Pomodoro:** jumlah blok tidak dibatasi; pengguna memulai blok berikutnya secara manual.

Keputusan teknis yang **harus divalidasi dengan eksperimen:** confidence threshold YOLO, window temporal, syarat Alert 1/2, cooldown, serta performa real-time. Jangan menulis angka final sebelum pengujian.

---

# 18. Definition of Done — MVP

- [ ] Training/evaluasi dataset menggunakan **kantukv2 saja**; versi dan lisensi dicatat.
- [ ] Model YOLO tersimpan, dapat dijalankan dan metrik test set tersedia.
- [ ] Deteksi kantuk menggunakan temporal analysis dan menangani `NO_FACE`.
- [ ] Pengguna dapat mengatur menit belajar dan menit istirahat.
- [ ] Countdown belajar dan break berjalan konsisten.
- [ ] Alert pertama muncul dengan pop-up dan suara bila browser mengizinkan.
- [ ] Alert kedua hanya muncul setelah recheck kantuk yang berkelanjutan.
- [ ] Alert kedua menyediakan aksi **Lanjutkan** dan **Akhiri sesi**.
- [ ] Aksi **Akhiri sesi** langsung menuju Summary.
- [ ] Aksi **Lanjutkan** menampilkan saran tindakan sebelum kembali ke sesi.
- [ ] Break timer tersedia, dengan durasi sesuai konfigurasi pengguna.
- [ ] Summary memuat durasi, event kantuk, peringatan, dan alasan sesi berakhir.
- [ ] Tidak ada fitur focus/concentration/distraction.
- [ ] Alur end-to-end diuji dan didemokan paling lambat **13 November 2026**.

---

**Sumber utama:** `SMART_STUDY_ASSISTANT_Project_Brief_v2.md` (25 Oktober 2026).  
**Sumber perubahan:** ketentuan pengguna tentang dataset tunggal kantukv2, Pomodoro custom, dua tahap alert suara+pop-up, pilihan tindakan, saran sebelum lanjut, dan timer istirahat custom.
