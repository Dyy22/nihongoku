# Nihongoku

Situs belajar bahasa Jepang tingkat dasar (mobile-first, ala Duolingo): kana, 25 pelajaran, latihan, simulasi ujian, dan akun dengan sinkronisasi progres.

- Frontend statis: `template.html` + konten `content/` + `exams/`, dirakit `build.py` menjadi `site/index.html`.
- Backend: Cloudflare Worker + D1 (`worker/`, `migrations/`), email lewat Resend.
- Deploy otomatis: push ke `main` menjalankan `.github/workflows/deploy.yml`.

## Build

`python3 build.py` merakit `site/index.html` dari `template.html`, `content/` (termasuk daftar kosa kata di `content/kosakata.md`), dan `exams/`. CI menjalankannya sebelum deploy, jadi `site/index.html` tidak di-commit. Audio (`site/audio`, dibuat `gen_audio.py`) dan efek suara (`site/sfx`, dibuat `gen_sfx.py`) di-commit karena butuh layanan eksternal untuk membuatnya.

## Secrets GitHub Actions

`CLOUDFLARE_API_TOKEN` dan `CLOUDFLARE_ACCOUNT_ID`. Secret Worker (`RESEND_API_KEY`) tersimpan di Cloudflare, bukan di repo.
