#!/usr/bin/env python3
"""Generate site/audio/<id>.mp3 untuk audio_texts.json dan audio_dialogs.json lewat edge-tts.

Jalankan:  .venv/bin/python gen_audio.py   lalu   python3 build.py
File yang sudah ada dilewati, jadi aman dijalankan ulang.
"""
import asyncio
import json
import subprocess
import sys

import edge_tts

from build import AUDIO_DIR, AUDIO_LIST, DIALOG_LIST, ROOT, audio_id

TMP_DIR = ROOT / ".audio-tmp"

VOICE = "ja-JP-NanamiNeural"
RATE = "-10%"
SPK_VOICE = {
    "n": ("ja-JP-NanamiNeural", "-10%"),
    "f": ("ja-JP-NanamiNeural", "-8%"),
    "m": ("ja-JP-KeitaNeural", "-8%"),
}
CONCURRENCY = 6


async def tts_file(text, voice, rate, dst):
    for attempt in range(4):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(dst))
            if dst.stat().st_size < 300:
                raise RuntimeError("file audio terlalu kecil")
            return
        except Exception as e:  # noqa: BLE001 — coba ulang sebelum menyerah
            err = e
            await asyncio.sleep(2 * (attempt + 1))
    raise err


async def one(text, sem, stats):
    out = AUDIO_DIR / f"{audio_id(text)}.mp3"
    if out.exists():
        stats["skip"] += 1
        return
    async with sem:
        tmp = TMP_DIR / f"{out.stem}.part"
        try:
            await tts_file(text, VOICE, RATE, tmp)
            if tmp.stat().st_size < 500:
                raise RuntimeError("file audio terlalu kecil")
            tmp.replace(out)
            stats["ok"] += 1
        except Exception as e:  # noqa: BLE001 — catat kegagalan
            tmp.unlink(missing_ok=True)
            stats["fail"].append((text, str(e)))


def concat_turns(turn_files, turns, part_out):
    k = len(turn_files)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for tf in turn_files:
        cmd += ["-i", str(tf)]
    filters = []
    for i in range(k):
        flt = f"[{i}:a]aresample=24000,aformat=channel_layouts=mono"
        if i < k - 1:
            pad = 0.75 if (turns[i][0] == "n" or turns[i + 1][0] == "n") else 0.40
            flt += f",apad=pad_dur={pad}"
        flt += f"[a{i}]"
        filters.append(flt)
    concat_in = "".join(f"[a{i}]" for i in range(k))
    filters.append(f"{concat_in}concat=n={k}:v=0:a=1[out]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-codec:a", "libmp3lame", "-b:a", "64k", str(part_out)]
    subprocess.run(cmd, check=True)


async def one_dialog(entry, sem, stats):
    did = entry["id"]
    turns = entry["turns"]
    out = AUDIO_DIR / f"{did}.mp3"
    if out.exists():
        stats["skip"] += 1
        return
    async with sem:
        turn_files = [TMP_DIR / f"{did}_t{i}.mp3" for i in range(len(turns))]
        part = TMP_DIR / f"{did}.part.mp3"
        try:
            for (spk, txt), tf in zip(turns, turn_files):
                voice, rate = SPK_VOICE.get(spk, (VOICE, RATE))
                await tts_file(txt, voice, rate, tf)
            await asyncio.to_thread(concat_turns, turn_files, turns, part)
            if part.stat().st_size < 500:
                raise RuntimeError("file dialog terlalu kecil")
            part.replace(out)
            stats["ok"] += 1
        except Exception as e:  # noqa: BLE001 — catat kegagalan
            stats["fail"].append((f"dialog:{did}", str(e)))
        finally:
            for tf in turn_files:
                tf.unlink(missing_ok=True)
            part.unlink(missing_ok=True)


async def main():
    texts = json.loads(AUDIO_LIST.read_text(encoding="utf-8"))
    dialogs = json.loads(DIALOG_LIST.read_text(encoding="utf-8")) if DIALOG_LIST.exists() else []
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(exist_ok=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    stats = {"ok": 0, "skip": 0, "fail": []}
    await asyncio.gather(
        *(one(t, sem, stats) for t in texts),
        *(one_dialog(d, sem, stats) for d in dialogs),
    )
    total = len(texts) + len(dialogs)
    print(f"baru {stats['ok']}, sudah ada {stats['skip']}, gagal {len(stats['fail'])} dari {total}")
    for t, e in stats["fail"][:20]:
        print("  gagal:", t, "—", e)
    sys.exit(1 if stats["fail"] else 0)


if __name__ == "__main__":
    asyncio.run(main())
