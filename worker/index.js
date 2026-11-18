// API akun nihongoku: daftar, masuk, keluar, sinkron progres, verifikasi email, dan reset password.
// Aset statis (site/) dilayani langsung oleh Workers Static Assets; Worker hanya menerima /api/*.
//
// Variabel lingkungan:
//   RESEND_API_KEY  (secret) API key Resend untuk mengirim email
//   MAIL_FROM       pengirim, mis. "Nihongoku <noreply@domainmu.com>"
//   APP_URL         alamat situs untuk link di email; default: origin permintaan
//   DEV_MAIL_LOG=1  (hanya lokal, lewat .dev.vars) catat email ke log alih-alih mengirim

// Free plan membatasi CPU 10 ms per permintaan; 100.000 iterasi memakai ~22 ms.
// Iterasi disimpan per akun (kolom pw_iter), jadi nilai ini bisa diubah kapan saja.
const PBKDF2_ITER = 30000;
const SESSION_DAYS = 30;
const MAX_FAILS = 5;
const LOCK_MS = 15 * 60 * 1000;
const MAX_PROGRESS_BYTES = 100 * 1024;
const USERNAME_RE = /^[a-z0-9_]{3,20}$/;
const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/;
const TOKEN_TTL = { verify: 3 * 864e5, reset: 60 * 60 * 1000 };
const RESEND_GAP_MS = 2 * 60 * 1000; // jeda minimum antar-email ke akun yang sama

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    try {
      return await route(req, env, ctx, url.pathname.slice(5));
    } catch (e) {
      console.error(e);
      return json({ error: e.userMessage || "Terjadi kesalahan di server. Coba lagi sebentar lagi." }, e.status || 500);
    }
  },
};

async function route(req, env, ctx, path) {
  const m = req.method;
  // Tulis hanya lewat JSON: memaksa preflight CORS untuk permintaan lintas situs.
  if (m !== "GET" && !(req.headers.get("content-type") || "").startsWith("application/json")) {
    return json({ error: "Content-Type harus application/json." }, 415);
  }
  const r = {
    "POST register": register,
    "POST login": login,
    "POST logout": logout,
    "GET me": me,
    "PUT progress": saveProgress,
    "POST forgot": forgot,
    "POST reset": reset,
    "POST verify": verify,
    "POST resend-verify": resendVerify,
    "POST email": changeEmail,
  }[`${m} ${path}`];
  return r ? r(req, env, ctx) : json({ error: "Tidak ditemukan." }, 404);
}

// ---------- handlers ----------

