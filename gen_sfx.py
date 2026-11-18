"""Bikin efek suara kuis (benar / salah / pasangan) ke site/sfx/*.mp3.

Disintesis dengan numpy (nada lonceng/marimba + gema pendek), lalu dikodekan
ke MP3 dengan ffmpeg. Jalankan ulang kalau mau mengubah bunyinya:
    python3 gen_sfx.py
"""
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT = Path(__file__).resolve().parent / "site" / "sfx"


def env(n, attack, decay):
    """Amplop: naik cepat lalu meluruh eksponensial (decay = detik sampai ~-60 dB)."""
    t = np.arange(n) / SR
    a = np.clip(t / attack, 0, 1)
    return a * np.exp(-6.9 * t / decay)


def bell(freq, dur, decay, partials, bright=1.0):
    """Nada lonceng/marimba: beberapa harmonik, yang tinggi meluruh lebih cepat."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for ratio, amp in partials:
        d = decay / (1 + (ratio - 1) * 0.9 / bright)
        y += amp * np.sin(2 * np.pi * freq * ratio * t) * env(n, 0.003, d)
    return y


def place(buf, sig, at):
    i = int(at * SR)
    end = min(len(buf), i + len(sig))
    buf[i:end] += sig[: end - i]


def lowpass(y, cutoff):
    """Low-pass satu kutub, cukup untuk melunakkan bunyi."""
    a = np.exp(-2 * np.pi * cutoff / SR)
    out = np.empty_like(y)
    acc = 0.0
    for i, x in enumerate(y):
        acc = (1 - a) * x + a * acc
        out[i] = acc
    return out


def reverb(y, mix=0.18):
    """Gema ruang kecil: beberapa comb filter (Schroeder) dirata-rata."""
    wet = np.zeros(len(y))
    for ms, g in ((29.7, 0.72), (37.1, 0.70), (41.1, 0.68), (43.7, 0.66)):
        d = int(ms / 1000 * SR)
        buf = y.copy()
        for i in range(d, len(buf)):
            buf[i] += g * buf[i - d]
        wet += buf
    wet = lowpass(wet / 4, 5000)
    return (1 - mix) * y + mix * wet


def finish(y, peak):
    fade = int(0.03 * SR)
    y[-fade:] *= np.linspace(1, 0, fade)
    return y / np.max(np.abs(y)) * peak


MARIMBA = [(1, 1.0), (2, 0.35), (3.0, 0.12), (4.0, 0.05)]
SOFT = [(1, 1.0), (2, 0.18), (3, 0.05)]


def correct():
    # "ding-ding!" naik: G5 lalu C6+E6 (terdengar ceria), timbre marimba terang.
    y = np.zeros(int(0.9 * SR))
    place(y, bell(784.0, 0.6, 0.35, MARIMBA, 1.3), 0.0)
    place(y, bell(1046.5, 0.8, 0.55, MARIMBA, 1.3), 0.095)
    place(y, 0.55 * bell(1318.5, 0.8, 0.5, MARIMBA, 1.3), 0.095)
    return finish(reverb(y, 0.2), 0.62)


def wrong():
    # "dum-dum" turun, lembut dan teredam: tidak menyakitkan telinga.
    y = np.zeros(int(0.7 * SR))
    for at, f in ((0.0, 311.1), (0.14, 233.1)):
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        bend = f * (1 - 0.06 * (1 - np.exp(-t / 0.08)))  # sedikit turun nadanya
        ph = 2 * np.pi * np.cumsum(bend) / SR
        sig = (np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)) * env(n, 0.006, 0.32)
        place(y, sig, at)
    return finish(reverb(lowpass(y, 1400), 0.12), 0.55)


def pair():
    # "pop" pendek bernada naik, untuk tiap pasangan yang benar.
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    f = 880 + 520 * (1 - np.exp(-t / 0.025))
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = (np.sin(ph) + 0.2 * np.sin(2 * ph)) * env(n, 0.002, 0.14)
    return finish(reverb(y, 0.12), 0.45)


def write_mp3(name, y):
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        pass
    with wave.open(tmp.name, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    dst = OUT / f"{name}.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-codec:a", "libmp3lame", "-b:a", "96k", str(dst)], check=True)
    Path(tmp.name).unlink()
    print(f"{dst.relative_to(OUT.parent.parent)}: {dst.stat().st_size/1024:.1f} KB")


if __name__ == "__main__":
    write_mp3("benar", correct())
    write_mp3("salah", wrong())
    write_mp3("pasang", pair())
