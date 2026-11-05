# SMART STUDY ASSISTANT
## Sistem Deteksi Kelelahan Belajar dan Manajemen Waktu Istirahat Berbasis Web

---

# 1. Project Brief

## 1.1 Nama Project

**SMART STUDY ASSISTANT**

## 1.2 Judul Project

**SMART STUDY ASSISTANT: Sistem Deteksi Kelelahan Belajar dan Manajemen Waktu Istirahat Berbasis Web**

## 1.3 Konsep

SMART STUDY ASSISTANT adalah aplikasi web yang menggunakan **webcam laptop** untuk menganalisis kondisi visual pengguna selama belajar maupun mengerjakan project.

Pipeline utama:

```text
WEBCAM
   ↓
Face Detection
   ↓
Facial Landmarks
   ↓
Feature Extraction
   ↓
Fatigue & Focus Analysis
   ↓
Decision Engine
   ↓
Rest Recommendation
   ↓
Session Analytics
   ↓
AI Recommendation
```

Sistem tidak hanya mendeteksi kondisi pengguna, tetapi juga memberikan intervensi istirahat dan menyajikan analytics setelah sesi selesai.

---

# 2. Scope MVP

MVP difokuskan pada lima indikator utama:

| Indikator | Data yang Dianalisis |
|---|---|
| Eye Closure | Kondisi mata terbuka/tertutup |
| Blink | Frekuensi dan pola kedipan |
| Yawning | Indikasi mulut terbuka dalam durasi tertentu |
| Head Pose | Pitch, yaw, dan roll |
| Facial Expression | Informasi ekspresi wajah |

Output real-time:

- Focused
- Normal
- Tired
- Drowsy
- Distracted
- Need Rest

Output setelah session:

- Total session duration
- Estimated focused duration
- Number of blinks
- Long eye-closure events
- Yawning count
- Distracted duration
- Fatigue events
- Rest recommendations
- AI-generated summary

---

# 3. Tech Stack

## 3.1 Frontend

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- Recharts

Digunakan untuk:

- Dashboard
- Webcam interface
- Session timer
- Real-time status
- Analytics
- Recommendation page

## 3.2 Computer Vision

### MediaPipe Face Landmarker

Digunakan untuk memperoleh facial landmarks.

Landmarks digunakan untuk mendapatkan:

- Left eye
- Right eye
- Mouth
- Nose
- Face contour

Kemudian landmarks digunakan untuk menghitung:

- EAR
- MAR
- Eye closure
- Blink
- Mouth opening
- Head pose

## 3.3 Machine Learning

- Python
- NumPy
- pandas
- scikit-learn
- joblib

Model utama:

**Random Forest Classifier**

Model digunakan untuk melakukan klasifikasi berbasis fitur, bukan untuk mendeteksi wajah secara langsung.

## 3.4 Backend

- FastAPI
- Python

FastAPI digunakan untuk menyediakan API prediksi model machine learning.

## 3.5 Database

- Supabase
- PostgreSQL

Digunakan untuk menyimpan:

- Session
- Session metrics
- Events
- Analytics

## 3.6 AI Recommendation

LLM API digunakan setelah session selesai untuk menghasilkan rekomendasi berdasarkan analytics.

AI menerima data terstruktur, bukan video webcam mentah.

---

# 4. Arsitektur Sistem

```text
                    ┌───────────────┐
                    │    WEBCAM     │
                    └───────┬───────┘
                            ↓
                  ┌──────────────────┐
                  │    MediaPipe     │
                  │  Face Landmarker │
                  └────────┬─────────┘
                           ↓
                ┌─────────────────────┐
                │ Feature Extraction  │
                │                     │
                │ EAR                 │
                │ MAR                 │
                │ Blink               │
                │ Eye Closure         │
                │ Head Pose           │
                │ Expression          │
                └──────────┬──────────┘
                           ↓
                ┌─────────────────────┐
                │  Random Forest ML   │
                └──────────┬──────────┘
                           ↓
                ┌─────────────────────┐
                │  Decision Engine    │
                │                     │
                │ Focus Score         │
                │ Fatigue Score       │
                └──────────┬──────────┘
                           ↓
               ┌───────────┴───────────┐
               ↓                       ↓
        REST INTERVENTION          SESSION DATA
                                       ↓
                                  SUPABASE
                                       ↓
                                   ANALYTICS
                                       ↓
                              AI RECOMMENDATION
```

