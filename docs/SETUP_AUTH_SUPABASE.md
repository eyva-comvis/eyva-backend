# Setup: Supabase, Sign in with Google, dan deploy dari GitHub

Status proyek Supabase `loopa` (org *Admrlrdj's Org*, region Paris/eu-west-3):
- URL: `https://siarvaknnerwvidoxqdi.supabase.co`
- Skema (`backend/app/db/schema.sql`) **sudah dijalankan**: tabel `profiles`, `sessions`, `pomodoro_blocks`, `breaks`, `session_metrics`, `events`, trigger pembuat profil, dan Row Level Security.
- Auth → URL Configuration: Site URL `https://loopa-smart-study.vercel.app`, Redirect URLs `https://loopa-smart-study.vercel.app/**` dan `http://localhost:3000/**`.

## 1. Aktifkan Sign in with Google (wajib dilakukan pemilik akun)

1. Buka https://console.cloud.google.com → pilih/buat project → **APIs & Services → OAuth consent screen**: tipe *External*, isi nama aplikasi (Loopa), email dukungan, lalu simpan. Tambahkan email penguji di *Test users* bila status masih *Testing*.
2. **Credentials → Create credentials → OAuth client ID** → *Web application*:
   - Authorized JavaScript origins: `https://loopa-smart-study.vercel.app` dan `http://localhost:3000`
   - Authorized redirect URIs: `https://siarvaknnerwvidoxqdi.supabase.co/auth/v1/callback`
3. Salin **Client ID** dan **Client secret**.
4. Supabase → **Authentication → Sign In / Providers → Google** → aktifkan, tempel Client ID dan Client secret, simpan. (Secret hanya diisi di dashboard Supabase, jangan di repo atau chat.)
5. Uji: buka `/login` → *Continue with Google*.

## 2. Variabel lingkungan

| Tempat | Variabel | Nilai |
|---|---|---|
| Vercel (Production) | `NEXT_PUBLIC_API_URL` | `https://loopa-backend-production-44f3.up.railway.app` |
| Vercel (Production) | `NEXT_PUBLIC_SUPABASE_URL` | `https://siarvaknnerwvidoxqdi.supabase.co` |
| Vercel (Production) | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Publishable key (Supabase → Settings → API Keys). Aman untuk browser. |
| Railway (`loopa-backend`) | `SUPABASE_URL` | `https://siarvaknnerwvidoxqdi.supabase.co` (otomatis memverifikasi token lewat JWKS) |
| Railway (`loopa-backend`) | `SUPABASE_SERVICE_KEY` | **Secret key** (Supabase → Settings → API Keys). Rahasia: isi lewat dashboard Railway. |
| Railway (`loopa-backend`) | `AUTH_REQUIRED` | `false` (tamu boleh) atau `true` (wajib login) |
| Railway (`loopa-backend`) | `CORS_ORIGINS` | `https://loopa-smart-study.vercel.app,http://localhost:3000` |

Cek hasilnya: `GET /health` harus menampilkan `"persistence": true` dan `"auth": {"enabled": true, ...}`.

## 3. Deploy otomatis dari GitHub (`Admrlrdj/loopa`, branch `main`)

**Railway** (`loopa-backend`): Settings → Source → *Connect Repo* → `Admrlrdj/loopa`, branch `main`, **Root Directory `backend`** (memakai `backend/Dockerfile`; `backend/models/best.pt` harus ada di repo).

**Vercel** (`loopa-smart-study`): Settings → Git → *Connect Git Repository* → `Admrlrdj/loopa`; Settings → General → **Root Directory `frontend`**, Framework Next.js.

**Status: keduanya sudah terhubung ke `Admrlrdj/loopa` (Railway Root Directory `/backend`, Vercel Root Directory `frontend`).** Setiap `git push` ke `main` men-deploy keduanya; jangan lagi memakai `vercel deploy` dari folder `frontend`. Sesi disimpan ke Supabase (write-behind) dan sesi yang sedang berjalan dimuat ulang dari database saat dibutuhkan, jadi redeploy tidak mereset sesi (butuh `SUPABASE_SERVICE_KEY`; sinkronisasi terakhir sebelum redeploy bisa tertinggal beberapa detik).

## 4. Perilaku akun

- Pengguna masuk: sesi, riwayat, statistik, dan refleksi tersimpan per akun (`sessions.user_id`). Sesi orang lain tidak bisa diakses (dijawab 404).
- Tamu (tanpa login): sesi berjalan normal tetapi tidak muncul di riwayat/statistik bila login aktif di backend.
- Username dan avatar diedit di `/profile` (tabel `profiles`, dilindungi RLS; username 3–24 karakter `A-Za-z0-9_.` dan unik).
