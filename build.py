#!/usr/bin/env python3
"""Bangun site/index.html (satu file, tanpa dependensi) dari content/.

Jalankan:  python3 build.py
"""
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "content" / "kosakata.md"
OUT = ROOT / "site" / "index.html"
TEMPLATE = ROOT / "template.html"

PART_KEYS = {"I": "kosa", "II": "terj", "III": "ref", "IV": "tata"}
AUDIO_DIR = ROOT / "site" / "audio"
AUDIO_LIST = ROOT / "audio_texts.json"
DIALOG_LIST = ROOT / "audio_dialogs.json"

# baris kana untuk unit Dasar (hiragana; katakana diturunkan di klien)
KANA_ROWS = ("あa いi うu えe おo|かka きki くku けke こko|さsa しshi すsu せse そso|たta ちchi つtsu てte とto|"
             "なna にni ぬnu ねne のno|はha ひhi ふfu へhe ほho|まma みmi むmu めme もmo|やya ゆyu よyo|"
             "らra りri るru れre ろro|わwa をo んn|がga ぎgi ぐgu げge ごgo|ざza じji ずzu ぜze ぞzo|"
             "だda ぢji づzu でde どdo|ばba びbi ぶbu べbe ぼbo|ぱpa ぴpi ぷpu ぺpe ぽpo")


def say_text(kana: str) -> str:
    """Teks yang dibacakan: kolom kana tanpa alternatif, tanda opsional, dan penanda kelompok."""
    t = re.split(r"[(（／]", kana)[0]
    t = re.sub(r"[\[\]～－*ⅠⅡⅢ…]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def to_kata(s: str) -> str:
    return "".join(chr(ord(c) + 96) if "\u3041" <= c <= "\u3096" else c for c in s)


def audio_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


PART_LABELS = [("kosa", "Kosa Kata"), ("tata", "Tata Bahasa"), ("cakap", "Percakapan")]
CONTENT = ROOT / "content"
EXAMS_DIR = ROOT / "exams"
DRILLS_DIR = ROOT / "drills"
DIALOGS = {}


# ---------- markdown mini-renderer ----------

def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"<em>\1</em>", s)
    return annotate(s) if ANNOTATE else s


K = r"[\u4e00-\u9fff々〆0-9０-９]"
KANA_ONLY = re.compile(r"^[\u3041-\u3096\u30a1-\u30faー]+$")
FURI = {}      # (run, next_char) -> {reading}; (run, None) -> {reading}
ANNOTATE = False


def furi(kana: str, kanji: str, pairs=None) -> str:
    """Sejajarkan kolom kana dengan kolom kanji -> HTML <ruby> per rangkaian kanji."""
    if "、" in kanji and "、" not in kana:
        return "、".join(furi(kana, k.strip(), pairs) for k in kanji.split("、"))
    parts = [p for p in re.split(f"({K}+)", kanji) if p]
    body = ""
    for p in parts:
        if re.match(K, p):
            body += "(.+?)"
        else:
            body += r"\s*" + "".join(r"\s*" if ch.isspace() else re.escape(ch) for ch in p) + r"\s*"
    # tanda kelompok kata kerja (Ⅰ/Ⅱ/Ⅲ) dan * hanya ada di kolom kana: lepas dulu, tempel lagi di akhir
    marks = "".join(re.findall(r"\s*[ⅠⅡⅢ]|\*", kana)) if not re.search(r"[ⅠⅡⅢ*]", kanji) else ""
    star = (" " + marks.replace(" ", "")) if "Ⅰ" in marks or "Ⅱ" in marks or "Ⅲ" in marks else marks
    if marks:
        kana = re.sub(r"\s*[ⅠⅡⅢ]|\*", "", kana)
    runs = [p for p in parts if re.match(K, p)]
    m = None
    for pat in ("^()" + body + "()$", r"^(.*\s)?" + body + r"(\s.*)?$"):
        m = re.match(pat, kana)
        if m and all(KANA_ONLY.match(g) for g in m.groups()[1:-1]):
            break
        m = None
    if not m:
        return f"<ruby>{html.escape(kanji)}<rt>{html.escape(kana)}</rt></ruby>"
    out, gi = html.escape(m.group(1) or ""), 2
    for i, p in enumerate(parts):
        if re.match(K, p):
            r = m.group(gi); gi += 1
            out += f"<ruby>{p}<rt>{r}</rt></ruby>"
            if pairs is not None:
                nxt = parts[i + 1][0] if i + 1 < len(parts) else ""
                pairs.append((p, nxt, r))
        else:
            out += html.escape(p)
    return out + html.escape(m.group(len(runs) + 2) or "") + star