async function register(req, env, ctx) {
  const body = await readJson(req);
  const username = String(body.username || "").trim().toLowerCase();
  const email = normEmail(body.email);
  const password = String(body.password || "");
  if (!USERNAME_RE.test(username)) {
    return json({ error: "Username 3–20 karakter: huruf kecil, angka, atau garis bawah." }, 400);
  }
  if (!EMAIL_RE.test(email)) return json({ error: "Alamat email tidak valid." }, 400);
  const pwErr = checkPassword(password);
  if (pwErr) return json({ error: pwErr }, 400);
  let progress = null;
  if (body.progress && typeof body.progress === "object") {
    const text = JSON.stringify(body.progress);
    if (text.length <= MAX_PROGRESS_BYTES) progress = text;
  }
  const salt = randomB64(16);
  const hash = await hashPassword(password, salt, PBKDF2_ITER);
  const now = Date.now();
  let res;
  try {
    res = await env.DB.prepare(
      "INSERT INTO users (username, email, pw_hash, pw_salt, pw_iter, progress, progress_updated, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    ).bind(username, email, hash, salt, PBKDF2_ITER, progress, progress ? now : 0, now).run();
  } catch (e) {
    const s = String(e);
    if (s.includes("users.email") || s.includes("users_email")) {
      return json({ error: "Email ini sudah terdaftar. Coba masuk, atau pakai Lupa password." }, 409);
    }
    if (s.includes("UNIQUE")) return json({ error: "Username sudah dipakai. Pilih yang lain." }, 409);
    throw e;
  }
  const user = { id: res.meta.last_row_id, username, email };
  ctx.waitUntil(sendVerify(env, req, user).catch((e) => console.error("kirim verifikasi gagal", e)));
  return withSession(env, user.id, publicUser({ ...user, email_verified: 0, progress }));
}

async function login(req, env) {
  const body = await readJson(req);
  const id = String(body.username || "").trim().toLowerCase();
  const password = String(body.password || "");
  let user = null;
  if (id.includes("@")) {
    if (EMAIL_RE.test(id)) user = await env.DB.prepare("SELECT * FROM users WHERE email = ?").bind(id).first();
  } else if (USERNAME_RE.test(id)) {
    user = await env.DB.prepare("SELECT * FROM users WHERE username = ?").bind(id).first();
  }
  const now = Date.now();
  if (user && user.locked_until > now) {
    const min = Math.ceil((user.locked_until - now) / 60000);
    return json({ error: `Terlalu banyak percobaan gagal. Coba lagi dalam ${min} menit.` }, 429);
  }
  // Hitung hash juga saat akun tidak ada, supaya waktu respons tidak membocorkan akun yang terdaftar.
  const hash = await hashPassword(password, user ? user.pw_salt : "AAAAAAAAAAAAAAAAAAAAAA==", user ? user.pw_iter : PBKDF2_ITER);
  if (!user || !timingSafeEqual(hash, user.pw_hash)) {
    if (user) {
      const fails = user.fail_count + 1;
      await env.DB.prepare("UPDATE users SET fail_count = ?, locked_until = ? WHERE id = ?")
        .bind(fails >= MAX_FAILS ? 0 : fails, fails >= MAX_FAILS ? now + LOCK_MS : 0, user.id).run();
    }
    return json({ error: "Username/email atau password salah." }, 401);
  }
  if (user.pw_iter !== PBKDF2_ITER) {
    // Hash ulang dengan jumlah iterasi terbaru setelah password terbukti benar.
    await setPassword(env, user.id, password);
  } else {
    await env.DB.prepare("UPDATE users SET fail_count = 0, locked_until = 0 WHERE id = ?").bind(user.id).run();
  }
  return withSession(env, user.id, publicUser(user));
}

async function logout(req, env) {
  const token = getCookie(req, "sid");
  if (token) await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(await sha256(token)).run();
  return json({ ok: true }, 200, { "Set-Cookie": cookie("", 0) });
}

async function me(req, env) {
  const user = await sessionUser(req, env);
  if (!user) return json({ error: "Belum masuk." }, 401);
  return json(publicUser(user));
}

async function saveProgress(req, env) {
  const user = await sessionUser(req, env);
  if (!user) return json({ error: "Belum masuk." }, 401);
  const text = await req.text();
  if (text.length > MAX_PROGRESS_BYTES) return json({ error: "Data progres terlalu besar." }, 413);
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return json({ error: "JSON tidak valid." }, 400);
  }
  if (!body || typeof body.progress !== "object" || body.progress === null) {
    return json({ error: "Field progress wajib berupa objek." }, 400);
  }
  const now = Date.now();
  await env.DB.prepare("UPDATE users SET progress = ?, progress_updated = ? WHERE id = ?")
    .bind(JSON.stringify(body.progress), now, user.id).run();
  return json({ ok: true, updated: now });
}

// Selalu menjawab sama, supaya tidak membocorkan email mana yang terdaftar.
async function forgot(req, env, ctx) {
  const email = normEmail((await readJson(req)).email);
  if (!EMAIL_RE.test(email)) return json({ error: "Alamat email tidak valid." }, 400);
  mailConfigured(env);
  const user = await env.DB.prepare("SELECT id, username, email FROM users WHERE email = ?").bind(email).first();
  if (user && !(await recentToken(env, user.id, "reset"))) {
    const token = await newToken(env, user.id, "reset");
    const link = `${appUrl(env, req)}/#/reset/${token}`;
    ctx.waitUntil(sendMail(env, user.email, "Atur ulang password Nihongoku", resetMail(user.username, link))
      .catch((e) => console.error("kirim reset gagal", e)));
  }
  return json({ ok: true });
}

async function reset(req, env) {
  const body = await readJson(req);
  const pwErr = checkPassword(String(body.password || ""));
  if (pwErr) return json({ error: pwErr }, 400);
  const row = await useToken(env, String(body.token || ""), "reset");
  if (!row) return json({ error: "Link reset tidak berlaku atau sudah kedaluwarsa. Minta link baru." }, 400);
  await setPassword(env, row.user_id, String(body.password));
  // Password baru: keluarkan semua sesi lama. Email terbukti milik pengguna, jadi sekalian terverifikasi.
  await env.DB.batch([
    env.DB.prepare("DELETE FROM sessions WHERE user_id = ?").bind(row.user_id),
    env.DB.prepare("DELETE FROM tokens WHERE user_id = ? AND kind = 'reset'").bind(row.user_id),
    env.DB.prepare("UPDATE users SET email_verified = 1 WHERE id = ?").bind(row.user_id),
  ]);
  const user = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(row.user_id).first();
  return withSession(env, user.id, publicUser(user));
}

