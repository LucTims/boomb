#!/usr/bin/env python3
"""Montage du documentaire BoomBooks « Les 10 hommes les plus riches d'Afrique en 2026 ».

Usage : python3 render.py <dossier_de_travail>

Le dossier de travail doit contenir :
  voice.mp3      voix off complète
  music.mp3      musique de fond
  words.json     transcription horodatée [{"text", "start", "end"}, ...]
  bg/<nom>.png   images de fond (voir PEOPLE / INTRO_BGS / OUTRO_BGS)
Produit <dossier>/boombooks_riches_afrique_2026.mp4 (1920x1080, 25 i/s).
"""
import json
import math
import os
import re
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 25
VOFF = 0.8          # la voix démarre après le titre
TAIL = 2.5          # secondes après la dernière phrase
XFADE = 0.35        # fondu entre deux séquences

GOLD = (236, 186, 72)
WHITE = (255, 255, 255)
DARK = (12, 12, 16)
FONT_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

INTRO_BGS = ["skyline_0", "luxury_3"]
OUTRO_BGS = ["skyline_1"]
# rang, nom, pays, fortune (Md$), secteur, badge, images de fond
PEOPLE = [
    (10, "Michiel Le Roux", "ZA", 3.8, "Banque · Capitec", None, ["skyline_2", "construction_3"]),
    (9, "Mohamed Mansour", "EG", 4.0, "Distribution · Caterpillar · General Motors", None, ["construction_0", "construction_2"]),
    (8, "Patrice Motsepe", "ZA", 4.3, "Mines · African Rainbow Minerals", "Président de la CAF", ["mine_0", "mine_2"]),
    (7, "Naguib Sawiris", "EG", 5.6, "Télécoms · Or", None, ["telecom_0", "mine_3"]),
    (6, "Mike Adenuga", "NG", 6.5, "Télécoms · Pétrole", "« The Guru »", ["telecom_1", "telecom_2"]),
    (5, "Nassef Sawiris", "EG", 9.6, "Construction · Engrais · Adidas", None, ["construction_1", "industry_3"]),
    (4, "Nicky Oppenheimer & famille", "ZA", 10.6, "Diamants · De Beers", None, ["mine_1", "luxury_1"]),
    (3, "Abdulsamad Rabiu", "NG", 11.2, "Ciment · Agroalimentaire (BUA)", "+120 % en un an", ["industry_0", "industry_2"]),
    (2, "Johann Rupert & famille", "ZA", 16.1, "Luxe · Richemont (Cartier)", None, ["luxury_0", "luxury_2"]),
    (1, "Aliko Dangote", "NG", 51.7, "Ciment · Sucre · Pétrole", "N°1 pour la 15e année", ["industry_1", "skyline_3"]),
]
# Dangote : 28,5 Md$ au classement de mars, réévalué à 51,7 Md$ par Forbes en septembre 2026.
# Le compteur s'arrête d'abord sur la valeur de mars, puis grimpe quand la voix dit « cinquante ».
DANGOTE_MARCH = 28.5
COUNTRY = {"NG": "Nigeria", "ZA": "Afrique du Sud", "EG": "Égypte"}
RANK_WORDS = ["dix", "neuf", "huit", "sept", "six", "cinq", "quatre", "trois", "deux", "un"]


def font(size, bold=True):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def fmt_md(v):
    return f"{v:.1f}".replace(".", ",") + " Md$"


