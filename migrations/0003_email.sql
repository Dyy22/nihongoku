-- Email akun: masuk pakai email, verifikasi, dan reset password
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS users_email ON users(email);

-- Token sekali pakai untuk link di email (disimpan sebagai hash SHA-256)
CREATE TABLE IF NOT EXISTS tokens (
  token_hash TEXT    PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT    NOT NULL CHECK (kind IN ('verify', 'reset')),
  expires    INTEGER NOT NULL,
  created    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tokens_user ON tokens(user_id, kind);