---

# 5. Computer Vision Pipeline

## 5.1 Face Landmark Detection

Gunakan MediaPipe Face Landmarker.

Target pertama:

```text
Webcam
  ↓
Face Detection
  ↓
Facial Landmarks
```

Output:

```text
Face landmarks
├── Left eye
├── Right eye
├── Mouth
├── Nose
└── Face contour
```

---

# 6. Eye Aspect Ratio (EAR)

EAR digunakan untuk mengetahui kondisi mata.

Konsep sederhana:

```text
Vertical eye distance
EAR = ─────────────────────
      Horizontal eye distance
```

Interpretasi:

```text
EAR > threshold
→ Eye Open

EAR < threshold
→ Eye Closed
```

Namun, kondisi tidak ditentukan berdasarkan satu frame saja.

Contoh:

```text
Open
Open
Open
Closed
Closed
Open
```

dapat dianggap sebagai blink.

Sedangkan:

```text
Open
Open
Closed
Closed
Closed
Closed
Closed
Open
```

lebih sesuai dianggap sebagai prolonged eye closure atau indikator kantuk.

---

# 7. Blink Detection

Blink detection menggunakan perubahan EAR dari waktu ke waktu.

Data yang disimpan:

```text
blink_count
blink_duration
average_blink_interval
```

Contoh output:

```text
EAR: 0.29
Eye: OPEN
Blink Count: 23
```

---

# 8. Mouth Aspect Ratio (MAR) dan Yawning

MAR digunakan untuk mengukur tingkat keterbukaan mulut.

```text
MAR rendah
→ Mouth Closed

MAR tinggi
→ Mouth Open
```

Untuk menghindari kesalahan mendeteksi percakapan sebagai menguap, yawning tidak ditentukan hanya dari satu frame.

Konsep:

```text
MAR tinggi
    +
durasi cukup lama
    +
pola pergerakan
    ↓
Possible Yawn
```

Data:

```text
yawn_count
yawn_duration
```

---

# 9. Head Pose

Gunakan facial landmarks untuk memperoleh:

- Pitch
- Yaw
- Roll

```text
             Pitch
               ↕
               │
       Yaw ←  HEAD  → Yaw
               │
              Roll
```

Contoh interpretasi:

```text
Head facing screen
→ Likely attentive

Head turned significantly
→ Possible distraction

Head continuously tilted/down
→ Possible fatigue/distraction
```

Interpretasi ini merupakan indikator visual, bukan bukti absolut bahwa pengguna tidak fokus.

---

# 10. Facial Expression

Untuk MVP, facial expression dapat dibuat sederhana.

Pilihan kategori:

```text
Neutral
Engaged
Fatigue-related
```

Facial expression dapat digunakan sebagai fitur tambahan dalam analisis kondisi pengguna.

Jika waktu pengembangan terbatas, komponen ini dapat diposisikan sebagai fitur tambahan, sedangkan indikator utama tetap:

- EAR
- MAR
- Eye closure
- Head pose

---

# 11. Feature Extraction

Semua indikator digabungkan menjadi feature vector.

Contoh:

```text
EAR
MAR
blink_rate
eye_closure_duration
yawn_count
head_yaw
head_pitch
head_roll
facial_expression
```

Contoh dataset:

```csv
ear,mar,blink_rate,eye_closure,head_yaw,head_pitch,emotion,fatigue
0.31,0.18,12,0.02,4,2,neutral,0
0.19,0.20,8,0.21,8,12,tired,1
0.17,0.48,7,0.31,15,18,tired,1
0.30,0.16,14,0.01,2,1,neutral,0
```

---

# 12. Machine Learning Model

## 12.1 Model Utama

