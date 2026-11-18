/* Service worker Nihongoku. Dibangun build.py menjadi site/sw.js; placeholder VERSION diganti hash isi situs,
   jadi tiap deploy yang mengubah situs otomatis memicu pembaruan SW dan cache lama dibuang.

   - Halaman (/): jaringan dulu, cadangan cache  -> selalu versi terbaru bila online, tetap bisa dibuka offline.
   - /audio, /sfx: cache dulu (sfx sudah diisi saat install, audio saat pertama diputar) (cache "media" tidak ikut dibuang saat update).
   - /api/*: tidak pernah disentuh (login, progres, email selalu langsung ke server).
*/
const VERSION = "{{VERSION}}";
const SHELL = `nihongoku-shell-${VERSION}`;
const MEDIA = "nihongoku-media";
const PRECACHE = [
  "/", "/manifest.webmanifest",
  "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png", "/icons/favicon-48.png",
];
const SFX = ["/sfx/benar.mp3", "/sfx/salah.mp3", "/sfx/pasang.mp3"];

self.addEventListener("install", (e) => {
  e.waitUntil(Promise.all([
    caches.open(SHELL).then((c) => c.addAll(PRECACHE)),
    caches.open(MEDIA).then((c) => c.addAll(SFX)),
  ]).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL && k !== MEDIA).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (req.mode === "navigate" || url.pathname === "/" || url.pathname === "/index.html") {
    e.respondWith(page(req));
  } else if (url.pathname.startsWith("/audio/") || url.pathname.startsWith("/sfx/")) {
    e.respondWith(media(req));
  } else {
    e.respondWith(shellFirst(req));
  }
});

async function page(req) {
  const cache = await caches.open(SHELL);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put("/", res.clone());
    return res;
  } catch (err) {
    return (await cache.match("/")) || Response.error();
  }
}

async function shellFirst(req) {
  const cache = await caches.open(SHELL);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) cache.put(req, res.clone());
  return res;
}

// Pemutar audio (terutama Safari) meminta potongan lewat header Range; cache menyimpan berkas utuh,
// jadi potongannya dilayani dari berkas itu.
async function media(req) {
  const cache = await caches.open(MEDIA);
  let res = await cache.match(req.url);
  if (!res) {
    res = await fetch(req.url);
    if (!res.ok) return res;
    cache.put(req.url, res.clone());
  }
  const range = req.headers.get("range");
  const m = range && /^bytes=(\d*)-(\d*)$/.exec(range);
  if (!m || res.status !== 200) return res;
  const buf = await res.arrayBuffer();
  const size = buf.byteLength;
  let start = m[1] === "" ? size - Number(m[2]) : Number(m[1]);
  let end = m[1] === "" || m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
  if (!(start >= 0 && start <= end)) {
    return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
  }
  return new Response(buf.slice(start, end + 1), {
    status: 206,
    headers: {
      "Content-Type": res.headers.get("Content-Type") || "audio/mpeg",
      "Content-Length": String(end - start + 1),
      "Content-Range": `bytes ${start}-${end}/${size}`,
      "Accept-Ranges": "bytes",
    },
  });
}
