-- Simpan jumlah iterasi PBKDF2 per akun supaya bisa diubah tanpa merusak password lama
ALTER TABLE users ADD COLUMN pw_iter INTEGER NOT NULL DEFAULT 100000;