async function verify(req, env) {
  const row = await useToken(env, String((await readJson(req)).token || ""), "verify");
  if (!row) return json({ error: "Link verifikasi tidak berlaku atau sudah kedaluwarsa." }, 400);
  await env.DB.batch([
    env.DB.prepare("UPDATE users SET email_verified = 1 WHERE id = ? AND email = ?").bind(row.user_id, row.email),
    env.DB.prepare("DELETE FROM tokens WHERE user_id = ? AND kind = 'verify'").bind(row.user_id),
  ]);
  return json({ ok: true });
}

async function resendVerify(req, env) {
  const user = await sessionUser(req, env);
  if (!user) return json({ error: "Belum masuk." }, 401);
  if (!user.email) return json({ error: "Akun ini belum punya email." }, 400);
  if (user.email_verified) return json({ ok: true, already: true });
  mailConfigured(env);
  if (await recentToken(env, user.id, "verify")) {
    return json({ error: "Email verifikasi baru saja dikirim. Tunggu 2 menit sebelum minta lagi." }, 429);
  }
  await sendVerify(env, req, user);
  return json({ ok: true });
}

async function changeEmail(req, env) {
  const user = await sessionUser(req, env);
  if (!user) return json({ error: "Belum masuk." }, 401);
  const email = normEmail((await readJson(req)).email);
  if (!EMAIL_RE.test(email)) return json({ error: "Alamat email tidak valid." }, 400);
  if (email === user.email) return json(publicUser(user));
  mailConfigured(env);
  try {
    await env.DB.batch([
      env.DB.prepare("UPDATE users SET email = ?, email_verified = 0 WHERE id = ?").bind(email, user.id),
      env.DB.prepare("DELETE FROM tokens WHERE user_id = ?").bind(user.id),
    ]);
  } catch (e) {
    if (String(e).includes("UNIQUE")) return json({ error: "Email ini sudah dipakai akun lain." }, 409);
    throw e;
  }
  await sendVerify(env, req, { ...user, email });
  return json(publicUser({ ...user, email, email_verified: 0 }));
}

// ---------- email ----------

async function sendVerify(env, req, user) {
  const token = await newToken(env, user.id, "verify");
  const link = `${appUrl(env, req)}/#/verify/${token}`;
  await sendMail(env, user.email, "Konfirmasi email akun Nihongoku", verifyMail(user.username, link));
}

function mailConfigured(env) {
  if (env.RESEND_API_KEY || env.DEV_MAIL_LOG === "1") return;
  const e = new Error("RESEND_API_KEY belum diatur");
  e.userMessage = "Pengiriman email belum diaktifkan di server ini.";
  e.status = 503;
  throw e;
}

async function sendMail(env, to, subject, { html, text }) {
  if (!env.RESEND_API_KEY) {
    if (env.DEV_MAIL_LOG === "1") {
      console.log(`[DEV MAIL] ke=${to} subjek="${subject}"\n${text}`);
      return;
    }
    mailConfigured(env);
  }
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({ from: env.MAIL_FROM, to: [to], subject, html, text }),
  });
  if (!r.ok) {
    const e = new Error(`Resend ${r.status}: ${await r.text()}`);
    e.userMessage = "Email gagal dikirim. Coba lagi beberapa menit lagi.";
    e.status = 502;
    throw e;
  }
}

function mailShell(title, intro, button, link, outro) {
  const html = `<!doctype html><html lang="id"><body style="margin:0;background:#f6f2ea;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#1d1b18">
<div style="max-width:480px;margin:0 auto;padding:32px 20px">
<p style="margin:0 0 20px;color:#c2362b;font-weight:700;letter-spacing:.08em">にほんごく · Nihongoku</p>
<h1 style="margin:0 0 12px;font-size:22px">${title}</h1>
<p style="margin:0 0 24px;line-height:1.6">${intro}</p>
<a href="${link}" style="display:inline-block;padding:14px 22px;border-radius:12px;background:#2c8a57;color:#fff;font-weight:700;text-decoration:none">${button}</a>
<p style="margin:24px 0 0;font-size:13px;line-height:1.6;color:#6f6a61">${outro}<br>Kalau tombol tidak bisa diklik, buka link ini:<br><a href="${link}" style="color:#35589f;word-break:break-all">${link}</a></p>
</div></body></html>`;
  const plain = (s) => s.replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
  const text = `${plain(title)}\n\n${plain(intro)}\n\n${button}: ${link}\n\n${outro}`;
  return { html, text };
}

function verifyMail(username, link) {
  return mailShell(
    `Halo, ${esc(username)}!`,
    "Satu langkah lagi: konfirmasi bahwa email ini milikmu, supaya kamu bisa memulihkan akun kalau lupa password.",
    "Konfirmasi email",
    link,
    "Link berlaku 3 hari. Kalau kamu tidak mendaftar di Nihongoku, abaikan email ini.",
  );
}

