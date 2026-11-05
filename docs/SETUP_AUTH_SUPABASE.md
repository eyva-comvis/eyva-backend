# Setup ulang Eyva: GitHub → Railway → Vercel → Supabase → Google Sign-In

Panduan ini dibuat setelah rebranding Loopa → Eyva dan pemisahan repo. Semua layanan lama (Vercel, Railway, Supabase, Google OAuth) dihapus, jadi semuanya dibuat dari nol.

Placeholder: `<org>` = organisasi GitHub, `<railway-url>` = domain publik Railway, `<vercel-url>` = domain Vercel, `<ref>` = project ref Supabase.

Urutan penting karena saling bergantung:

| Langkah | Butuh dari langkah lain | Dihasilkan |
|---|---|---|
| 1. GitHub backend | - | repo `eyva-backend` |
| 2. Railway | repo backend | `<railway-url>` |
| 3. Clone frontend | - | folder lokal |
| 4. Vercel | `<railway-url>` | `<vercel-url>` |
| 5. Supabase | `<vercel-url>` | `<ref>`, anon key, secret key |
| 6. Google OAuth | `<ref>`, `<vercel-url>` | Client ID + secret |
| 7. Sambungkan | semua | redeploy Railway + Vercel |

## 1. Push backend ke GitHub

Repo `eyva-backend` di `<org>` dibuat kosong (tanpa README/.gitignore/license).

```bash
cd eyva-backend
git remote add origin https://github.com/<org>/eyva-backend.git
git push -u origin main
```

Cek di GitHub: `models/best.pt` ada, `.env` tidak ada.

## 2. Railway dari GitHub