def annotate(s: str) -> str:
    """Beri furigana pada kanji di teks biasa, hanya bila bacaannya tunggal di daftar kosa kata."""
    def sub(m):
        run, nxt = m.group(1), m.group(2)
        r = FURI.get((run, nxt)) or FURI.get((run, None))
        if r and len(r) == 1:
            return f"<ruby>{run}<rt>{next(iter(r))}</rt></ruby>{nxt}"
        return m.group(0)
    return re.sub(r"([\u4e00-\u9fff々〆]+)(.?)", sub, s)


def cells(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


class Renderer:
    def __init__(self, lesson=None, vocab=None):
        self.lesson = lesson
        self.vocab = vocab  # list to append [kana, kanji, arti, lesson, idx]
        self.vi = 0

    def table(self, rows):
        head = cells(rows[0])
        body = [cells(r) for r in rows[1:] if not re.match(r"^\|?\s*:?-{2,}", r.strip())]
        if head and head[0].startswith("Kana / Bacaan") and len(head) == 3:
            return self.vocab_table(body)
        out = ['<div class="tw"><table><thead><tr>']
        out += [f"<th>{inline(h)}</th>" for h in head]
        out.append("</tr></thead><tbody>")
        for r in body:
            if r and r[0].startswith("**") and not any(r[1:]):
                out.append(f'<tr class="grp"><td colspan="{len(head)}">{inline(r[0])}</td></tr>')
                continue
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
        out.append("</tbody></table></div>")
        return "".join(out)

    def vocab_table(self, body):
        out = ['<ul class="vocab">']
        for r in body:
            r = (r + ["", "", ""])[:3]
            if r[0].startswith("**") and not r[1] and not r[2]:
                label = re.sub(r"^\*\*▸?\s*|\*\*$", "", r[0])
                out.append(f'<li class="vg">{inline(label)}</li>')
                continue
            vid = ""
            if self.vocab is not None and self.lesson:
                vid = f' id="v-{self.lesson}-{self.vi}"'
            rb = furi(r[0], r[1]) if r[1] else ""
            if vid:
                self.vocab.append([r[0], r[1], r[2], self.lesson, self.vi, rb, say_text(r[0])])
                self.vi += 1
            out.append(
                f'<li class="v"{vid}><div class="jp"><span class="kn" lang="ja">{rb or html.escape(r[0])}</span></div>'
                f'<div class="ar">{inline(r[2])}</div></li>'
            )
        out.append("</ul>")
        return "".join(out)

    def render(self, lines):
        out, para = [], []

        def flush():
            if para:
                out.append("<p>" + "<br>".join(para) + "</p>")
                para.clear()

        i = 0
        while i < len(lines):
            ln = lines[i].rstrip()
            st = ln.strip()
            if not st:
                flush()
            elif st.startswith("<!--"):
                flush()
            elif re.match(r"^#{2,6}\s", st):
                flush()
                lvl = len(st) - len(st.lstrip("#"))
                text = st[lvl:].strip()
                text = re.sub(r"^Pelajaran \d+ · ", "", text)
                out.append(f"<h{lvl}>{inline(text)}</h{lvl}>")
            elif st.startswith("|"):
                flush()
                rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append(lines[i])
                    i += 1
                out.append(self.table(rows))
                continue
            elif st.startswith(">"):
                flush()
                out.append(f"<blockquote>{inline(st.lstrip('> '))}</blockquote>")
            else:
                m = re.match(r"^(\s*)(?:(\d+)[.)]|[-*])\s+(.*)$", ln)
                if m:
                    flush()
                    lv = min(len(m.group(1)) // 2, 3)
                    mark = f"{m.group(2)}." if m.group(2) else "•"
                    out.append(f'<div class="li l{lv}"><span class="mk">{mark}</span><span>{inline(m.group(3))}</span></div>')
                else:
                    para.append(inline(st))
            i += 1
        flush()
        return "\n".join(out)


# ---------- konten sendiri (content/*.md) ----------
# Format ringkas:
#   漢字{かんじ}          -> furigana
#   ## / ###              -> judul bagian
#   > teks                -> kotak pola
#   !! teks               -> kotak tips
#   - jepang | indonesia  -> contoh kalimat (dengan tombol suara)
#   Nama: jepang | indo   -> baris percakapan
#   | a | b |             -> tabel
RUBY_RE = re.compile(r"([\u4e00-\u9fff々〆0-9０-９]+)\{([\u3041-\u3096\u30a1-\u30faー]+)\}")
SAYS = set()


def ruby(s: str) -> str:
    return RUBY_RE.sub(r"<ruby>\1<rt>\2</rt></ruby>", s)


def reading(jp: str) -> str:
    """Teks Jepang dengan kanji diganti bacaannya, untuk TTS."""
    t = RUBY_RE.sub(r"\2", jp)
    t = re.sub(r"\*\*|[〔〕（）()]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def cinline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"<u>\1</u>", s)
    s = re.sub(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return ruby(s).replace("\n", "<br>")


def load_exams():
    DIALOGS.clear()
    exams = []
    if not EXAMS_DIR.exists():
        return exams
    for f in sorted(EXAMS_DIR.glob("*.json")):
        ex = json.loads(f.read_text(encoding="utf-8"))
        for sec in ex.get("sections", []):
            for q in sec.get("questions", []):
                for k in ("q", "passage", "script", "exp"):
                    if q.get(k):
                        q[k] = cinline(q[k])
                if "opts" in q:
                    q["opts"] = [cinline(o) for o in q["opts"]]
                if q.get("turns"):
                    turns_kana = [[spk, reading(txt)] for spk, txt in q["turns"]]
                    say = " ".join(txt for _, txt in turns_kana)
                    did = audio_id("v2:" + json.dumps(turns_kana, ensure_ascii=False))
                    DIALOGS[say] = (did, turns_kana)
                    q["say"] = say
                    del q["turns"]
                elif q.get("say"):
                    t = reading(q["say"])
                    q["say"] = t
                    SAYS.add(t)
        exams.append(ex)
    exams.sort(key=lambda e: (e.get("order", 99), e.get("id", "")))
    return exams


SPEAK_BTN = ('<button class="say sm" type="button" data-say="{}" aria-label="Dengarkan">'
             '<svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/></svg></button>')


def say_btn(jp: str) -> str:
    t = reading(jp)
    SAYS.add(t)
    return SPEAK_BTN.format(html.escape(t))


def render_content(lines) -> str:
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para.clear()

    while i < len(lines):
        st = lines[i].strip()
        if not st:
            flush()
        elif st.startswith("###"):
            flush(); out.append(f"<h3>{cinline(st[3:].strip())}</h3>")
        elif st.startswith("##"):
            flush(); out.append(f"<h2>{cinline(st[2:].strip())}</h2>")
        elif st.startswith(">"):
            flush(); out.append(f'<div class="pola" lang="ja">{cinline(st[1:].strip())}</div>')
        elif st.startswith("!!"):
            flush(); out.append(f'<div class="tip">{cinline(st[2:].strip())}</div>')
        elif st.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i])); i += 1
            body = [r for r in rows[1:] if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
            out.append('<div class="tw"><table><thead><tr>' + "".join(f"<th>{cinline(h)}</th>" for h in rows[0]) +
                       "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{cinline(c)}</td>" for c in r) + "</tr>" for r in body) +
                       "</tbody></table></div>")
            continue
        elif st.startswith("- ") and " | " in st:
            flush()
            exs = []
            while i < len(lines) and lines[i].strip().startswith("- ") and " | " in lines[i]:
                jp, idn = lines[i].strip()[2:].split(" | ", 1); i += 1
                exs.append(f'<li class="ex"><div class="exj"><span lang="ja">{cinline(jp)}</span>{say_btn(jp)}</div>'
                           f'<div class="exi">{cinline(idn)}</div></li>')
            out.append('<ul class="exs">' + "".join(exs) + "</ul>")
            continue
        elif re.match(r"^[^\s|:：]{1,16}[:：]\s.*\s\|\s", st):
            flush()
            rows = []
            while i < len(lines) and re.match(r"^[^\s|:：]{1,16}[:：]\s.*\s\|\s", lines[i].strip()):
                who, rest = re.split(r"[:：]\s", lines[i].strip(), maxsplit=1); jp, idn = rest.split(" | ", 1); i += 1
                rows.append(f'<div class="dl"><b>{cinline(who)}</b><div><div class="exj"><span lang="ja">{cinline(jp)}</span>'
                            f'{say_btn(jp)}</div><div class="exi">{cinline(idn)}</div></div></div>')
            out.append('<div class="dlg">' + "".join(rows) + "</div>")
            continue
        elif re.match(r"^(\d+\.|-)\s", st):
            flush()
            m = re.match(r"^(\d+\.|-)\s+(.*)$", st)
            out.append(f'<div class="li l0"><span class="mk">{m.group(1) if m.group(1) != "-" else "•"}</span><span>{cinline(m.group(2))}</span></div>')
        else:
            para.append(cinline(st))
        i += 1
    flush()
    return "\n".join(out)