Gunakan:

**Random Forest Classifier**

Alasan:

- Cocok untuk feature-based classification
- Tidak membutuhkan GPU besar
- Mudah digunakan
- Mudah dijelaskan saat presentasi
- Dapat melihat feature importance

Alternatif yang dapat dibandingkan:

- Decision Tree
- SVM
- XGBoost

Namun Random Forest dijadikan baseline utama.

---

# 13. Model Classification

Disarankan membuat dua model atau dua output classification.

## 13.1 Fatigue Model

Input:

```text
EAR
Blink
Eye Closure
MAR
Yawn
```

Output:

```text
Normal
Fatigued
```

## 13.2 Focus Model

Input:

```text
Head Pose
Eye Direction
Eye Closure
Facial Expression
```

Output:

```text
Focused
Not Focused
```

Kemudian hasil keduanya digabungkan oleh Decision Engine.

---

# 14. Fatigue dan Focus Score

Gunakan dua skor:

```text
Fatigue Score
Focus Score
```

Contoh:

| Fatigue | Focus | Status |
|---:|---:|---|
| Rendah | Tinggi | Focused |
| Rendah | Rendah | Distracted |
| Tinggi | Sedang | Fatigued |
| Tinggi | Rendah | Need Rest |

Bobot awal dapat ditentukan melalui eksperimen dan evaluasi dataset.

---

# 15. Dataset

Dataset utama dapat dibuat melalui pengumpulan data sendiri.

Fitur yang dikumpulkan:

```text
timestamp
EAR
MAR
blink_rate
eye_closure
yaw
pitch
roll
```

Label:

```text
NORMAL
FATIGUED
FOCUSED
NOT_FOCUSED
```

Dataset kemudian dibagi menjadi:

```text
Training Set
Validation/Test Set
```

Evaluasi menggunakan:

- Accuracy
- Precision
- Recall
- F1-score
- Confusion Matrix

Jangan hanya menggunakan accuracy.

---

# 16. Decision Engine

Decision Engine menggabungkan hasil computer vision dan machine learning.

Konsep:

```text
Eye Closure
Blink Pattern
Yawning
Head Pose
Facial Expression
        ↓
Fatigue Score
Focus Score
        ↓
Decision Engine
```

Contoh rule awal:

```text
IF fatigue_score > threshold
AND condition persists for a defined duration
THEN
    trigger rest recommendation
```

Jangan memicu notifikasi hanya berdasarkan satu frame.

Gunakan temporal smoothing atau rolling window.

Contoh:

```text
Last 10 seconds
        ↓
Multiple fatigue indicators
        ↓
Consistent condition
        ↓
Rest Recommendation
```

---

# 17. Web Application

## 17.1 Home Page

Konten:

```text
SMART STUDY ASSISTANT

Monitor your focus.
Understand your fatigue.
Study smarter.

[ Start Session ]
```

---

# 18. Study Session Page

Contoh struktur:

```text
┌────────────────────────────────────────────┐
│ SMART STUDY ASSISTANT       01:24:32       │
├───────────────────────┬────────────────────┤
│                       │ STATUS             │
│                       │                    │
│       WEBCAM          │ 🟢 Focused         │
│                       │                    │
│                       │ Focus  82%         │
│                       │ Fatigue 18%        │
│                       │                    │
├───────────────────────┴────────────────────┤
│ Today's Session                            │
│                                            │
│ Focus        ███████████████░░ 82%         │
│ Fatigue      ███░░░░░░░░░░░░░ 18%          │
│                                            │
│ Blinks: 47    Yawns: 2                     │
│                                            │
│              [ End Session ]               │
└────────────────────────────────────────────┘
```

---

# 19. Rest Intervention

Ketika kondisi memenuhi threshold:

```text
⚠️ TIME FOR A BREAK

Your current visual indicators suggest
that you may benefit from a short break.

Suggested activities:

- Relax your eyes
- Look away from the screen
- Move your head gently
- Stretch your hands or upper body

[ Take a Break ]
```