1. https://railway.com → **New Project** → **Deploy from GitHub repo** → pilih `<org>/eyva-backend`. Jika org tidak muncul: *Configure GitHub App* dan beri akses ke repo itu.
2. Biarkan **Root Directory kosong**. Railway memakai `Dockerfile` di root. Build pertama ±5–10 menit (torch CPU).
3. Service → **Variables** → tambahkan:

   | Variabel | Nilai |
   |---|---|
   | `APP_ENV` | `production` |
   | `CORS_ORIGINS` | sementara `http://localhost:3000`, diganti di langkah 7 |
   | `EYE_CLOSURE_SECONDS` | sesuai kalibrasi (lihat `.env.example`) |
   | `ALERT1_CONFIRM_SECONDS` | idem |
   | `ALERT2_RECHECK_SECONDS` | idem |
   | `ALERT_COOLDOWN_SECONDS` | idem |
   | `LLM_API_KEY` | key OpenRouter (https://openrouter.ai/keys) |
   | `LLM_BASE_URL` | `https://openrouter.ai/api/v1` |
   | `LLM_MODEL` | lihat `.env.example` / README |
   | `LLM_FALLBACK_MODELS` | opsional |
   | `LLM_TIMEOUT_SECONDS` | lihat `.env.example` |

   Jangan set `PORT`; Railway mengisinya. `INFERENCE_BACKEND=yolo`, `MODEL_PATH`, `YOLO_DEVICE`, `YOLO_IMGSZ` sudah ada di `Dockerfile`.
   Variabel Supabase ditambahkan di langkah 7.
4. **Settings → Deploy**: replicas = **1** (state sesi ada di memori).
5. **Settings → Networking → Generate Domain** → catat `<railway-url>`.
6. Tes: `curl https://<railway-url>/health` → `status: ok`, `inference_backend: yolo`, `persistence: false` (belum ada Supabase).

## 3. Clone frontend dari organisasi

```bash
git clone https://github.com/<org>/eyva-frontend.git
cd eyva-frontend
npm install
copy .env.local.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
```

Pastikan nama repo sama dengan yang dibuat di org. Pekerjaan Vezajiva lewat branch/PR, bukan langsung ke `main`.

## 4. Vercel

1. https://vercel.com/new → **Import Git Repository** → pilih `<org>/eyva-frontend`. Jika org tidak muncul: *Adjust GitHub App Permissions*.
2. Framework **Next.js**, Root Directory **kosong** (`./`).
3. **Environment Variables** (Production):
   - `NEXT_PUBLIC_API_URL` = `https://<railway-url>` (tanpa slash di akhir)
   - `NEXT_PUBLIC_SUPABASE_URL` dan `NEXT_PUBLIC_SUPABASE_ANON_KEY` diisi di langkah 7.
4. **Deploy**. Catat `<vercel-url>`.
5. Nilai `NEXT_PUBLIC_*` tertanam saat build, jadi tiap mengubahnya harus **Redeploy**.

## 5. Supabase

1. https://supabase.com → **New project** (catat password database, region dekat Indonesia mis. Singapore).
2. **SQL Editor** → tempel seluruh isi `app/db/schema.sql` dari repo backend → **Run**. Membuat tabel `profiles`, `sessions`, `pomodoro_blocks`, `breaks`, `session_metrics`, `events`, trigger pembuat profil, dan Row Level Security.
3. **Authentication → URL Configuration**:
   - Site URL: `https://<vercel-url>`
   - Redirect URLs: `https://<vercel-url>/**` dan `http://localhost:3000/**`
4. **Project Settings → API Keys**, catat:
   - Project URL: `https://<ref>.supabase.co`
   - Publishable key (anon): aman untuk browser, untuk Vercel
   - Secret key (service_role): **rahasia**, hanya untuk Railway

## 6. Google OAuth

1. https://console.cloud.google.com → buat/pilih project → **APIs & Services → OAuth consent screen**: tipe *External*, nama aplikasi `Eyva`, email dukungan, simpan. Selama status *Testing*, tambahkan email penguji di *Test users*.
2. **Credentials → Create credentials → OAuth client ID** → *Web application*:
   - Authorized JavaScript origins: `https://<vercel-url>` dan `http://localhost:3000`
   - Authorized redirect URIs: `https://<ref>.supabase.co/auth/v1/callback`
3. Salin **Client ID** dan **Client secret**.
4. Supabase → **Authentication → Sign In / Providers → Google** → aktifkan, tempel keduanya, simpan. Secret hanya di dashboard Supabase, jangan di repo atau chat.
5. Untuk publik (bukan hanya test user): isi privacy policy di consent screen dengan `https://<vercel-url>/privacy`, lalu *Publish app*.

## 7. Sambungkan semuanya

Railway (Variables):

| Variabel | Nilai |
|---|---|
| `SUPABASE_URL` | `https://<ref>.supabase.co` (token diverifikasi otomatis lewat JWKS) |
| `SUPABASE_SERVICE_KEY` | Secret key (service_role), isi lewat dashboard |
| `AUTH_REQUIRED` | `false` (tamu boleh) atau `true` (wajib login) |
| `CORS_ORIGINS` | `https://<vercel-url>,http://localhost:3000` |

Vercel (Environment Variables, Production): `NEXT_PUBLIC_SUPABASE_URL` = `https://<ref>.supabase.co`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` = publishable key. Lalu **Redeploy**.

Verifikasi:
1. `GET https://<railway-url>/health` → `"persistence": true` dan `"auth": {"enabled": true, ...}`.
2. Buka `<vercel-url>`: Home menampilkan backend terhubung, tanpa error CORS di DevTools.
3. `/login` → *Continue with Google* → kembali ke aplikasi dalam keadaan login.
4. Jalankan satu sesi penuh, lalu cek riwayat dan baris baru di tabel `sessions` Supabase.

## Perilaku akun

- Pengguna masuk: sesi, riwayat, statistik, dan refleksi tersimpan per akun (`sessions.user_id`). Sesi orang lain tidak bisa diakses (404).
- Tamu: sesi berjalan normal tetapi tidak muncul di riwayat/statistik bila login aktif di backend.
- Username dan avatar diedit di `/profile` (tabel `profiles`, dilindungi RLS; username 3–24 karakter `A-Za-z0-9_.` dan unik).
- Setiap push ke `main` men-deploy otomatis ke Railway/Vercel. Sesi aktif dimuat ulang dari Supabase setelah redeploy (butuh `SUPABASE_SERVICE_KEY`).