def read_content(path: Path):
    """-> (meta dict, {bagian: [baris]}) ; bagian dipisah dengan '# Nama'."""
    text = path.read_text(encoding="utf-8")
    meta = {}
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if m:
        for ln in m.group(1).split("\n"):
            if ":" in ln:
                k, v = ln.split(":", 1); meta[k.strip()] = v.strip()
        text = text[m.end():]
    secs, cur = {}, "isi"
    for ln in text.split("\n"):
        if ln.startswith("# "):
            cur = ln[2:].strip().lower(); secs[cur] = []
        else:
            secs.setdefault(cur, []).append(ln)
    return meta, secs


# ---------- konjugasi otomatis dari daftar kosa kata ----------
I_TO = {"い": ("う", "わ"), "き": ("く", "か"), "ぎ": ("ぐ", "が"), "し": ("す", "さ"), "ち": ("つ", "た"),
        "に": ("ぬ", "な"), "び": ("ぶ", "ば"), "み": ("む", "ま"), "り": ("る", "ら")}
TE = {"い": "って", "ち": "って", "り": "って", "み": "んで", "び": "んで", "に": "んで", "き": "いて", "ぎ": "いで", "し": "して"}


def conjugate(masu: str, group: str):
    stem = masu[:-2]
    if group == "Ⅲ":
        if stem.endswith("し"):
            b = stem[:-1]; return [b + "する", b + "して", b + "しない", b + "した"]
        if stem.endswith("き"):
            b = stem[:-1]; return [b + "くる", b + "きて", b + "こない", b + "きた"]
    if group == "Ⅱ":
        return [stem + "る", stem + "て", stem + "ない", stem + "た"]
    b, last = stem[:-1], stem[-1]
    if last not in I_TO:
        return None
    if stem in ("いき",) or stem.endswith(" いき"):
        te = b + "って"
    else:
        te = b + TE[last]
    nai = "ない" if stem == "あり" else b + I_TO[last][1] + "ない"
    return [b + I_TO[last][0], te, nai, te[:-1] + ("た" if te.endswith("て") else "だ")]


