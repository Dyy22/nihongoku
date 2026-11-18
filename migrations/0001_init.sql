-- Akun dan sesi login untuk nihongoku
CREATE TABLE IF NOT EXISTS users (
  id               INTEGER PRIMARY KEY,
  username         TEXT    NOT NULL UNIQUE,
  pw_hash          TEXT    NOT NULL,
  pw_salt          TEXT    NOT NULL,
  fail_count       INTEGER NOT NULL DEFAULT 0,
  locked_until     INTEGER NOT NULL DEFAULT 0,
  progress         TEXT,
  progress_updated INTEGER NOT NULL DEFAULT 0,
  created          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT    PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
