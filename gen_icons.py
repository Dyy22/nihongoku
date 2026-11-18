"""Bikin ikon PWA ke site/icons/*.png: huruf に putih di atas merah aksen situs.

Butuh Pillow dan font Noto Sans CJK JP (Bold). Jalankan ulang kalau mau mengubah desain:
    python3 gen_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "site" / "icons"
FONT = "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"  # indeks 0 = varian JP
RED = (194, 54, 43)  # --accent di template.html (#c2362b)
GLYPH = "に"
SS = 4  # supersampling supaya tepi halus


def draw(size, *, rounded, glyph_ratio):
    """rounded=True: sudut membulat dan transparan (ikon biasa). False: penuh (maskable/apple)."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=RED + (255,))
    else:
        d.rectangle((0, 0, big, big), fill=RED + (255,))
    font = ImageFont.truetype(FONT, int(big * glyph_ratio), index=0)
    x0, y0, x1, y1 = d.textbbox((0, 0), GLYPH, font=font)
    d.text(((big - (x1 - x0)) / 2 - x0, (big - (y1 - y0)) / 2 - y0), GLYPH, font=font, fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {
        "icon-192.png": (192, True, 0.66),
        "icon-512.png": (512, True, 0.66),
        # maskable: glyph harus di dalam zona aman (lingkaran 80% di tengah)
        "icon-maskable-512.png": (512, False, 0.5),
        "apple-touch-icon.png": (180, False, 0.58),
        "favicon-48.png": (48, True, 0.68),
    }
    for name, (size, rounded, ratio) in jobs.items():
        img = draw(size, rounded=rounded, glyph_ratio=ratio)
        if not rounded:  # iOS dan maskable tidak mendukung transparansi
            img = img.convert("RGB")
        img.save(OUT / name, optimize=True)
        print(f"site/icons/{name}: {(OUT / name).stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