# ---------------------------------------------------------------- drapeaux
def flag(code, w=96, h=64):
    s = 4
    im = Image.new("RGB", (w * s, h * s), WHITE)
    d = ImageDraw.Draw(im)
    W2, H2 = w * s, h * s
    if code == "NG":
        g = (0, 135, 81)
        d.rectangle([0, 0, W2 // 3, H2], fill=g)
        d.rectangle([2 * W2 // 3, 0, W2, H2], fill=g)
    elif code == "EG":
        d.rectangle([0, 0, W2, H2 // 3], fill=(206, 17, 38))
        d.rectangle([0, 2 * H2 // 3, W2, H2], fill=(0, 0, 0))
        r = H2 // 9
        d.ellipse([W2 // 2 - r, H2 // 2 - r, W2 // 2 + r, H2 // 2 + r], fill=(192, 147, 0))
    elif code == "ZA":
        d.rectangle([0, 0, W2, H2 // 2], fill=(222, 56, 49))
        d.rectangle([0, H2 // 2, W2, H2], fill=(0, 35, 149))
        jx = int(W2 * 0.42)
        for col, wd in ((WHITE, H2 // 3), ((0, 122, 77), H2 // 5)):
            d.line([(-wd, -wd // 2), (jx, H2 // 2), (W2 + wd, H2 // 2)], fill=col, width=wd, joint="curve")
            d.line([(-wd, H2 + wd // 2), (jx, H2 // 2)], fill=col, width=wd, joint="curve")
        d.polygon([(0, int(H2 * 0.2)), (int(W2 * 0.33), H2 // 2), (0, int(H2 * 0.8))], fill=(255, 182, 18))
        d.polygon([(0, int(H2 * 0.28)), (int(W2 * 0.25), H2 // 2), (0, int(H2 * 0.72))], fill=(0, 0, 0))
    im = im.resize((w, h), Image.LANCZOS).convert("RGBA")
    border = Image.new("RGBA", (w + 4, h + 4), (255, 255, 255, 230))
    border.paste(im, (2, 2))
    return border


# ---------------------------------------------------------------- éléments graphiques
def text_img(txt, size, color=WHITE, bold=True, shadow=True, max_w=None, spacing=0):
    f = font(size, bold)
    while max_w and f.getlength(txt) + spacing * len(txt) > max_w and size > 30:
        size -= 4
        f = font(size, bold)
    tw = int(f.getlength(txt) + spacing * len(txt)) + 20
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (tw + 16, asc + desc + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def draw(dd, xy, fill):
        if spacing:
            x, y = xy
            for ch in txt:
                dd.text((x, y), ch, font=f, fill=fill)
                x += f.getlength(ch) + spacing
        else:
            dd.text(xy, txt, font=f, fill=fill)

    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        draw(ImageDraw.Draw(sh), (8, 10), (0, 0, 0, 170))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(6)))
        d = ImageDraw.Draw(im)
    draw(d, (8, 6), color + (255,) if len(color) == 3 else color)
    return im


def chip(txt, size, fg=WHITE, bg=(255, 255, 255, 38), border=GOLD, pad=(26, 12)):
    f = font(size, True)
    tw = int(f.getlength(txt))
    asc, desc = f.getmetrics()
    w, h = tw + pad[0] * 2, asc + desc + pad[1] * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=bg, outline=border, width=3)
    d.text((pad[0], pad[1]), txt, font=f, fill=fg)
    return im


def fade_alpha(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


def put(frame, im, x, y, a=1.0):
    if a <= 0.001:
        return
    frame.alpha_composite(fade_alpha(im, a), (int(x), int(y)))


def gradient_overlay():
    """Assombrit la gauche (zone texte) et le bas (sous-titres)."""
    g = Image.new("L", (W, 1))
    g.putdata([int(215 * max(0.0, 1 - x / 1250) ** 1.3) for x in range(W)])
    left = g.resize((W, H))
    b = Image.new("L", (1, H))
    b.putdata([int(200 * max(0.0, (y - 760) / 320) ** 1.5) if y > 760 else 0 for y in range(H)])
    bottom = b.resize((W, H))
    t = Image.new("L", (1, H))
    t.putdata([int(120 * max(0.0, 1 - y / 160)) for y in range(H)])
    top = t.resize((W, H))
    a = Image.fromarray(np.maximum.reduce([np.array(left), np.array(bottom), np.array(top)]))
    ov = Image.new("RGBA", (W, H), DARK + (0,))
    ov.putalpha(a)
    return ov


def vignette():
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    a = np.clip((r - 0.75) / 0.7, 0, 1) * 150
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov.putalpha(Image.fromarray(a.astype("uint8")))
    return ov


# ---------------------------------------------------------------- timeline
def load_words(path):
    data = json.load(open(path))
    if isinstance(data, dict):
        data = data.get("words", data)
    out, opener = [], ""
    for w in data:
        txt = (w.get("text") or w.get("word") or "").strip()
        if not txt or w.get("type") in ("spacing", "audio_event"):
            continue
        if txt in ("«", "(", "“"):
            opener = txt + " " if txt == "«" else txt
            continue
        if out and re.fullmatch(r"[^\w]+", txt):
            # ponctuation isolée (« : », « ? », « », ») : accrochée au mot précédent
            out[-1]["text"] += (" " if txt[0] in ":?!;»" else "") + txt
            out[-1]["end"] = float(w["end"]) + VOFF
            continue
        out.append({"text": opener + txt, "start": float(w["start"]) + VOFF, "end": float(w["end"]) + VOFF})
        opener = ""
    return out


def norm(s):
    return re.sub(r"[^\wéèêàùçô]", "", s.lower())


def find_segments(words, total):
    starts = []
    i = 0
    for rw in RANK_WORDS:
        while i < len(words) - 1:
            if norm(words[i]["text"]) == "numéro" and norm(words[i + 1]["text"]) in (rw, {"un": "1"}.get(rw, ""), str(10 - len(starts))):
                j = i - 1 if rw == "un" and i > 0 and norm(words[i - 1]["text"]) == "et" else i
                starts.append(words[j]["start"] - 0.2)
                i += 2
                break
            i += 1
        else:
            raise SystemExit(f"Rang introuvable dans la transcription : numéro {rw}")
    outro = None
    for k in range(i, len(words) - 1):
        if norm(words[k]["text"]) == "le" and norm(words[k + 1]["text"]).startswith("nigeria"):
            outro = words[k]["start"] - 0.2
            break
    if outro is None:
        raise SystemExit("Début de la conclusion introuvable")
    bounds = [0.0] + starts + [outro, total]
    segs = [("intro", None, bounds[0], bounds[1])]
    for p, a, b in zip(PEOPLE, bounds[1:11], bounds[2:12]):
        segs.append(("person", p, a, b))
    segs.append(("outro", None, bounds[11], bounds[12]))
    return segs


def subtitle_chunks(words):
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x["text"] for x in cur)
        end = re.search(r"[.?!:;]$", w["text"]) or (w["text"].endswith(",") and len(cur) >= 4)
        if end or len(cur) >= 8 or len(text) > 42:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out = []
    for k, c in enumerate(chunks):
        a, b = c[0]["start"], c[-1]["end"]
        if k + 1 < len(chunks) and chunks[k + 1][0]["start"] - b < 0.5:
            b = chunks[k + 1][0]["start"]
        out.append((a, b, " ".join(x["text"] for x in c)))
    return out


# ---------------------------------------------------------------- rendu
class Renderer:
    def __init__(self, work, segs, subs, marks):
        self.work, self.segs, self.subs, self.marks = work, segs, subs, marks
        self.cache = {}
        self.overlay = gradient_overlay()
        self.vig = vignette()
        self.logo = self._logo()
        self.source = text_img("Source : Forbes Afrique 2026", 24, (255, 255, 255, 200), bold=False)
        self.source_rt = text_img("Source : Forbes Afrique 2026 · Forbes temps réel (sept. 2026)", 24,
                                  (255, 255, 255, 200), bold=False)
        self.sub_cache = {}
        self.person_assets = {}

    def _logo(self):
        f = font(34)
        txt = "BOOMBOOKS"
        im = Image.new("RGBA", (int(f.getlength(txt)) + 70, 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([4, 14, 34, 44], fill=GOLD)
        d.text((46, 10), txt, font=f, fill=(255, 255, 255, 235))
        return im

    def bg(self, name):
        if name not in self.cache:
            im = Image.open(os.path.join(self.work, "bg", name + ".png")).convert("RGB")
            s = max(W * 1.12 / im.width, H * 1.12 / im.height)
            im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.LANCZOS)
            self.cache[name] = im
        return self.cache[name]

    def kenburns(self, name, u, seed):
        """u : progression 0..1 dans le plan."""
        im = self.bg(name)
        z0, z1 = (1.0, 1.10) if seed % 2 == 0 else (1.10, 1.0)
        z = z0 + (z1 - z0) * u
        cw, ch = im.width / 1.12 / z, im.height / 1.12 / z
        dirs = [(-1, -0.4), (1, 0.3), (0.6, -1), (-0.7, 1)]
        dx, dy = dirs[seed % 4]
        cx = im.width / 2 + dx * (im.width - cw) / 2 * (u - 0.5)
        cy = im.height / 2 + dy * (im.height - ch) / 2 * (u - 0.5)
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        fr = im.resize((W, H), Image.BILINEAR, box=box)
        return fr

    def background(self, names, t, a, b, seed):
        dur = b - a
        if len(names) == 1:
            fr = self.kenburns(names[0], (t - a) / dur, seed)
        else:
            mid = a + dur / 2
            if t < mid - 0.3:
                fr = self.kenburns(names[0], (t - a) / (dur / 2 + 0.3), seed)
            elif t > mid + 0.3:
                fr = self.kenburns(names[1], (t - mid + 0.3) / (dur / 2 + 0.3), seed + 1)
            else:
                k = (t - (mid - 0.3)) / 0.6
                f1 = self.kenburns(names[0], (t - a) / (dur / 2 + 0.3), seed)
                f2 = self.kenburns(names[1], (t - mid + 0.3) / (dur / 2 + 0.3), seed + 1)
                fr = Image.blend(f1, f2, k)
        fr = Image.eval(fr, lambda v: int(v * 0.82))
        return fr.convert("RGBA")

    def assets(self, p):
        rank = p[0]
        if rank not in self.person_assets:
            r, name, cc, fortune, sector, badge, _ = p
            self.person_assets[rank] = {
                "num": text_img("N°", 70, GOLD),
                "rank": text_img(str(r), 230, GOLD),
                "name": text_img(name, 96, WHITE, max_w=1150),
                "flag": flag(cc),
                "country": text_img(COUNTRY[cc], 50, WHITE, bold=False),
                "sector": chip(sector, 36),
                "badge": chip(badge, 34, fg=DARK, bg=GOLD + (255,), border=GOLD) if badge else None,
                "march": text_img(f"Classement de mars 2026 : {fmt_md(DANGOTE_MARCH)}  ·  réévalué en septembre", 34,
                                  (255, 255, 255, 220), bold=False),
            }
        return self.person_assets[rank]

    def draw_person(self, fr, p, lt):
        A = self.assets(p)

        def slide(delay, dur=0.55):
            k = ease((lt - delay) / dur)
            return k, (1 - k) * -60

        k, dx = slide(0.0)
        put(fr, A["num"], 110 + dx, 205, k)
        put(fr, A["rank"], 200 + dx, 95, k)
        k, dx = slide(0.25)
        put(fr, A["name"], 104 + dx, 375, k)
        k, dx = slide(0.45)
        put(fr, A["flag"], 120 + dx, 505, k)
        put(fr, A["country"], 240 + dx, 500, k)
        c0 = self.marks.get(p[0], 0.6)
        k, dx = slide(c0 - 0.1, 0.4)
        if k > 0:
            if p[0] == 1 and "sept" in self.marks:
                v = DANGOTE_MARCH * ease((lt - c0) / 1.6)
                s = self.marks["sept"]
                if lt > s:
                    v = DANGOTE_MARCH + (p[3] - DANGOTE_MARCH) * ease((lt - s) / 2.0)
                    put(fr, A["march"], 120, 712, ease((lt - s) / 0.6))
            else:
                v = p[3] * ease((lt - c0) / 1.6)
            put(fr, text_img(fmt_md(v), 150, GOLD), 104 + dx, 560, k)
        k, dx = slide(1.0)
        put(fr, A["sector"], 120 + dx, 785, k)
        if A["badge"]:
            k, dx = slide(1.4)
            put(fr, A["badge"], 120 + dx, 855, k)

    def draw_intro(self, fr, lt):
        k = ease(lt / 0.8)
        top = text_img("CLASSEMENT FORBES AFRIQUE 2026", 38, GOLD, spacing=6)
        put(fr, top, (W - top.width) / 2, 250 - (1 - k) * 30, k)
        for i, line in enumerate(["LES 10 HOMMES", "LES PLUS RICHES D'AFRIQUE"]):
            k = ease((lt - 0.25 - 0.2 * i) / 0.8)
            im = self.sub_cache.setdefault(("intro", i), text_img(line, 118 if i == 0 else 96, WHITE))
            put(fr, im, (W - im.width) / 2, 320 + i * 140 + (1 - k) * 40, k)
        k = ease((lt - 1.2) / 0.8)
        big = self.sub_cache.setdefault(("intro", "y"), text_img("EN 2026", 84, GOLD))
        put(fr, big, (W - big.width) / 2, 600, k)
        k = ease((lt - 3.0) / 0.8)
        stat = self.sub_cache.setdefault(("intro", "stat"), chip("23 milliardaires  ·  126,7 Md$  ·  +21 % en un an", 40))
        put(fr, stat, (W - stat.width) / 2, 740, k)

    def draw_outro(self, fr, lt, dur):
        panel = Image.new("RGBA", (W, H), DARK + (165,))
        fr.alpha_composite(panel)
        title = self.sub_cache.setdefault(("outro", "t"), text_img("LE CLASSEMENT 2026", 60, GOLD, spacing=4))
        put(fr, title, (W - title.width) / 2, 70, ease(lt / 0.6))
        rows = sorted(PEOPLE, key=lambda p: p[0])
        x0, y0, rh, maxw = 640, 175, 64, 1000
        for i, p in enumerate(rows):
            k = ease((lt - 0.3 - i * 0.12) / 0.9)
            if k <= 0:
                continue
            y = y0 + i * rh
            lab = self.sub_cache.setdefault(("lab", i), text_img(f"{p[0]}. {p[1]}", 34, WHITE, max_w=470))
            put(fr, lab, x0 - 90 - lab.width, y, k)
            put(fr, self.sub_cache.setdefault(("fl", i), flag(p[2], 54, 36)), x0 - 76, y + 12, k)
            bw = int(maxw * p[3] / PEOPLE[-1][3] * k)
            d = ImageDraw.Draw(fr)
            col = GOLD if p[0] == 1 else (200, 160, 70)
            d.rounded_rectangle([x0, y + 10, x0 + max(bw, 8), y + rh - 12], radius=8, fill=col + (255,))
            val = text_img(fmt_md(p[3] * k), 32, WHITE)
            put(fr, val, x0 + bw + 8, y + 4, k)
        k = ease((lt - (dur - 6.5)) / 0.7)
        cta = self.sub_cache.setdefault(("outro", "cta"), chip("ABONNEZ-VOUS À BOOMBOOKS", 46, fg=DARK, bg=GOLD + (255,)))
        put(fr, cta, (W - cta.width) / 2, 850 - (1 - k) * 30, k)

    def subtitle(self, fr, t):
        for a, b, txt in self.subs:
            if a <= t < b:
                im = self.sub_cache.get(txt)
                if im is None:
                    f = font(46)
                    tw = int(f.getlength(txt))
                    asc, desc = f.getmetrics()
                    im = Image.new("RGBA", (tw + 48, asc + desc + 24), (0, 0, 0, 0))
                    d = ImageDraw.Draw(im)
                    d.rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=14, fill=(0, 0, 0, 165))
                    d.text((24, 11), txt, font=f, fill=WHITE)
                    self.sub_cache[txt] = im
                put(fr, im, (W - im.width) / 2, H - 150 if self.seg_kind(t) != "outro" else H - 140)
                return

    def seg_kind(self, t):
        for kind, _, a, b in self.segs:
            if a <= t < b:
                return kind
        return self.segs[-1][0]

    def seg_frame(self, idx, t):
        kind, p, a, b = self.segs[idx]
        lt = t - a
        if kind == "intro":
            fr = self.background(INTRO_BGS, t, a, b, 0)
            fr.alpha_composite(Image.new("RGBA", (W, H), DARK + (90,)))
            fr.alpha_composite(self.vig)
            self.draw_intro(fr, lt)
        elif kind == "outro":
            fr = self.background(OUTRO_BGS, t, a, b, 3)
            fr.alpha_composite(self.vig)
            self.draw_outro(fr, lt, b - a)
        else:
            fr = self.background(p[6], t, a, b, idx)
            fr.alpha_composite(self.overlay)
            fr.alpha_composite(self.vig)
            self.draw_person(fr, p, lt)
        return fr

    def frame(self, t):
        idx = next(i for i, s in enumerate(self.segs) if s[2] <= t < s[3] or i == len(self.segs) - 1)
        fr = self.seg_frame(idx, t)
        a = self.segs[idx][2]
        if idx > 0 and t - a < XFADE:
            prev = self.seg_frame(idx - 1, t)
            fr = Image.blend(prev, fr, ease((t - a) / XFADE))
        fr.alpha_composite(self.logo, (W - self.logo.width - 50, 40))
        src = self.source_rt if (self.segs[idx][1] or (0,))[0] == 1 or self.segs[idx][0] == "outro" else self.source
        fr.alpha_composite(src, (W - src.width - 40, H - 52))
        self.subtitle(fr, t)
        total = self.segs[-1][3]
        if t < 0.4:
            fr = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), fr, t / 0.4)
        elif t > total - 0.8:
            fr = Image.blend(fr, Image.new("RGBA", (W, H), (0, 0, 0, 255)), min(1, (t - (total - 0.8)) / 0.8))
        return fr.convert("RGB")


def fortune_marks(words, segs):
    """Instant (relatif au début du plan) où la voix annonce chaque fortune."""
    marks = {}
    for kind, p, a, b in segs:
        if kind != "person":
            continue
        ws = [w for w in words if a <= w["start"] < b]
        k = next((i for i, w in enumerate(ws) if w["text"].endswith(".")), None)
        if k is not None and k + 1 < len(ws):
            marks[p[0]] = ws[k + 1]["start"] - a
        if p[0] == 1:
            for w in ws:
                if norm(w["text"]).startswith("vingthuit"):
                    marks[1] = w["start"] - a
                if norm(w["text"]) == "cinquante":
                    marks["sept"] = w["start"] - a
    return marks


def render_part(args):
    work, segs, subs, marks, k, f0, f1 = args
    r = Renderer(work, segs, subs, marks)
    out = os.path.join(work, "parts", f"part_{k:02d}.mp4")
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for f in range(f0, f1):
        p.stdin.write(r.frame(f / FPS).tobytes())
    p.stdin.close()
    p.wait()
    return out


def main():
    work = sys.argv[1]
    os.makedirs(os.path.join(work, "parts"), exist_ok=True)
    vdur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         os.path.join(work, "voice.mp3")]).decode())
    words = load_words(os.path.join(work, "words.json"))
    total = max(vdur + VOFF, words[-1]["end"]) + TAIL
    segs = find_segments(words, total)
    subs = subtitle_chunks(words)
    marks = fortune_marks(words, segs)
    json.dump({"segments": [(s[0], s[1][1] if s[1] else None, s[2], s[3]) for s in segs],
               "marks": {str(k): v for k, v in marks.items()}},
              open(os.path.join(work, "timeline.json"), "w"), ensure_ascii=False, indent=1)

    nframes = int(total * FPS)
    only = os.environ.get("ONLY")  # ex. ONLY=12.0 → image fixe de test
    if only:
        for t in only.split(","):
            Renderer(work, segs, subs, marks).frame(float(t)).save(os.path.join(work, f"test_{t}.png"))
        return
    n = os.cpu_count() or 4
    step = math.ceil(nframes / n)
    jobs = [(work, segs, subs, marks, k, k * step, min(nframes, (k + 1) * step)) for k in range(n)]
    with Pool(n) as pool:
        parts = pool.map(render_part, jobs)
    lst = os.path.join(work, "parts", "list.txt")
    open(lst, "w").write("".join(f"file '{os.path.basename(p)}'\n" for p in parts))
    video = os.path.join(work, "video_only.mp4")
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                           "-c", "copy", video])

    # Mixage : musique baissée automatiquement sous la voix, normalisation -14 LUFS
    out = os.path.join(work, "boombooks_riches_afrique_2026.mp4")
    ms = int(VOFF * 1000)
    fc = (f"[1:a]aresample=48000,adelay={ms}|{ms},apad,volume=1.0,asplit=2[v][vk];"
          f"[2:a]aresample=48000,volume=0.55,atrim=0:{total:.2f},afade=t=out:st={total - 3.5:.2f}:d=3.5[m];"
          f"[m][vk]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=450[md];"
          f"[v][md]amix=inputs=2:duration=first:normalize=0,atrim=0:{total:.2f},"
          f"loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", video,
                           "-i", os.path.join(work, "voice.mp3"),
                           "-stream_loop", "-1", "-i", os.path.join(work, "music.mp3"),
                           "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out])
    print(out)


if __name__ == "__main__":
    main()
