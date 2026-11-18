#!/usr/bin/env python3
"""Generate site/audio/<id>.mp3 untuk tiap teks di audio_texts.json (dibuat oleh build.py) lewat edge-tts.

Jalankan:  .venv/bin/python gen_audio.py   lalu   python3 build.py
File yang sudah ada dilewati, jadi aman dijalankan ulang.
"""
import asyncio
import json
import sys

import edge_tts

from build import AUDIO_DIR, AUDIO_LIST, ROOT, audio_id

TMP_DIR = ROOT / ".audio-tmp"

VOICE = "ja-JP-NanamiNeural"
RATE = "-10%"
CONCURRENCY = 6


async def one(text, sem, stats):
    out = AUDIO_DIR / f"{audio_id(text)}.mp3"
    if out.exists():
        stats["skip"] += 1
        return
    async with sem:
        for attempt in range(4):
            try:
                # file sementara di luar site/, supaya tidak terbaca watcher wrangler atau ikut ter-deploy
                tmp = TMP_DIR / f"{out.stem}.part"
                await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(tmp))
                if tmp.stat().st_size < 500:
                    raise RuntimeError("file audio terlalu kecil")
                tmp.replace(out)
                stats["ok"] += 1
                return
            except Exception as e:  # noqa: BLE001 — coba ulang lalu catat
                err = e
                await asyncio.sleep(2 * (attempt + 1))
        stats["fail"].append((text, str(err)))


async def main():
    texts = json.loads(AUDIO_LIST.read_text(encoding="utf-8"))
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(exist_ok=True)
    sem, stats = asyncio.Semaphore(CONCURRENCY), {"ok": 0, "skip": 0, "fail": []}
    await asyncio.gather(*(one(t, sem, stats) for t in texts))
    print(f"baru {stats['ok']}, sudah ada {stats['skip']}, gagal {len(stats['fail'])} dari {len(texts)}")
    for t, e in stats["fail"][:20]:
        print("  gagal:", t, "—", e)
    sys.exit(1 if stats["fail"] else 0)


if __name__ == "__main__":
    asyncio.run(main())
