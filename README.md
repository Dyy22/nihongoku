# Nihongoku

Situs belajar bahasa Jepang tingkat dasar (mobile-first, ala Duolingo): kana, 25 pelajaran, latihan, simulasi ujian, dan akun dengan sinkronisasi progres.

- Frontend statis: `template.html` + konten `content/` + `exams/`, dirakit `build.py` menjadi `site/index.html`.
- Backend: Cloudflare Worker + D1 (`worker/`, `migrations/`), email lewat Resend.
- Deploy otomatis: push ke `main` menjalankan `.github/workflows/deploy.yml`.

## Catatan

`build.py` membutuhkan teks buku sumber di `docs/` (tidak ada di repo karena hak cipta), jadi `site/` hasil build ikut di-commit dan CI hanya men-deploy-nya. Setelah mengubah `template.html`, `content/`, atau `exams/`, jalankan `python3 build.py` lalu commit `site/`.

## Secrets GitHub Actions

`CLOUDFLARE_API_TOKEN` dan `CLOUDFLARE_ACCOUNT_ID`. Secret Worker (`RESEND_API_KEY`) tersimpan di Cloudflare, bukan di repo.
