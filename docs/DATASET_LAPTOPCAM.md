# Dataset webcam laptop/PC

## Masalahnya
kantukv2 berisi frame **kamera di dalam mobil** (pengemudi, latar kabin). Webcam laptop/PC berbeda: latar, pencahayaan, jarak, sudut, dan kualitas sensor. Model hasil kantukv2 saja akan lebih lemah di webcam (metrik 0,959 mAP50 hanyalah untuk domain mobil). Cara memperbaikinya yang jujur: **data dari webcam laptop**, bukan hanya augmentasi.

> Catatan terhadap PRD: PRD §3.1 menetapkan kantukv2 sebagai satu-satunya dataset. Menambah data webcam sendiri adalah keputusan tim di luar PRD dan harus dicatat di laporan (sumber, jumlah orang, persetujuan).

## Panduan langkah demi langkah

Semua perintah dijalankan dari folder `loopa` (PowerShell). Total waktu: rekam ±15 menit, latih ±1–3 jam di CPU (atau ±15 menit di GPU Colab).

**A. Siapkan (sekali saja)**
1. Buka `backend/.env`, tambahkan baris `ENABLE_DETECT=true`, simpan. Pastikan `frontend/.env.local` berisi `NEXT_PUBLIC_API_URL=http://localhost:8000` (alat ini hanya jalan di lokal, jangan aktifkan di Railway).
2. Buat folder `datasets/laptopcam` (kosong).
3. Jalankan backend dan web: `powershell -ExecutionPolicy Bypass -File start.ps1`. Tunggu sampai http://localhost:3000 terbuka.

**B. Rekam data (±15 menit)**
4. Buka http://localhost:3000/collect di **Chrome atau Edge** (perlu akses folder), izinkan kamera, lalu klik *Choose output folder* dan pilih `datasets/laptopcam`.
5. Isi *Take name* (mis. `lampu-siang-rdj`) dan *Split*, lalu klik *Start guided take*. Satu take ±40 detik, ikuti 5 instruksi di layar: lihat layar, pejamkan mata, menguap lebar, bicara/senyum (bukan menguap), kepala menunduk. Wajah harus terlihat penuh dan tidak terpotong.
6. Satu take menghasilkan sekitar 60–110 gambar. Karena target ≥300 gambar train dan setiap split butuh data, rekam **±8 take**, masing-masing dengan kondisi berbeda dan nama take berbeda:

   | Take | Kondisi | Split |
   |---|---|---|
   | 1–4 | lampu menyala, redup, backlight (jendela di belakang), jarak dekat vs jauh | `train` |
   | 5 | kacamata (jika memakai) atau ruangan lain | `train` |
   | 6 | hari/waktu berbeda | `valid` |
   | 7 | orang lain (dengan persetujuan) atau ruangan lain | `valid` |
   | 8 | kondisi baru yang tidak ada di train | `test` |

   Aturan penting: **satu take hanya boleh di satu split** (frame berurutan sangat mirip, kalau bocor metrik jadi palsu).
7. Setelah tiap take, lihat pratinjau kotak. Kotak harus ada di mata, mulut, dan kepala. Kalau meleset, hapus folder take itu (file diawali nama take-nya di `train/valid/test`) dan ulangi dengan cahaya lebih baik atau lebih dekat ke kamera.

**C. Validasi**
8. `backend\.venv\Scripts\python.exe -I scripts/prepare_laptopcam.py`. Baca bagian PERHATIAN: tidak boleh ada kebocoran take, label rusak, split kosong, atau kelas yang hilang. Perbaiki dengan merekam ulang bila ada. Skrip ini juga membuat `datasets/laptopcam/data.yaml` dan `datasets/combined_data.yaml`.

**D. Ukur dulu model lama (sebagai pembanding)**
9. `backend\.venv\Scripts\python.exe -I scripts/evaluate_yolo.py datasets/laptopcam/data.yaml --weights models/best.pt`. Catat mAP50 dan recall per kelas pada data laptop (hampir pasti lebih rendah dari 0,959 milik kamera mobil).

**E. Latih (fine-tune dari model yang ada)**
10. Di CPU (data kantukv2 ±3.000 gambar + data laptop, hitungan jam):
    ```powershell
    backend\.venv\Scripts\python.exe -I scripts/train_yolo.py datasets/combined_data.yaml --model models/best.pt --epochs 20 --imgsz 416 --batch 16 --device cpu --strong-aug --lr0 0.002 --name laptopcam_ft
    ```
    Untuk uji cepat tambahkan `--fraction 0.3` (hanya memakai 30% data train) dulu untuk memastikan tidak error. Kalau ada GPU (mis. Google Colab), pakai `--device 0 --epochs 40`. Jika data laptop sangat sedikit (<300), tambahkan `--freeze 10`.
    - Hati-hati: skrip ini **menimpa `models/best.pt`** di akhir. Salin dulu `models/best.pt` ke `models/best_kantukv2_backup.pt`.