# Kata kerja Pelajaran 4–13 di daftar kosa kata belum diberi penanda kelompok.
GROUP_FIX = {
    "おきます": "Ⅱ", "ねます": "Ⅱ", "はたらきます": "Ⅰ", "やすみます": "Ⅰ", "べんきょうします": "Ⅲ", "おわります": "Ⅰ",
    "いきます": "Ⅰ", "きます": "Ⅲ", "かえります": "Ⅰ", "たべます": "Ⅱ", "のみます": "Ⅰ", "みます": "Ⅱ", "ききます": "Ⅰ",
    "よみます": "Ⅰ", "かきます": "Ⅰ", "かいます": "Ⅰ", "します": "Ⅲ", "きります": "Ⅰ", "おくります": "Ⅰ", "あげます": "Ⅱ",
    "もらいます": "Ⅰ", "かします": "Ⅰ", "かります": "Ⅱ", "おしえます": "Ⅱ", "ならいます": "Ⅰ", "わかります": "Ⅰ",
    "あります": "Ⅰ", "います": "Ⅱ", "かかります": "Ⅰ", "あそびます": "Ⅰ", "およぎます": "Ⅰ", "むかえます": "Ⅱ",
    "つかれます": "Ⅱ", "けっこんします": "Ⅲ", "かいものします": "Ⅲ", "しょくじします": "Ⅲ", "かわきます": "Ⅰ", "すきます": "Ⅰ",
}