function resetMail(username, link) {
  return mailShell(
    "Atur ulang password",
    `Ada permintaan untuk mengatur ulang password akun <b>${esc(username)}</b>. Pilih password baru lewat tombol di bawah.`,
    "Buat password baru",
    link,
    "Link berlaku 1 jam dan hanya bisa dipakai sekali. Kalau kamu tidak meminta ini, abaikan saja: passwordmu tidak berubah.",
  );
}

// ---------- tokens ----------

async function newToken(env, userId, kind) {
  const token = randomB64(32);
  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM tokens WHERE user_id = ? AND kind = ?").bind(userId, kind),
    env.DB.prepare("INSERT INTO tokens (token_hash, user_id, kind, expires, created) VALUES (?, ?, ?, ?, ?)")
      .bind(await sha256(token), userId, kind, now + TOKEN_TTL[kind], now),
  ]);
  return token;
}

async function recentToken(env, userId, kind) {
  return env.DB.prepare("SELECT 1 FROM tokens WHERE user_id = ? AND kind = ? AND created > ?")
    .bind(userId, kind, Date.now() - RESEND_GAP_MS).first();
}

// Mengembalikan baris token (plus email akun) bila sah, lalu menghapusnya supaya sekali pakai.
async function useToken(env, token, kind) {
  if (!/^[A-Za-z0-9_-]{20,64}$/.test(token)) return null;
  const h = await sha256(token);
  const row = await env.DB.prepare(
    "SELECT t.user_id, t.expires, u.email FROM tokens t JOIN users u ON u.id = t.user_id WHERE t.token_hash = ? AND t.kind = ?",
  ).bind(h, kind).first();
  if (!row) return null;
  await env.DB.prepare("DELETE FROM tokens WHERE token_hash = ?").bind(h).run();
  return row.expires > Date.now() ? row : null;
}

// ---------- sessions & users ----------

async function withSession(env, userId, payload) {
  const token = randomB64(32);
  const expires = Date.now() + SESSION_DAYS * 864e5;
  await env.DB.batch([
    env.DB.prepare("DELETE FROM sessions WHERE user_id = ? AND expires < ?").bind(userId, Date.now()),
    env.DB.prepare("INSERT INTO sessions (token_hash, user_id, expires) VALUES (?, ?, ?)").bind(await sha256(token), userId, expires),
  ]);
  return json(payload, 200, { "Set-Cookie": cookie(token, SESSION_DAYS * 86400) });
}

async function sessionUser(req, env) {
  const token = getCookie(req, "sid");
  if (!token) return null;
  return env.DB.prepare(
    "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires > ?",
  ).bind(await sha256(token), Date.now()).first();
}

async function setPassword(env, userId, password) {
  const salt = randomB64(16);
  await env.DB.prepare("UPDATE users SET pw_hash = ?, pw_salt = ?, pw_iter = ?, fail_count = 0, locked_until = 0 WHERE id = ?")
    .bind(await hashPassword(password, salt, PBKDF2_ITER), salt, PBKDF2_ITER, userId).run();
}

function publicUser(u) {
  let progress = null;
  try {
    progress = typeof u.progress === "string" ? JSON.parse(u.progress) : u.progress || null;
  } catch {}
  return { username: u.username, email: u.email || null, emailVerified: !!u.email_verified, progress };
}

function checkPassword(pw) {
  return pw.length < 8 || pw.length > 128 ? "Password minimal 8 karakter." : null;
}

function normEmail(v) {
  return String(v || "").trim().toLowerCase();
}

function appUrl(env, req) {
  return (env.APP_URL || new URL(req.url).origin).replace(/\/$/, "");
}

function cookie(value, maxAge) {
  return `sid=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

function getCookie(req, name) {
  const raw = req.headers.get("cookie") || "";
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

// ---------- crypto ----------

async function hashPassword(password, saltB64, iterations) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: fromB64(saltB64), iterations },
    key,
    256,
  );
  return toB64(new Uint8Array(bits));
}

async function sha256(text) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

function randomB64(n) {
  return toB64(crypto.getRandomValues(new Uint8Array(n))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function toB64(bytes) {
  return btoa(String.fromCharCode(...bytes));
}
function fromB64(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(s + "=".repeat((4 - (s.length % 4)) % 4)), (c) => c.charCodeAt(0));
}

// ---------- utils ----------

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

async function readJson(req) {
  try {
    const text = await req.text();
    if (text.length > MAX_PROGRESS_BYTES + 1024) return {};
    return JSON.parse(text) || {};
  } catch {
    return {};
  }
}

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}