**F. Evaluasi dan pakai**
11. Bandingkan dengan langkah 9: `backend\.venv\Scripts\python.exe -I scripts/evaluate_yolo.py datasets/laptopcam/data.yaml --weights models/best.pt` (sekarang berisi model baru). Syarat layak dipakai: mAP50 dan recall di **test laptopcam** naik dibanding model lama, dan skor di valid kantukv2 tidak turun jauh.
12. Uji nyata: jalankan sesi di http://localhost:3000, tutup mata ±3 detik, menguap, dan menunduk. Alert harus muncul, dan tidak ada alert saat bicara atau senyum.
13. Kalau lebih baik: salin `models/best.pt` ke `backend/models/best.pt`, commit, lalu `git push` (Railway membangun ulang dan memakai model baru). Kalau lebih buruk: kembalikan dari backup.
14. Matikan `ENABLE_DETECT` di `backend/.env` dan catat di laporan: sumber data (webcam tim), jumlah orang, kondisi, jumlah gambar, persetujuan, dan hasil sebelum/sesudah. Ini keputusan di luar PRD (PRD §3.1 hanya kantukv2).

## Detail alur

1. **Jalankan backend lokal dengan `/detect` aktif** (alat ini hanya untuk lokal): di `backend/.env` set `ENABLE_DETECT=true`, lalu `powershell -ExecutionPolicy Bypass -File start.ps1`.
2. Buka **http://localhost:3000/collect** di Chrome/Edge, izinkan kamera, dan klik *Choose output folder* → pilih `datasets/laptopcam`.
3. **Rekam take terpandu.** Satu take = 5 langkah (±40 detik): menatap layar, menutup mata, menahan menguap lebar, bicara/senyum dengan mulut terbuka (bukan menguap), dan kepala menunduk. Aplikasi menghitung mundur 3 detik di setiap langkah.
   - Kebenaran kelas ditentukan protokol (mis. langkah "tutup mata" = `eye_closed`). Kotak kepala/mata/mulut diambil dari model; frame dibuang bila kotak tidak ditemukan atau model ragu untuk kelas yang tidak ditentukan protokol.
   - **Periksa pratinjau kotak.** Bila kotak tidak berada di mata/mulut/kepala, jangan pakai take itu.
4. **Variasikan kondisi** (satu *take name* per kondisi): lampu menyala/redup/backlight, kacamata, jarak dekat/jauh, ruangan berbeda, orang berbeda (dengan persetujuan), hari berbeda.
5. **Bagi per take, bukan per frame:** pilih `train` untuk sebagian besar take, `valid` untuk 1–2 take, `test` untuk 1–2 take lain. Satu take hanya boleh ada di satu split (frame berurutan sangat mirip, kebocoran akan membuat metrik palsu).
6. **Target minimum yang disarankan:** ≥ 300 frame train, ≥ 3 kondisi berbeda, ≥ 2 orang bila memungkinkan, dan setiap kelas muncul di setiap split.

## Validasi dan gabung

```bash
backend\.venv\Scripts\python.exe -I scripts/prepare_laptopcam.py
```
Melaporkan jumlah gambar/kelas per split, mendeteksi **kebocoran take antar split**, label rusak, kelas yang hilang, lalu menulis `datasets/laptopcam/data.yaml` (hanya domain laptop) dan `datasets/combined_data.yaml` (kantukv2_split + laptopcam; `test` = laptopcam).

## Fine-tuning dari model yang ada

```bash
backend\.venv\Scripts\python.exe -I scripts/train_yolo.py datasets/combined_data.yaml --model models/best.pt --epochs 30 --imgsz 416 --batch 16 --device cpu --strong-aug --lr0 0.002 --name laptopcam_ft
```
- `--model models/best.pt` melanjutkan dari bobot yang sudah ada (bukan dari nol), `--lr0` kecil menjaga pengetahuan lama, `--strong-aug` memperkuat augmentasi cahaya/skala/posisi.
- Untuk hasil terbaik latih di GPU (Colab). Opsi `--freeze 10` membekukan backbone bila data laptop sedikit.

## Evaluasi yang jujur

```bash
backend\.venv\Scripts\python.exe -I scripts/evaluate_yolo.py datasets/laptopcam/data.yaml --weights models/best.pt   # SEBELUM fine-tune: kondisi nyata
backend\.venv\Scripts\python.exe -I scripts/evaluate_yolo.py datasets/laptopcam/data.yaml --weights models/runs/laptopcam_ft/weights/best.pt
```
Bandingkan keduanya pada **test laptopcam** (take yang tidak dipakai training). Laporkan juga uji video (`scripts/replay_video.py`) karena metrik deteksi tidak menilai hitungan blink/yawn. Bila lebih baik, salin ke `models/best.pt` dan `backend/models/best.pt`, lalu `git push` (Railway membangun ulang dari GitHub).

## Privasi
Frame disimpan hanya di folder yang Anda pilih; tidak ada yang diunggah. Jangan commit `datasets/` ke GitHub (sudah diabaikan oleh `.gitignore`). Rekam diri sendiri atau orang yang menyetujui, dan hapus data atas permintaan.