Gunakan bahasa seperti "visual indicators suggest" daripada menyatakan pengguna pasti mengalami kelelahan.

---

# 20. Analytics Page

Setelah session:

```text
SESSION ANALYTICS

Total Session
01h 32m

Focused
68 min

Fatigue
17 min

Distracted
7 min
```

Behavioral metrics:

```text
Eye Closure
12 events

Yawning
4 times

Blinks
86 times

Fatigue Events
5 times
```

Focus timeline:

```text
Focus
100% ┤      ╭──╮
 80% ┤──────╯  ╰───╮
 60% ┤              ╰──
 40% ┤
     └─────────────────
      0   30   60   90
```

---

# 21. AI Recommendation

AI digunakan setelah session selesai.

Pipeline:

```text
Session Analytics
       ↓
Structured Summary
       ↓
LLM
       ↓
Personalized Recommendation
```

Contoh input:

```json
{
  "session_duration": 90,
  "focused_minutes": 64,
  "fatigued_minutes": 18,
  "distracted_minutes": 8,
  "yawn_count": 4,
  "eye_closure_events": 12
}
```

Contoh output:

```text
AI INSIGHT

Your focus remained relatively stable during
the first part of the session but decreased
after approximately 50 minutes.

For your next session, consider taking a
short break before continuing when fatigue
indicators begin to increase.
```

AI tidak memproses video webcam mentah.

AI menerima analytics yang sudah dihasilkan sistem.

---

# 22. Database Design

## 22.1 sessions

```text
id
user_id
started_at
ended_at
duration
focused_duration
fatigue_duration
distraction_duration
```

## 22.2 session_metrics

```text
id
session_id
timestamp
ear
mar
blink_rate
head_yaw
head_pitch
fatigue_score
focus_score
status
```

## 22.3 events

```text
id
session_id
timestamp
event_type
duration
```

Contoh event:

```text
YAWN
EYE_CLOSURE
DISTRACTION
FATIGUE
REST
```

---

# 23. Backend API

FastAPI digunakan sebagai service untuk model.

Contoh endpoint:

```text
POST /predict
```

Input:

```json
{
  "ear": 0.19,
  "mar": 0.42,
  "blink_rate": 8,
  "eye_closure": 0.23,
  "yaw": 15,
  "pitch": 12
}
```

Output:

```json
{
  "fatigue_score": 0.78,
  "focus_score": 0.31,
  "status": "NEED_REST"
}
```

---

# 24. Folder Structure

Struktur awal:

```text
smart-study-assistant/
│
├── cv/
│   ├── face_detection.py
│   ├── eye_detection.py
│   ├── mouth_detection.py
│   ├── head_pose.py
│   └── feature_extraction.py
│
├── ml/
│   ├── dataset/
│   ├── train.py
│   ├── evaluate.py
│   └── model/
│
├── backend/
│   ├── main.py
│   ├── routes/
│   └── services/
│
├── web/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── hooks/
│
└── README.md
```

---

# 25. Step-by-Step Pengerjaan

## STEP 1 — Requirement

Tentukan functional requirement.

```text
FR-01 System dapat mengakses webcam.
FR-02 System dapat mendeteksi wajah.
FR-03 System dapat mendeteksi mata.
FR-04 System dapat mendeteksi kondisi mata.
FR-05 System dapat mendeteksi menguap.
FR-06 System dapat mendeteksi head pose.
FR-07 System dapat menghitung fatigue score.
FR-08 System dapat menghitung focus score.
FR-09 System dapat memberikan rest notification.
FR-10 System dapat menyimpan session.
FR-11 System dapat menampilkan analytics.
FR-12 System dapat memberikan AI recommendation.
```

---

## STEP 2 — Prototype Computer Vision

Jangan langsung membuat Next.js.

Buat prototype Python terlebih dahulu.

Target:

```text
Webcam
  ↓
Face Detection
  ↓
Face Landmarks
```

Pastikan landmarks berhasil ditampilkan.

---

## STEP 3 — Implement EAR

Buat perhitungan EAR.

Target output:

```text
EAR: 0.29
Eye: OPEN
```

Pastikan sistem mampu membedakan open dan closed eyes.

---

## STEP 4 — Implement Blink Detection

Tambahkan:

```text
blink_count
blink_duration
```

Target:

```text
Blink Count: 23
```

---

## STEP 5 — Implement MAR dan Yawning

Tambahkan:

```text
MAR
yawn_count
yawn_duration
```

Target:

```text
MAR: 0.41
Yawn: 3
```

---

## STEP 6 — Implement Head Pose

Tambahkan:

```text
Yaw
Pitch
Roll
```

Target:

```text
Yaw: 12°
Pitch: -5°
Roll: 2°
```

---

## STEP 7 — Buat Dataset

Jalankan sistem dan simpan feature:

```text
timestamp
EAR
MAR
blink
eye_closure
yaw
pitch
roll
```

Kemudian beri label:

```text
NORMAL
FATIGUED
FOCUSED
NOT_FOCUSED
```

---

## STEP 8 — Train Machine Learning

Pipeline:

```text
Dataset
   ↓
Train/Test Split
   ↓
Random Forest
   ↓
Evaluation
```

Evaluasi:

```text
Accuracy
Precision
Recall
F1-score
Confusion Matrix
```

---

## STEP 9 — Buat Backend

Buat FastAPI.

Pipeline:

```text
Next.js
   ↓
FastAPI
   ↓
ML Model
   ↓
Prediction
   ↓
Next.js
```

---

## STEP 10 — Integrasikan Next.js

Implement:

- Webcam
- Session timer
- Real-time status
- Fatigue score
- Focus score
- Blink counter
- Yawn counter

---

## STEP 11 — Session Management

Alur:

```text
Start Session
     ↓
Monitoring
     ↓
Record Events
     ↓
Stop Session
     ↓
Save Session
```

---

## STEP 12 — Analytics

Dari session data hitung:

```text
Focused minutes
Fatigued minutes
Distracted minutes
Blink count
Yawn count
Eye closure events
```

---

## STEP 13 — Rest Recommendation

Implement rule engine:

```text
IF fatigue_score > threshold
AND condition persists
THEN
    REST RECOMMENDATION
```

Tambahkan temporal smoothing agar tidak terjadi false alarm dari satu frame.

---

## STEP 14 — AI Recommendation

Pipeline:

```text
Analytics
   ↓
Structured Summary
   ↓
LLM
   ↓
Recommendation
```

---

## STEP 15 — Testing

### Scenario 1 — Focused

```text
User fokus
→ Focused
```

### Scenario 2 — Blink

```text
User menutup mata sebentar
→ Blink
```

### Scenario 3 — Prolonged Eye Closure

```text
User menutup mata cukup lama
→ Eye Closure / Drowsiness Indicator
```

### Scenario 4 — Yawning

```text
User menguap
→ Yawn Event
```

### Scenario 5 — Distraction

```text
User melihat ke samping dalam waktu tertentu
→ Distraction Indicator
```

### Scenario 6 — Fatigue

```text
Fatigue indicators terus muncul
→ Rest Recommendation
```

### Scenario 7 — End Session

```text
End Session
→ Analytics
→ AI Recommendation
```

---

# 26. Development Phases

## Phase 1 — Computer Vision

```text
Webcam
 ↓
Face
 ↓
Landmark
 ↓
EAR
 ↓
MAR
 ↓
Blink
 ↓
Yawn
 ↓
Head Pose
```

## Phase 2 — Machine Learning

```text
Features
 ↓
Dataset
 ↓
Random Forest
 ↓
Fatigue Classification
 ↓
Focus Classification
```

## Phase 3 — Web

```text
Next.js
 ↓
Dashboard
 ↓
Webcam
 ↓
Real-time Status
```

## Phase 4 — System

```text
Session
 ↓
Database
 ↓
Analytics
 ↓
Rest Notification
```

## Phase 5 — AI

```text
Analytics
 ↓
LLM
 ↓
Recommendation
```

---

# 27. MVP Final