def conj_data(vocab):
    rows, seen = [], set()
    for v in vocab:
        k = v[0].replace("*", "").strip()
        m = re.match(r"^(.*ます)\s*([ⅠⅡⅢ])", k)
        if m:
            masu, g = re.sub(r"\[.*?\]|\s", "", m.group(1)), m.group(2)
        else:
            last = k.split(" ")[-1]
            if last not in GROUP_FIX or not k.endswith("ます"):
                continue
            masu, g = last, GROUP_FIX[last]
        if masu in seen:
            continue
        f = conjugate(masu, g)
        if not f:
            continue
        seen.add(masu)
        rows.append((masu, *f, v[2], g, v[3]))
    return rows


def conj_table(vocab) -> str:
    by_g = {"Ⅰ": [], "Ⅱ": [], "Ⅲ": []}
    for r in conj_data(vocab):
        by_g[r[6]].append(r)
    out = ['<p><a class="practice" href="#/q/drill/konjugasi"><span>Latihan Konjugasi</span><span>›</span></a></p>']
    for g, name in (("Ⅰ", "Kelompok I"), ("Ⅱ", "Kelompok II"), ("Ⅲ", "Kelompok III")):
        out.append(f"<h2>{name} <small class=\"muted\">({len(by_g[g])} kata)</small></h2>")
        out.append('<div class="tw"><table><thead><tr><th>ます</th><th>Kamus</th><th>て</th><th>ない</th><th>た</th><th>Arti</th><th>Pel.</th></tr></thead><tbody>' +
                   "".join("<tr>" + "".join(f'<td lang="ja">{html.escape(c)}</td>' for c in r[:5]) +
                           f"<td>{html.escape(r[5])}</td><td>{r[7]}</td></tr>" for r in by_g[g]) + "</tbody></table></div>")
    return "\n".join(out)


def load_drills(vocab):
    verbs = [[r[0], r[1], r[2], r[3], r[4], r[5], r[6]] for r in conj_data(vocab)]
    p_path = DRILLS_DIR / "partikel-n5.json"
    particles = json.loads(p_path.read_text(encoding="utf-8")) if p_path.exists() else []
    for p in particles:
        p["q"] = cinline(p["q"])
        p["exp"] = cinline(p["exp"])
    k_path = DRILLS_DIR / "kanji-n5.json"
    kanji = json.loads(k_path.read_text(encoding="utf-8")) if k_path.exists() else []
    return {"verbs": verbs, "particles": particles, "kanji": kanji}


def kanji_page(kanji_list) -> str:
    out = ['<p><a class="practice" href="#/q/drill/kanji"><span>Latihan Kanji N5</span><span>›</span></a></p>']
    cats = []
    by_cat = {}
    for item in kanji_list:
        cat = item.get("cat", "Lainnya")
        if cat not in by_cat:
            cats.append(cat)
            by_cat[cat] = []
        by_cat[cat].append(item)
    for cat in cats:
        items = by_cat[cat]
        out.append(f'<h2>{html.escape(cat)} <small class="muted">({len(items)} kanji)</small></h2>')
        out.append('<div class="kgrid">')
        for item in items:
            exs = "".join(
                f'<div class="kc-ex"><span lang="ja"><ruby>{html.escape(w)}<rt>{html.escape(rd)}</rt></ruby></span>'
                f'<small>{html.escape(mn)}</small>{SPEAK_BTN.format(html.escape(rd))}</div>'
                for w, rd, mn in item.get("ex", [])
            )
            out.append(
                f'<div class="kcard"><div class="kc-top"><span class="kc-k" lang="ja">{html.escape(item["k"])}</span>'
                f'<div><b>{html.escape(item["arti"])}</b>'
                f'<div class="kc-rd"><span>On: {html.escape(item["on"])}</span><span>Kun: {html.escape(item["kun"])}</span></div>'
                f'</div></div><div class="kc-exs">{exs}</div></div>'
            )
        out.append('</div>')
    return "\n".join(out)


# ---------- parse ----------

def split_on(lines, prefix):
    """-> (preamble, [(heading_text, body_lines)])"""
    pre, parts, cur = [], [], None
    for ln in lines:
        if ln.startswith(prefix):
            cur = (ln[len(prefix):].strip(), [])
            parts.append(cur)
        elif cur is None:
            pre.append(ln)
        else:
            cur[1].append(ln)
    return pre, parts


