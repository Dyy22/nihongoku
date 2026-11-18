# Nihongoku

Situs belajar bahasa Jepang tingkat dasar, mobile-first dan bergaya Duolingo. Live di https://nihongoku.dylab.my.id.

## Fitur

- **Jalur belajar**: unit Hiragana, Katakana, dan Pelajaran 1–25. Tiap unit berisi sesi berisi ±6 kata (kenalan, pilihan ganda, pasangkan, susun kata) dan ujian ★ di akhir. Lulus ujian bab (nilai minimal 70%) menandai semua sesi di bab itu selesai.
- **Materi tertulis**: kosa kata, tata bahasa, dan percakapan tiap pelajaran, plus halaman tambahan (hiragana dan katakana, ungkapan sehari-hari, angka dan tanggal, tabel perubahan kata kerja otomatis).
- **Furigana** di semua kanji, bisa disembunyikan dengan tombol ふ.
- **Suara**: pelafalan Jepang dari file MP3 (edge-tts, `ja-JP-NanamiNeural`), efek suara benar/salah/pasangan, dan tombol untuk mematikan pelafalan.
- **Simulasi ujian**: JLPT N5 dan JFT-Basic A1.
- **Progres**: XP, hari beruntun, target harian, dan latihan ulang untuk kata yang sering salah. Tersimpan di browser dan, kalau masuk akun, disinkronkan ke server.
- **Akun**: daftar dengan username dan password, verifikasi email, masuk dengan email, dan lupa password. Email dikirim lewat Resend.
- **Pencarian** kosa kata (kana, kanji, atau arti), tema terang dan gelap.

## Struktur

| Jalur | Isi |
|---|---|
| `template.html` | Seluruh CSS dan JavaScript situs (SPA dengan router berbasis hash) |
| `content/pelajaran-NN.md` | Tata bahasa dan percakapan tiap pelajaran |
| `content/hal-*.md` | Halaman tambahan di tab Buku |
| `content/kosakata.md` | Daftar kosa kata per pelajaran (sumber untuk Kosa Kata, latihan, pencarian, dan furigana otomatis) |
| `exams/*.json` | Soal simulasi ujian |
| `build.py` | Merakit `site/index.html` dari semua yang di atas, dan menulis `audio_texts.json` |
| `gen_audio.py` | Membuat `site/audio/*.mp3` dari `audio_texts.json` |
| `gen_sfx.py` | Membuat `site/sfx/*.mp3` (efek suara) |
| `check_content.py` | Memeriksa kanji di `content/` yang belum punya furigana |
| `worker/index.js` | API akun (`/api/*`) di Cloudflare Worker |
| `migrations/` | Skema database D1 |
| `wrangler.jsonc` | Konfigurasi Worker: aset, D1, domain, dan variabel |

Penulisan furigana di `content/` memakai `漢字{かんじ}`. Aset statis di `site/` dilayani langsung oleh Cloudflare Workers Static Assets, sedangkan Worker hanya menerima `/api/*`.

## Menjalankan lokal

Butuh Python 3, Node 22, dan `ffmpeg` (hanya untuk `gen_sfx.py`).

```bash
npm ci
```

Bangun situs saja:

```bash
python3 build.py
```

Jalankan situs lengkap dengan API dan database lokal di http://localhost:4173:

```bash
npm run dev
```

Untuk mencoba email secara lokal tanpa mengirim, buat `.dev.vars` berisi `DEV_MAIL_LOG=1`. Email hanya dicatat ke log wrangler.

Setelah menambah atau mengubah kata atau kalimat yang dibacakan, buat audionya dengan edge-tts di virtualenv (`.venv`, sudah di-`.gitignore`) lalu commit file mp3 barunya:

```bash
python3 -m venv .venv && .venv/bin/pip install edge-tts
```
```bash
python3 build.py && .venv/bin/python gen_audio.py
```

## Deploy

Push ke `main` menjalankan `.github/workflows/deploy.yml`: `npm ci`, `python3 build.py`, cek isi `site/`, migrasi D1, lalu `wrangler deploy`. `site/index.html` dibangun di CI dan tidak di-commit. `site/audio` dan `site/sfx` di-commit karena membuatnya butuh layanan eksternal.

Deploy manual dari komputer lokal:

```bash
npm run deploy
```

### Secrets dan variabel

| Nama | Letak | Fungsi |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Secret GitHub Actions | Token dengan izin Workers dan D1 (Edit) |
| `CLOUDFLARE_ACCOUNT_ID` | Secret GitHub Actions | ID akun Cloudflare |
| `RESEND_API_KEY` | Secret Worker (`npx wrangler secret put RESEND_API_KEY`) | Mengirim email |
| `MAIL_FROM` | `vars` di `wrangler.jsonc` | Alamat pengirim email |
| `APP_URL` | `vars` di `wrangler.jsonc` | Alamat situs untuk link di email |

Domain pengirim email (`mail.dylab.my.id`) diverifikasi di Resend lewat record DKIM, SPF, dan MX di DNS Cloudflare, ditambah record DMARC di `_dmarc.dylab.my.id`.

## Catatan

- Worker memakai PBKDF2 dengan 30.000 iterasi supaya muat di batas CPU 10 ms paket gratis Cloudflare. Jumlah iterasi disimpan per akun, jadi nilainya bisa dinaikkan dan akun lama diperbarui saat masuk.