Target minimum viable product:

```text
┌─────────────────────────────────────┐
│       SMART STUDY ASSISTANT         │
├────────────────────┬────────────────┤
│                    │ STATUS         │
│                    │                │
│     WEBCAM         │ Focus: 82%     │
│                    │ Fatigue: 18%   │
│                    │                │
│                    │ Blink: 54      │
│                    │ Yawn: 3        │
├────────────────────┴────────────────┤
│ Focus Timeline                       │
│ ████████████████░░░░░               │
│                                     │
│ [ End Session ]                     │
└─────────────────────────────────────┘
```

Setelah session:

```text
SESSION SUMMARY

Duration       90 min
Focused        64 min
Fatigued       18 min
Distracted      8 min

Yawn            4
Blink          81
Eye Closure    12

────────────────────────

AI INSIGHT

Your focus decreased after approximately
50 minutes. Consider taking a short break
before your next session.
```

---

# 28. Final Architecture

```text
                  ┌───────────────┐
                  │    WEBCAM     │
                  └───────┬───────┘
                          ↓
                ┌──────────────────┐
                │    MediaPipe     │
                │  Face Landmarker │
                └────────┬─────────┘
                         ↓
              ┌─────────────────────┐
              │ Feature Extraction  │
              │                     │
              │ EAR                 │
              │ MAR                 │
              │ Blink               │
              │ Eye Closure         │
              │ Head Pose            │
              │ Expression          │
              └──────────┬──────────┘
                         ↓
              ┌─────────────────────┐
              │  Random Forest ML   │
              └──────────┬──────────┘
                         ↓
              ┌─────────────────────┐
              │  Decision Engine    │
              │                     │
              │ Focus Score         │
              │ Fatigue Score       │
              └──────────┬──────────┘
                         ↓
             ┌───────────┴───────────┐
             ↓                       ↓
      REST INTERVENTION          SESSION DATA
                                     ↓
                                SUPABASE
                                     ↓
                                  ANALYTICS
                                     ↓
                              AI RECOMMENDATION
```

---

# 29. Prinsip Pengembangan

1. **Jangan training semua model dari awal.** Gunakan pretrained facial landmark model.
2. **Fokuskan computer vision pada feature extraction.**
3. **Gunakan Random Forest sebagai baseline classifier.**
4. **Gunakan beberapa indikator sekaligus**, bukan satu indikator untuk menentukan fatigue.
5. **Gunakan temporal analysis**, bukan keputusan berdasarkan satu frame.
6. **Pisahkan fatigue dan focus.**
7. **AI recommendation berada di atas analytics**, bukan menggantikan computer vision.
8. **Simpan feature dan event**, bukan video webcam mentah, sebagai default untuk menjaga privasi.
9. **Gunakan istilah "indikasi" atau "estimasi"**, bukan diagnosis kelelahan medis.
10. **Bangun prototype CV terlebih dahulu sebelum membangun web.**

---

# 30. Urutan Implementasi Praktis

Urutan pengerjaan yang direkomendasikan:

```text
1. Setup Python Environment
        ↓
2. Webcam Test
        ↓
3. MediaPipe Face Landmarker
        ↓
4. EAR
        ↓
5. Blink Detection
        ↓
6. MAR
        ↓
7. Yawning Detection
        ↓
8. Head Pose
        ↓
9. Feature Logger
        ↓
10. Dataset Collection
        ↓
11. Random Forest Training
        ↓
12. Model Evaluation
        ↓
13. FastAPI
        ↓
14. Next.js Setup
        ↓
15. Webcam UI
        ↓
16. Real-time Prediction
        ↓
17. Session Management
        ↓
18. Supabase
        ↓
19. Analytics Dashboard
        ↓
20. Rest Intervention
        ↓
21. AI Recommendation
        ↓
22. Integration Testing
        ↓
23. Final Evaluation
```

**Prioritas utama:** selesaikan **Step 1–12** terlebih dahulu. Jika computer vision dan model klasifikasinya sudah stabil, integrasi ke web akan jauh lebih mudah.