MANIFEST = {
    "id": "/",
    "name": "Nihongoku — Belajar Bahasa Jepang",
    "short_name": "Nihongoku",
    "description": "Belajar bahasa Jepang dasar dengan latihan singkat ala Duolingo: kana, 25 pelajaran, dan simulasi ujian.",
    "lang": "id",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#f6f2ea",
    "theme_color": "#f6f2ea",
    "categories": ["education"],
    "icons": [
        {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}


def write_pwa(page: str):
    """Tulis manifest dan service worker. Versi SW = hash isi situs, supaya tiap perubahan memicu pembaruan."""
    site = OUT.parent
    (site / "manifest.webmanifest").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sw = (ROOT / "sw.template.js").read_text(encoding="utf-8")
    version = hashlib.sha1((page + sw).encode("utf-8")).hexdigest()[:10]
    (site / "sw.js").write_text(sw.replace("{{VERSION}}", version), encoding="utf-8")


def build():
    text = SRC.read_text(encoding="utf-8")
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    _, chapters = split_on(text.split("\n"), "# ")

    # pra-pindai tabel kosa kata -> kamus bacaan untuk furigana otomatis di teks lain
    global ANNOTATE
    pairs, in_vocab = [], False
    for ln in text.split("\n"):
        if ln.startswith("| Kana / Bacaan"):
            in_vocab = True
        elif not ln.startswith("|"):
            in_vocab = False
        elif in_vocab:
            c = cells(ln)
            if len(c) == 3 and c[1] and not c[0].startswith("**"):
                furi(c[0], c[1], pairs)
    for run, nxt, r in pairs:
        FURI.setdefault((run, nxt), set()).add(r)
        FURI.setdefault((run, None), set()).add(r)
    ANNOTATE = True

    vocab = []
    lessons, pages = [], []
    PLACEHOLDER = '<p class="empty">Materi bagian ini sedang ditulis.</p>'

    # Dari berkas buku hanya diambil tabel kosa kata; materi lain ditulis sendiri di content/.
    for title, body in chapters:
        m = re.match(r"Pelajaran (\d+)", title)
        if not m:
            continue
        n = int(m.group(1))
        _, parts = split_on(body, "## ")
        R = Renderer(lesson=n, vocab=vocab)
        kosa = ""
        for head, plines in parts:
            if re.search(r"· I\. ", head):
                kosa = R.render([ln for ln in plines if not ln.startswith("_Sumber")])
        f = CONTENT / f"pelajaran-{n:02d}.md"
        meta, secs = read_content(f) if f.exists() else ({}, {})
        tata, cakap = secs.get("tata bahasa", []), secs.get("percakapan", [])
        topics = [cinline(re.sub(r"^\d+\.\s*", "", ln[3:].strip())) for ln in tata if ln.startswith("## ")]
        lessons.append(dict(n=n, title=meta.get("judul", f"Pelajaran {n}"), sub=meta.get("ringkas", ""), topics=topics,
                            parts={"kosa": kosa,
                                   "tata": render_content(tata) if tata else PLACEHOLDER,
                                   "cakap": render_content(cakap) if cakap else PLACEHOLDER}))

    # halaman tambahan: content/hal-*.md (urut berdasarkan nama berkas)
    drills = load_drills(vocab)
    others = []
    for f in sorted(CONTENT.glob("hal-*.md")):
        meta, secs = read_content(f)
        body = "\n".join(render_content(v) for v in secs.values())
        if meta.get("sisip") == "konjugasi":
            body += conj_table(vocab)
        elif meta.get("sisip") == "kanji":
            body += kanji_page(drills["kanji"])
        others.append(dict(i=len(others), slug=f.stem[4:], title=meta.get("judul", f.stem), grup=meta.get("grup", "pengantar"),
                           html=body))

    # ---- buku ----
    def other_links(grup):
        return "".join(f'<a class="row" href="#/b/{o["i"]}"><span>{html.escape(o["title"])}</span><i>›</i></a>'
                       for o in others if o["grup"] == grup)

    cards = "".join(
        f'<a class="card" href="#/p/{l["n"]}" data-n="{l["n"]}"><span class="num">{l["n"]}</span>'
        f'<span class="ka" lang="ja">第{l["n"]}課</span><b>{html.escape(l["title"])}</b>'
        f'<small>{html.escape(l["sub"])}</small></a>'
        for l in lessons)
    home = f'''<section class="page" id="pg-buku" data-title="Buku" hidden>
<header class="hero"><p class="eyebrow" lang="ja">にほんごく</p>
<h1>Buku Pelajaran</h1><p class="sub">Penjelasan tata bahasa dan percakapan untuk 25 pelajaran tingkat dasar, ditulis ulang dengan bahasa sederhana. {len(vocab)} kosa kata.</p></header>
<a id="resume" class="resume" hidden></a>
<h2 class="sec">Mulai di sini</h2><nav class="rows">{other_links("pengantar")}</nav>
<h2 class="sec">Pelajaran</h2><nav class="grid">{cards}</nav>
<h2 class="sec">Lampiran</h2><nav class="rows">{other_links("lampiran")}</nav>
</section>'''
    pages.append(home)

    # ---- lessons ----
    for l in lessons:
        n = l["n"]
        tabs = "".join(f'<a href="#/p/{n}/{k}" data-tab="{k}">{lab}</a>' for k, lab in PART_LABELS)
        topics = "".join(f"<li>{t}</li>" for t in l["topics"])
        parts = ""
        for k, _ in PART_LABELS:
            tool = '<button class="hide-btn" type="button" data-hide>Sembunyikan arti</button>' if k == "kosa" else ""
            parts += f'<div class="part" data-part="{k}" hidden>{tool}{l["parts"][k]}</div>'
        prev = f'<a href="#/p/{n-1}">‹ Pelajaran {n-1}</a>' if n > 1 else "<span></span>"
        nxt = f'<a href="#/p/{n+1}">Pelajaran {n+1} ›</a>' if n < len(lessons) else "<span></span>"
        det = f'<details><summary>{len(l["topics"])} topik tata bahasa</summary><ol>{topics}</ol></details>' if topics else ""
        pages.append(f'''<section class="page lesson" id="pg-p{n}" data-title="Pelajaran {n}" hidden>
<header class="lhead"><span class="ka" lang="ja">第{n}課</span><h1>{html.escape(l["title"])}</h1>
{det}</header>
<nav class="tabs">{tabs}</nav>
<article class="prose">{parts}</article>
<nav class="pn">{prev}{nxt}</nav></section>''')

    # ---- halaman tambahan ----
    for o in others:
        pages.append(f'<section class="page" id="pg-b{o["i"]}" data-title="{html.escape(o["title"])}" hidden>'
                     f'<article class="prose"><h1>{html.escape(o["title"])}</h1>{o["html"]}</article></section>')

    intro = next((o["i"] for o in others if o["slug"].endswith("kana")), 0)
    exams = load_exams()
    # audio: daftar teks untuk gen_audio.py, peta teks -> id untuk file yang sudah ada
    kana = [x[0] for row in KANA_ROWS.split("|") for x in row.split(" ")]
    texts = sorted({v[6] for v in vocab if v[6]} | set(kana) | {to_kata(k) for k in kana} | SAYS)
    AUDIO_LIST.write_text(json.dumps(texts, ensure_ascii=False, indent=0), encoding="utf-8")
    dialogs_out = sorted({did: turns for did, turns in DIALOGS.values()}.items())
    DIALOG_LIST.write_text(json.dumps([{"id": did, "turns": turns} for did, turns in dialogs_out], ensure_ascii=False, indent=2), encoding="utf-8")
    audio = {t: audio_id(t) for t in texts if (AUDIO_DIR / f"{audio_id(t)}.mp3").exists()}
    for t, (did, _) in DIALOGS.items():
        if (AUDIO_DIR / f"{did}.mp3").exists():
            audio[t] = did
    meta = json.dumps({"lessons": [[l["n"], l["title"]] for l in lessons], "intro": intro, "kana": KANA_ROWS,
                       "audio": audio}, ensure_ascii=False, separators=(",", ":"))
    data = json.dumps(vocab, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    exams_json = json.dumps(exams, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    drills_json = json.dumps(drills, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = (TEMPLATE.read_text(encoding="utf-8")
            .replace("{{PAGES}}", "\n".join(pages))
            .replace("{{VOCAB}}", data)
            .replace("{{EXAMS}}", exams_json)
            .replace("{{DRILLS}}", drills_json)
            .replace("{{META}}", meta.replace("</", "<\\/")))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    write_pwa(page)
    print(f"{OUT.relative_to(ROOT)}: {len(page)/1024:.0f} KB, {len(lessons)} pelajaran, {len(vocab)} kosa kata, "
          f"{len(others)} bagian lain, {len(exams)} ujian, audio {len(audio)}/{len(texts) + len(dialogs_out)}")


if __name__ == "__main__":
    build()
