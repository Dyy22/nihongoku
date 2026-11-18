#!/usr/bin/env python3
"""Cek content/*.md: kanji tanpa furigana dan kurung kurawal yang tidak terpakai."""
import glob
import re
import sys

bad = 0
for f in sorted(glob.glob("content/*.md")):
    if f.endswith("kosakata.md"):  # tabel kana/kanji: furigana dibuat dari kolomnya oleh build.py
        continue
    for n, ln in enumerate(open(f, encoding="utf-8"), 1):
        s = ln.rstrip("\n")
        if s.startswith(("judul:", "ringkas:", "grup:", "sisip:")):
            continue
        t = re.sub(r"[一-鿿々〆0-9０-９]+\{[^}]*\}", "", s)
        k = re.findall(r"[一-鿿々]+", t)
        stray = re.findall(r"\{[^}]*\}", t)
        if k or stray:
            bad += 1
            print(f"{f}:{n}: {k or stray} :: {s[:100]}")
print("ok" if not bad else f"{bad} baris perlu dicek")
sys.exit(1 if bad else 0)
