# -*- coding: utf-8 -*-
"""Motor de animación y montaje de "Crónicas de Leonida".

Dibuja cada fotograma con PIL (fondos ilustrados originales, tarjetas, textos
animados, subtítulos) y los envía a ffmpeg. Después mezcla voz + música +
efectos y genera el MP4 final, los subtítulos .srt y la miniatura.

Uso: python engine/render.py 01 02 ...   (sin argumentos: todos)
"""
import json, math, os, random, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from content import VIDEOS, CHANNEL
import audio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(ROOT, "videos")
FONTS = os.path.join(ROOT, "assets", "fonts")
W, H, FPS = 1920, 1080, 30
PREVIEW = os.environ.get("PREVIEW")  # renderiza solo un fotograma por escena

GAP = 0.32      # silencio entre beats
LEAD = 0.55     # entrada de escena (transición)
TAIL = 0.65     # cola de escena
INTRO = 2.2     # sting del canal

THEMES = {
    "sunset": dict(sky=[(0, (32, 8, 52)), (0.45, (150, 22, 92)), (0.62, (255, 128, 60))],
                   sun=((255, 230, 90), (255, 60, 130)), water=((60, 14, 70), (18, 6, 30)),
                   city=(28, 6, 40), palm=(14, 3, 20), acc=(255, 46, 136), acc2=(255, 210, 63), grid=False, stars=False),
    "night": dict(sky=[(0, (5, 6, 22)), (0.4, (24, 14, 66)), (0.62, (96, 26, 110))],
                  sun=((255, 120, 200), (120, 40, 200)), water=((20, 10, 50), (4, 4, 14)),
                  city=(12, 8, 30), palm=(4, 3, 12), acc=(41, 227, 255), acc2=(255, 46, 136), grid=False, stars=True),
    "synth": dict(sky=[(0, (13, 2, 33)), (0.42, (38, 20, 71)), (0.62, (255, 56, 100))],
                  sun=((255, 220, 80), (255, 40, 120)), water=((30, 8, 50), (8, 2, 20)),
                  city=(20, 6, 40), palm=(8, 2, 18), acc=(255, 56, 100), acc2=(45, 226, 230), grid=True, stars=True),
    "keys": dict(sky=[(0, (8, 50, 84)), (0.42, (30, 136, 168)), (0.62, (255, 178, 107))],
                 sun=((255, 245, 180), (255, 150, 90)), water=((20, 120, 140), (6, 40, 60)),
                 city=(10, 40, 60), palm=(4, 22, 32), acc=(255, 178, 107), acc2=(41, 227, 255), grid=False, stars=False),
}
WHITE = (255, 255, 255)
INK = (14, 6, 24)
HORIZON = int(H * 0.62)

# ------------------------------------------------------------------ utilidades
_fonts = {}


def font(name, size):
    key = (name, size)
    if key not in _fonts:
        f = {"anton": "Anton.woff", "bebas": "BebasNeue.woff", "mont": "montserrat-latin-800-normal.woff",
             "montr": "montserrat-latin-500-normal.woff"}[name]
        _fonts[key] = ImageFont.truetype(os.path.join(FONTS, f), size)
    return _fonts[key]


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_back(x):
    x = min(max(x, 0.0), 1.0)
    c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def with_alpha(img, a):
    if a >= 0.999:
        return img
    img = img.copy()
    img.putalpha(img.getchannel("A").point(lambda v: int(v * max(a, 0))))
    return img


def text_sprite(text, fnt, fill=WHITE, glow=None, glow_r=18, stroke=0, stroke_fill=INK, spacing=0, align="center"):
    """Texto (multilínea) como sprite RGBA con resplandor opcional."""
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = d.multiline_textbbox((0, 0), text, font=fnt, spacing=spacing, align=align, stroke_width=stroke)
    pad = glow_r * 2 + 10 if glow else 10
    w, h = int(bbox[2] - bbox[0] + pad * 2), int(bbox[3] - bbox[1] + pad * 2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pos = (int(pad - bbox[0]), int(pad - bbox[1]))
    if glow:
        g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(g).multiline_text(pos, text, font=fnt, fill=glow + (255,), spacing=spacing, align=align,
                                         stroke_width=stroke + 4, stroke_fill=glow + (255,))
        g = g.filter(ImageFilter.GaussianBlur(glow_r))
        img = Image.alpha_composite(img, g)
    ImageDraw.Draw(img).multiline_text(pos, text, font=fnt, fill=fill + (255,) if len(fill) == 3 else fill,
                                       spacing=spacing, align=align, stroke_width=stroke, stroke_fill=stroke_fill)
    return img


def rounded(w, h, r, fill, outline=None, width=0, shadow=False):
    pad = 30 if shadow else 0
    img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    if shadow:
        s = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(s).rounded_rectangle((pad, pad + 10, pad + w, pad + h + 10), r, fill=(0, 0, 0, 150))
        img = Image.alpha_composite(img, s.filter(ImageFilter.GaussianBlur(14)))
    ImageDraw.Draw(img).rounded_rectangle((pad, pad, pad + w - 1, pad + h - 1), r, fill=fill, outline=outline, width=width)
    return img


def paste(frame, spr, x, y, a=1.0, anchor="mm"):
    if a <= 0.01:
        return
    spr = with_alpha(spr, a)
    w, h = spr.size
    if anchor == "mm":
        x, y = x - w // 2, y - h // 2
    elif anchor == "lm":
        y = y - h // 2
    frame.alpha_composite(spr, (int(x), int(y))) if 0 <= x and 0 <= y and x + w <= W and y + h <= H else \
        _safe_paste(frame, spr, int(x), int(y))


def _safe_paste(frame, spr, x, y):
    tmp = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    tmp.paste(spr, (x, y))
    frame.alpha_composite(tmp)


# ------------------------------------------------------------------ fondos
def gradient(h, stops):
    ys = np.linspace(0, 1, h)
    out = np.zeros((h, 3))
    pts = [s[0] for s in stops]
    for c in range(3):
        out[:, c] = np.interp(ys, pts, [s[1][c] for s in stops])
    return out


class Background:
    def __init__(self, theme, seed=1, size=(W, H)):
        self.t = THEMES[theme]
        self.W, self.H = size
        rnd = random.Random(seed)
        Wd = self.W + 700
        hz = int(self.H * 0.62)
        self.hz = hz
        # cielo (incluye sol) en ancho extendido
        sky = gradient(self.H, [(s[0], s[1]) for s in self.t["sky"]] + [(1.0, self.t["sky"][-1][1])])
        arr = np.repeat(sky[:, None, :], Wd, axis=1).astype(np.uint8)
        img = Image.fromarray(arr, "RGB").convert("RGBA")
        d = ImageDraw.Draw(img)
        if self.t["stars"]:
            for _ in range(260):
                x, y = rnd.randrange(Wd), rnd.randrange(int(hz * 0.8))
                r = rnd.choice([1, 1, 1, 2])
                d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randrange(80, 230)))
        # sol con franjas retro
        R = int(self.H * 0.25); cx, cy = Wd // 2 + 120, hz - int(R * 0.35)
        sun = Image.new("RGBA", (R * 2, R * 2), (0, 0, 0, 0))
        sg = gradient(R * 2, [(0, self.t["sun"][0]), (1, self.t["sun"][1])]).astype(np.uint8)
        sun_rgb = Image.fromarray(np.repeat(sg[:, None, :], R * 2, axis=1), "RGB").convert("RGBA")
        mask = Image.new("L", (R * 2, R * 2), 0)
        md = ImageDraw.Draw(mask); md.ellipse((0, 0, R * 2 - 1, R * 2 - 1), fill=255)
        for i in range(7):
            y0 = int(R * 1.05 + i * i * 4.2 + i * 14)
            md.rectangle((0, y0, R * 2, y0 + 4 + i * 2), fill=0)
        sun.paste(sun_rgb, (0, 0), mask)
        glow = Image.new("RGBA", (R * 4, R * 4), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((R // 2, R // 2, R * 3.5, R * 3.5), fill=self.t["sun"][1] + (110,))
        glow = glow.filter(ImageFilter.GaussianBlur(R // 3))
        img.alpha_composite(glow, (cx - R * 2, cy - R * 2))
        img.alpha_composite(sun, (cx - R, cy - R))
        # skyline
        x = 0
        city = self.t["city"]
        while x < Wd:
            bw = rnd.randrange(40, 130); bh = rnd.randrange(int(self.H * 0.06), int(self.H * 0.3))
            if rnd.random() < 0.12:
                bh = int(bh * 1.6)
            d.rectangle((x, hz - bh, x + bw, hz), fill=city + (255,))
            if rnd.random() < 0.3:  # antena
                d.rectangle((x + bw // 2 - 2, hz - bh - 40, x + bw // 2 + 2, hz - bh), fill=city + (255,))
            if self.t["stars"] or rnd.random() < 0.3:
                for wy in range(hz - bh + 10, hz - 8, 16):
                    for wx in range(x + 8, x + bw - 8, 14):
                        if rnd.random() < 0.28:
                            col = rnd.choice([self.t["acc"], self.t["acc2"], (255, 230, 160)])
                            d.rectangle((wx, wy, wx + 5, wy + 7), fill=col + (rnd.randrange(120, 230),))
            x += bw + rnd.randrange(0, 18)
        self.sky = img
        self.sun_x = cx
        # palmeras en primer plano (capa propia)
        self.palms = Image.new("RGBA", (self.W + 1400, self.H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(self.palms)
        px = 60
        while px < self.palms.width:
            self._palm(pd, px, self.H + 20, rnd.uniform(0.75, 1.25), rnd)
            px += rnd.randrange(450, 900)
        # superposición oscura para legibilidad (+viñeta)
        ov = np.zeros((self.H, self.W, 4), np.uint8)
        yy, xx = np.mgrid[0:self.H, 0:self.W]
        dist = np.sqrt(((xx - self.W / 2) / (self.W / 2)) ** 2 + ((yy - self.H / 2) / (self.H / 2)) ** 2)
        ov[..., 3] = np.clip(70 + (dist - 0.6) * 160, 70, 210).astype(np.uint8)
        self.overlay = Image.fromarray(ov, "RGBA")

    def _palm(self, d, x, base, s, rnd):
        col = self.t["palm"] + (255,)
        h = int(self.H * 0.62 * s)
        lean = rnd.uniform(-0.25, 0.25)
        pts = []
        for i in range(30):
            t = i / 29
            pts.append((x + math.sin(t * 1.4) * lean * h * 0.5, base - t * h))
        for i in range(len(pts) - 1):
            w = int(lerp(26, 12, i / 29) * s)
            d.line([pts[i], pts[i + 1]], fill=col, width=w)
        tx, ty = pts[-1]
        for k in range(9):
            ang = -math.pi / 2 + (k - 4) * 0.42 + rnd.uniform(-0.1, 0.1)
            L = rnd.uniform(150, 230) * s
            leaf = []
            for j in range(14):
                t = j / 13
                lx = tx + math.cos(ang) * L * t
                ly = ty + math.sin(ang) * L * t + (t ** 2) * L * 0.55
                leaf.append((lx, ly))
            for j in range(len(leaf) - 1):
                d.line([leaf[j], leaf[j + 1]], fill=col, width=max(2, int((1 - j / 13) * 22 * s)))
        d.ellipse((tx - 16 * s, ty - 10 * s, tx + 16 * s, ty + 18 * s), fill=col)

    def frame(self, t):
        """Fondo animado en el instante t (segundos)."""
        off = int(120 + 260 * math.sin(t * 0.02))  # deriva lenta de cámara
        f = self.sky.crop((off, 0, off + self.W, self.H))
        d = ImageDraw.Draw(f)
        hz = self.hz
        wt = self.t["water"]
        # agua / suelo
        g = gradient(self.H - hz, [(0, wt[0]), (1, wt[1])]).astype(np.uint8)
        f.paste(Image.fromarray(np.repeat(g[:, None, :], self.W, axis=1), "RGB"), (0, hz))
        sx = self.sun_x - off
        if self.t["grid"]:
            col = self.t["acc"] + (200,)
            ph = (t * 0.6) % 1.0
            for i in range(14):
                z = (i + ph) / 14
                y = hz + (self.H - hz) * (z ** 2.2)
                d.line((0, y, self.W, y), fill=col, width=2)
            for k in range(-16, 17):
                d.line((self.W / 2 + k * 40, hz, self.W / 2 + k * 260, self.H), fill=col, width=2)
        else:
            # reflejo del sol que tiembla
            for i in range(16):
                y = hz + 8 + i * i * 1.6 + i * 6
                if y > self.H:
                    break
                w = (220 - i * 10) * (0.75 + 0.25 * math.sin(t * 2.2 + i * 1.7))
                d.rounded_rectangle((sx - w / 2, y, sx + w / 2, y + 4 + i * 0.4), 2,
                                    fill=self.t["sun"][1] + (int(190 - i * 9),))
        d.line((0, hz, self.W, hz), fill=self.t["sun"][0] + (160,), width=2)
        # palmeras con paralaje
        poff = int((t * 22) % 700)
        f.alpha_composite(self.palms.crop((poff, 0, poff + self.W, self.H)))
        f.alpha_composite(self.overlay)
        return f


# ------------------------------------------------------------------ escenas
class Scene:
    def __init__(self, spec, beat_times, dur, th):
        self.s, self.bt, self.dur, self.th = spec, beat_times, dur, th
        self.acc, self.acc2 = th["acc"], th["acc2"]
        self.cache = {}
        self.build()

    def reveal(self, idx):
        """Instante de aparición del elemento idx alineado al final de los beats."""
        n_items = self.n_items()
        off = len(self.bt) - n_items
        b = max(0, idx + off)
        return self.bt[b] if b < len(self.bt) else self.bt[-1]

    def n_items(self):
        return 0

    def build(self):
        pass

    def draw(self, f, t):
        pass

    # helpers comunes
    def header(self, f, t, text):
        if "hdr" not in self.cache:
            self.cache["hdr"] = text_sprite(text, font("anton", 92), glow=self.acc, glow_r=14)
        e = ease_out((t - 0.05) / 0.5)
        paste(f, self.cache["hdr"], W // 2, 175 - (1 - e) * 40, e)
        bw = int(260 * ease_out((t - 0.25) / 0.6))
        if bw > 2:
            ImageDraw.Draw(f).rounded_rectangle((W // 2 - bw, 250, W // 2 + bw, 257), 3, fill=self.acc + (255,))


class TitleScene(Scene):
    def build(self):
        self.kick = text_sprite(self.s["kicker"], font("mont", 40), fill=INK)
        kw, kh = self.kick.size
        self.pill = rounded(kw + 30, 74, 37, self.acc2 + (255,), shadow=True)
        self.lines = [text_sprite(l, font("anton", 190), glow=self.acc, glow_r=26, stroke=3, stroke_fill=INK)
                      for l in self.s["title"].split("\n")]

    def draw(self, f, t):
        e = ease_back((t - 0.1) / 0.5)
        paste(f, self.pill, W // 2, 250, min(1, e * 1.2))
        paste(f, self.kick, W // 2, 250, min(1, e * 1.2))
        y0 = 520 - (len(self.lines) - 1) * 105
        for i, l in enumerate(self.lines):
            e = ease_out((t - 0.25 - i * 0.18) / 0.55)
            sc = 1 + 0.015 * math.sin(t * 1.3)
            spr = l if abs(sc - 1) < 0.002 else l.resize((int(l.width * sc), int(l.height * sc)), Image.BILINEAR)
            paste(f, spr, W // 2, y0 + i * 210 + (1 - e) * 80, e)


class StatScene(Scene):
    def build(self):
        self.label = text_sprite(self.s["label"], font("mont", 46), fill=WHITE)
        v = self.s["value"]
        import re
        m = re.match(r"^(\d+)(.*)$", v)
        self.num = (int(m.group(1)), m.group(2)) if m and ":" not in v and int(m.group(1)) > 20 else None

    def draw(self, f, t):
        v = self.s["value"]
        p = ease_out((t - 0.15) / 1.3)
        if self.num:
            n, rest = self.num
            txt = f"{int(round(n * p))}{rest}"
        else:
            k = int(len(v) * min(1, (t - 0.15) / 0.6)) if t > 0.15 else 0
            txt = v[:k] + ("|" if int(t * 3) % 2 == 0 and k < len(v) else "")
        key = ("v", txt)
        if key not in self.cache:
            self.cache = {kk: vv for kk, vv in self.cache.items() if kk[0] != "v"}
            self.cache[key] = text_sprite(txt or " ", font("anton", 300), glow=self.acc, glow_r=34, stroke=4)
        pulse = 1 + 0.02 * math.sin(t * 2.0)
        spr = self.cache[key]
        spr = spr.resize((int(spr.width * pulse), int(spr.height * pulse)), Image.BILINEAR)
        paste(f, spr, W // 2, 470, ease_out(t / 0.3))
        e = ease_out((t - 0.6) / 0.5)
        bar = rounded(self.label.width + 60, 96, 20, (0, 0, 0, 150), outline=self.acc2 + (255,), width=3)
        paste(f, bar, W // 2, 740 + (1 - e) * 30, e)
        paste(f, self.label, W // 2, 740 + (1 - e) * 30, e)


class ListScene(Scene):
    """Viñetas (bullets) y tabla comparten el mismo estilo de tarjetas."""

    def n_items(self):
        return len(self.s.get("items") or self.s.get("rows"))

    def build(self):
        self.cards = []
        rows = self.s.get("rows")
        items = self.s.get("items")
        n = self.n_items()
        self.ch = 118 if n >= 4 else 130
        for i in range(n):
            card = rounded(1320, self.ch - 18, 22, (12, 6, 28, 205), outline=(255, 255, 255, 40), width=2, shadow=True)
            if rows:
                a = text_sprite(rows[i][0], font("mont", 44))
                b = text_sprite(rows[i][1], font("mont", 40), fill=self.acc2)
                card.alpha_composite(a, (80, (card.height - a.height) // 2))
                card.alpha_composite(b, (card.width - b.width - 70, (card.height - b.height) // 2))
            else:
                badge = Image.new("RGBA", (70, 70), (0, 0, 0, 0))
                ImageDraw.Draw(badge).ellipse((0, 0, 69, 69), fill=self.acc + (255,))
                num = text_sprite(str(i + 1), font("anton", 44), fill=INK)
                badge.alpha_composite(num, ((70 - num.width) // 2, (70 - num.height) // 2))
                card.alpha_composite(badge, (70, (card.height - 70) // 2))
                txt = items[i]
                if txt[:1].isdigit() and " · " in txt:
                    txt = txt.split(" · ", 1)[1]
                a = text_sprite(txt, font("mont", 48))
                card.alpha_composite(a, (165, (card.height - a.height) // 2))
            # barra de acento
            ImageDraw.Draw(card).rounded_rectangle((30, 40, 38, card.height - 40), 4, fill=self.acc + (255,))
            self.cards.append(card)

    def draw(self, f, t):
        self.header(f, t, self.s["title"])
        n = len(self.cards)
        y0 = 560 - (n - 1) * self.ch / 2
        for i, c in enumerate(self.cards):
            tr = self.reveal(i)
            e = ease_out((t - tr) / 0.45)
            if e <= 0:
                continue
            x = W // 2 + (1 - e) * (-260 if i % 2 == 0 else 260)
            paste(f, c, x, y0 + i * self.ch, e)
            # destello en la tarjeta recién aparecida
            if 0 < t - tr < 0.5:
                fl = rounded(1320, self.ch - 18, 22, self.acc + (int(90 * (1 - (t - tr) / 0.5)),))
                paste(f, fl, x, y0 + i * self.ch, 1)


class CompareScene(Scene):
    def n_items(self):
        return len(self.s["cards"])

    def build(self):
        n = self.n_items()
        self.cw = 560 if n == 2 else 480
        self.sprites = []
        for i, c in enumerate(self.s["cards"]):
            hi = c["price"] == "NO"
            card = rounded(self.cw, 520, 32, (12, 6, 28, 215), outline=(self.acc2 if not hi else (255, 80, 80)) + (255,),
                           width=4, shadow=True)
            nm = text_sprite(c["name"], font("anton", 64 if len(c["name"]) < 10 else 50))
            pr = text_sprite(c["price"], font("anton", 150), glow=self.acc, glow_r=20)
            nt = text_sprite(c["note"], font("montr", 34), fill=(230, 220, 255))
            cx = card.width // 2
            card.alpha_composite(nm, (cx - nm.width // 2, 70))
            card.alpha_composite(pr, (cx - pr.width // 2, 300 - pr.height // 2))
            card.alpha_composite(nt, (cx - nt.width // 2, 470))
            self.sprites.append(card)

    def draw(self, f, t):
        self.header(f, t, self.s["title"])
        n = len(self.sprites)
        gap = self.cw + 80
        for i, c in enumerate(self.sprites):
            e = ease_back((t - self.reveal(i)) / 0.5)
            if e <= 0.01:
                continue
            sc = max(0.05, e)
            spr = c.resize((max(1, int(c.width * sc)), max(1, int(c.height * sc))), Image.BILINEAR) if sc < 0.999 else c
            paste(f, spr, W // 2 + (i - (n - 1) / 2) * gap, 610 + 6 * math.sin(t * 1.5 + i), min(1, e))


class VerdictScene(Scene):
    def n_items(self):
        return 2

    def build(self):
        self.cols = []
        for k, (lst, col) in enumerate(((self.s["left"], self.acc), (self.s["right"], self.acc2))):
            card = rounded(760, 520, 30, (12, 6, 28, 215), outline=col + (255,), width=4, shadow=True)
            hd = text_sprite(lst[0], font("anton", 70), fill=col)
            card.alpha_composite(hd, ((card.width - hd.width) // 2, 70))
            for j, it in enumerate(lst[1:]):
                tx = text_sprite("✓  " if False else it, font("mont", 42))
                dot = Image.new("RGBA", (26, 26), (0, 0, 0, 0))
                ImageDraw.Draw(dot).ellipse((0, 0, 25, 25), fill=col + (255,))
                y = 240 + j * 105
                card.alpha_composite(dot, (90, y + 20))
                card.alpha_composite(tx, (140, y + 33 - tx.height // 2))
            self.cols.append(card)

    def draw(self, f, t):
        self.header(f, t, self.s["title"])
        for i, c in enumerate(self.cols):
            e = ease_out((t - self.reveal(i)) / 0.5)
            paste(f, c, W // 2 + (i - 0.5) * 840, 590 + (1 - e) * 120, e)


class AlertScene(Scene):
    def build(self):
        self.lab = text_sprite(self.s["label"], font("anton", 64), fill=INK)
        self.txt = text_sprite(self.s["text"], font("mont", 58), spacing=22)
        self.cw = max(1200, self.txt.width + 160)
        self.card = rounded(self.cw, self.txt.height + 220, 36, (12, 6, 28, 225), shadow=True)
        self.badge = rounded(self.lab.width + 50, 100, 22, self.acc2 + (255,), shadow=True)
        self.icon = text_sprite("!", font("anton", 110), fill=INK)

    def draw(self, f, t):
        e = ease_back(t / 0.5)
        sc = max(0.05, min(e, 1.2))
        cy = 560
        card = self.card if abs(sc - 1) < 0.01 else self.card.resize((int(self.card.width * sc), int(self.card.height * sc)))
        paste(f, card, W // 2, cy, min(1, e))
        # borde pulsante
        p = 0.5 + 0.5 * math.sin(t * 4)
        ch = self.card.height - 60
        if e > 0.9:
            d = ImageDraw.Draw(f)
            d.rounded_rectangle((W // 2 - self.cw // 2, cy - ch // 2, W // 2 + self.cw // 2, cy + ch // 2), 36,
                                outline=mix(self.acc, self.acc2, p) + (255,), width=5)
        paste(f, self.txt, W // 2, cy + 40, ease_out((t - 0.3) / 0.4))
        eb = ease_back((t - 0.2) / 0.45)
        paste(f, self.badge, W // 2, cy - ch // 2, min(1, eb))
        paste(f, self.lab, W // 2, cy - ch // 2, min(1, eb))
        # triángulo de aviso
        tri = Image.new("RGBA", (170, 150), (0, 0, 0, 0))
        ImageDraw.Draw(tri).polygon([(85, 0), (170, 150), (0, 150)], fill=self.acc2 + (255,))
        tri.alpha_composite(self.icon, (85 - self.icon.width // 2, 92 - self.icon.height // 2))
        paste(f, tri, W // 2, 205 + 8 * math.sin(t * 3), ease_out(t / 0.4))


class TimelineScene(Scene):
    def n_items(self):
        return len(self.s["events"])

    def build(self):
        self.ev = [(text_sprite(y, font("anton", 78), glow=self.acc, glow_r=12),
                    text_sprite(l, font("mont", 36), spacing=8)) for y, l in self.s["events"]]

    def draw(self, f, t):
        self.header(f, t, self.s["title"])
        n = len(self.ev)
        x0, x1, y = 260, W - 260, 600
        d = ImageDraw.Draw(f)
        # línea que avanza hasta el último evento revelado
        last = -1
        for i in range(n):
            if t >= self.reveal(i):
                last = i
        xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
        target = xs[max(last, 0)] if last >= 0 else x0
        prev = xs[max(last - 1, 0)]
        tr = self.reveal(max(last, 0))
        cur = lerp(prev, target, ease_out((t - tr) / 0.5)) if last >= 0 else x0
        d.rounded_rectangle((x0 - 40, y - 4, x1 + 40, y + 4), 4, fill=(255, 255, 255, 60))
        d.rounded_rectangle((x0 - 40, y - 5, cur, y + 5), 5, fill=self.acc + (255,))
        for i, (ys, ls) in enumerate(self.ev):
            e = ease_back((t - self.reveal(i)) / 0.45)
            if e <= 0.01:
                continue
            r = 26 * min(e, 1.2)
            d.ellipse((xs[i] - r - 10, y - r - 10, xs[i] + r + 10, y + r + 10), fill=self.acc + (90,))
            d.ellipse((xs[i] - r, y - r, xs[i] + r, y + r), fill=self.acc2 + (255,))
            paste(f, ys, xs[i], y - 120 - (1 - min(e, 1)) * 30, min(1, e))
            paste(f, ls, xs[i], y + 110 + (1 - min(e, 1)) * 30, min(1, e))


class MapScene(Scene):
    # posiciones ilustrativas (no es el mapa oficial)
    POS = {"MOUNT KALAGA": (0.38, 0.12), "AMBROSIA": (0.5, 0.33), "PORT GELLHORN": (0.22, 0.3),
           "GRASSRIVERS": (0.5, 0.62), "VICE CITY": (0.78, 0.66), "LEONIDA KEYS": (0.45, 0.93)}

    def n_items(self):
        return len(self.s["regions"])

    def build(self):
        self.mw, self.mh = 820, 680
        self.mx, self.my = 170, 215
        rnd = random.Random(7)
        base = Image.new("RGBA", (self.mw, self.mh), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        # península ficticia con forma orgánica
        pts = []
        outline = [(0.05, 0.02), (0.95, 0.02), (0.95, 0.15), (0.88, 0.35), (0.9, 0.55), (0.86, 0.75), (0.74, 0.86),
                   (0.6, 0.84), (0.5, 0.76), (0.42, 0.66), (0.36, 0.5), (0.24, 0.42), (0.12, 0.38), (0.05, 0.3)]
        for i in range(len(outline)):
            a, b = outline[i], outline[(i + 1) % len(outline)]
            for k in range(8):
                tt = k / 8
                x = lerp(a[0], b[0], tt) * self.mw + rnd.uniform(-6, 6)
                y = lerp(a[1], b[1], tt) * self.mh + rnd.uniform(-6, 6)
                pts.append((x, y))
        glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).polygon(pts, fill=self.acc2 + (150,))
        base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(18)))
        d.polygon(pts, fill=(18, 40, 52, 235), outline=self.acc2 + (255,))
        d.line(pts + [pts[0]], fill=self.acc2 + (255,), width=4)
        # cayos
        for i in range(9):
            x = self.mw * (0.62 - i * 0.05); y = self.mh * (0.9 + i * 0.008)
            d.ellipse((x - 14, y - 7, x + 14, y + 7), fill=(18, 40, 52, 235), outline=self.acc2 + (255,), width=3)
        # cuadrícula
        for gx in range(0, self.mw, 80):
            d.line((gx, 0, gx, self.mh), fill=(255, 255, 255, 18))
        for gy in range(0, self.mh, 80):
            d.line((0, gy, self.mw, gy), fill=(255, 255, 255, 18))
        self.base = base
        self.labels = [text_sprite(r, font("mont", 30)) for r in self.s["regions"]]
        self.rows = [text_sprite(r, font("anton", 56)) for r in self.s["regions"]]
        self.note = text_sprite("Ilustración orientativa · no es el mapa oficial", font("montr", 24), fill=(200, 200, 220))
        self.title = text_sprite("LEONIDA", font("anton", 110), glow=self.acc, glow_r=16)

    def draw(self, f, t):
        e = ease_out(t / 0.6)
        paste(f, self.base, self.mx, self.my + (1 - e) * 40, e, anchor="tl")
        paste(f, self.note, self.mx + self.mw // 2, self.my - 30, e)
        paste(f, self.title, 1440, 200, ease_out((t - 0.2) / 0.5))
        d = ImageDraw.Draw(f)
        for i, r in enumerate(self.s["regions"]):
            tr = self.reveal(i)
            er = ease_back((t - tr) / 0.45)
            if er <= 0.01:
                continue
            px, py = self.POS.get(r, (0.5, 0.5))
            x, y = self.mx + px * self.mw, self.my + py * self.mh
            active = i == len(self.s["regions"]) - 1 or t < self.reveal(i + 1)
            col = self.acc if active else self.acc2
            rr = 20 * min(er, 1.2)
            if active:
                ring = 20 + 30 * ((t * 1.4) % 1)
                d.ellipse((x - ring, y - ring, x + ring, y + ring), outline=col + (int(255 * (1 - (t * 1.4) % 1)),), width=4)
            d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=col + (255,), outline=WHITE + (255,), width=3)
            paste(f, self.labels[i], x, y - 46, min(1, er))
            # lista lateral
            ey = 330 + i * 105
            card = self.cache.get(("row", i, active))
            if card is None:
                card = rounded(700, 86, 18, (col + (235,)) if active else (12, 6, 28, 200), shadow=False)
                spr = text_sprite(r, font("anton", 56), fill=INK if active else WHITE)
                card.alpha_composite(spr, (40, (86 - spr.height) // 2))
                self.cache[("row", i, active)] = card
            paste(f, card, 1440 + (1 - min(er, 1)) * 200, ey, min(1, er))


class CharacterScene(Scene):
    def n_items(self):
        return len(self.s["traits"])

    def build(self):
        col = self.acc if self.s["color"] == "pink" else self.acc2
        if self.s["color"] == "cyan":
            col = (41, 227, 255)
        if self.s["color"] == "pink":
            col = (255, 46, 136)
        self.col = col
        # silueta estilizada (busto) con luz de neón
        sw, sh = 640, 820
        sil = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(sil)
        fem = self.s["color"] == "pink"
        cx = sw // 2
        d.ellipse((cx - 300, 560, cx + 300, 1100), fill=(10, 4, 20, 255))  # hombros
        d.rectangle((cx - 60, 440, cx + 60, 600), fill=(10, 4, 20, 255))  # cuello
        d.ellipse((cx - 130, 170, cx + 130, 500), fill=(10, 4, 20, 255))  # cabeza
        if fem:
            d.ellipse((cx - 175, 140, cx + 165, 420), fill=(10, 4, 20, 255))
            d.polygon([(cx - 175, 280), (cx - 210, 640), (cx - 70, 560)], fill=(10, 4, 20, 255))
            d.polygon([(cx + 165, 280), (cx + 200, 640), (cx + 70, 560)], fill=(10, 4, 20, 255))
        else:
            d.ellipse((cx - 140, 150, cx + 140, 330), fill=(10, 4, 20, 255))
            d.rectangle((cx - 100, 380, cx + 100, 470), fill=(10, 4, 20, 255))  # barba/mandíbula
        mask = sil.getchannel("A")
        rim = Image.new("RGBA", (sw, sh), col + (0,))
        edge = mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(3))
        rim.putalpha(edge)
        glow = Image.new("RGBA", (sw, sh), col + (0,))
        glow.putalpha(mask.filter(ImageFilter.GaussianBlur(40)).point(lambda v: int(v * 0.7)))
        out = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        out.alpha_composite(glow)
        out.alpha_composite(sil)
        out.alpha_composite(rim)
        q = text_sprite("?", font("anton", 220), fill=col + (90,))
        out.alpha_composite(q, (cx - q.width // 2, 330 - q.height // 2))
        self.sil = out
        parts = self.s["name"].split(" ", 1)
        self.n1 = text_sprite(parts[0], font("anton", 150), glow=col, glow_r=20)
        self.n2 = text_sprite(parts[1] if len(parts) > 1 else "", font("anton", 150), fill=col)
        self.tr = []
        for tx in self.s["traits"]:
            c = rounded(860, 96, 20, (12, 6, 28, 210), outline=col + (200,), width=3, shadow=True)
            s = text_sprite(tx, font("mont", 40))
            c.alpha_composite(s, (30 + 50, 30 + (96 - s.height) // 2))
            self.tr.append(c)

    def draw(self, f, t):
        e = ease_out(t / 0.7)
        paste(f, self.sil, 480 - (1 - e) * 200, 640 + 10 * math.sin(t * 1.2), e)
        paste(f, self.n1, 1280, 230 - (1 - ease_out((t - 0.2) / 0.5)) * 40, ease_out((t - 0.2) / 0.5), anchor="mm")
        paste(f, self.n2, 1280, 405 - (1 - ease_out((t - 0.35) / 0.5)) * 40, ease_out((t - 0.35) / 0.5))
        for i, c in enumerate(self.tr):
            et = ease_out((t - self.reveal(i)) / 0.45)
            paste(f, c, 1300 + (1 - et) * 220, 560 + i * 125, et)


class OutroScene(Scene):
    def build(self):
        self.big = text_sprite("SUSCRÍBETE", font("anton", 170), fill=WHITE)
        self.btn = rounded(self.big.width + 120, 230, 115, (230, 30, 50, 255), shadow=True)
        self.ch = text_sprite(CHANNEL, font("anton", 80), glow=self.acc, glow_r=16)
        self.sub = text_sprite("Guías y noticias de GTA 6 desde el día 1", font("mont", 42))

    def draw(self, f, t):
        e = ease_back(t / 0.55)
        pulse = 1 + 0.035 * math.sin(t * 5)
        sc = max(0.05, min(e, 1.2)) * pulse
        b = self.btn.resize((int(self.btn.width * sc), int(self.btn.height * sc)))
        g = self.big.resize((int(self.big.width * sc), int(self.big.height * sc)))
        paste(f, b, W // 2, 480, min(1, e))
        paste(f, g, W // 2, 480, min(1, e))
        # campana
        bx, by = W // 2 + self.btn.width // 2 * sc + 90, 470
        if e > 0.5:
            sw = math.sin(t * 9) * 12 * (1 if (t % 2) < 0.6 else 0)
            bell = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bell)
            bd.pieslice((30, 20, 130, 130), 180, 360, fill=self.acc2 + (255,))
            bd.rectangle((30, 74, 130, 112), fill=self.acc2 + (255,))
            bd.rounded_rectangle((18, 108, 142, 124), 6, fill=self.acc2 + (255,))
            bd.ellipse((66, 122, 94, 146), fill=self.acc2 + (255,))
            bell = bell.rotate(sw, resample=Image.BICUBIC)
            paste(f, bell, bx, by, ease_out((t - 0.3) / 0.4))
        paste(f, self.ch, W // 2, 250, ease_out((t - 0.2) / 0.5))
        paste(f, self.sub, W // 2, 690, ease_out((t - 0.45) / 0.5))
        # tarjetas de pantalla final
        for i in range(2):
            et = ease_out((t - 0.8 - i * 0.15) / 0.5)
            c = self.cache.get(("end", i))
            if c is None:
                c = rounded(560, 150, 20, (12, 6, 28, 200), outline=(self.acc if i == 0 else self.acc2) + (255,), width=3)
                s = text_sprite("SIGUIENTE VÍDEO »" if i == 0 else "LISTA: GTA 6 DÍA 1", font("mont", 34))
                c.alpha_composite(s, ((560 - s.width) // 2, (150 - s.height) // 2))
                self.cache[("end", i)] = c
            paste(f, c, W // 2 + (i - 0.5) * 640, 830 + (1 - et) * 60, et)


class IntroScene(Scene):
    def build(self):
        self.logo = text_sprite(CHANNEL, font("anton", 130), glow=self.acc, glow_r=26, stroke=2)
        self.tag = text_sprite("CANAL NO OFICIAL · GTA 6", font("mont", 34), fill=self.acc2)

    def draw(self, f, t):
        d = ImageDraw.Draw(f)
        e = ease_out(t / 0.6)
        # destello de barras
        for i in range(6):
            x = lerp(-600, W + 600, ease_out((t - i * 0.05) / 0.9))
            d.polygon([(x, 0), (x + 120, 0), (x - 300, H), (x - 420, H)],
                      fill=(self.acc if i % 2 else self.acc2) + (int(120 * (1 - min(1, t / 1.2))),))
        sc = 1.25 - 0.25 * e
        lg = self.logo.resize((int(self.logo.width * sc), int(self.logo.height * sc)))
        out = 1 - ease_out((t - (self.dur - 0.4)) / 0.4)
        paste(f, lg, W // 2, 500, e * out)
        paste(f, self.tag, W // 2, 640, ease_out((t - 0.5) / 0.4) * out)


TYPES = {"title": TitleScene, "stat": StatScene, "table": ListScene, "bullets": ListScene,
         "compare": CompareScene, "verdict": VerdictScene, "alert": AlertScene, "timeline": TimelineScene,
         "map": MapScene, "character": CharacterScene, "outro": OutroScene, "intro": IntroScene}


# ------------------------------------------------------------------ HUD, transición y subtítulos
class Hud:
    def __init__(self, video, th, total):
        self.th, self.total = th, total
        self.bug = text_sprite(CHANNEL, font("mont", 28), fill=WHITE)
        self.dot = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
        ImageDraw.Draw(self.dot).ellipse((0, 0, 21, 21), fill=th["acc"] + (255,))
        topic = video["thumb"]["badge"]
        self.topic = text_sprite("GTA 6 · " + topic, font("mont", 26), fill=INK)
        self.topic_bg = rounded(self.topic.width + 10, 50, 25, th["acc2"] + (255,))
        self.caps = {}

    def draw(self, f, t, cap):
        paste(f, self.dot, 70, 70, 0.6 + 0.4 * math.sin(t * 3))
        paste(f, self.bug, 90, 70, 0.9, anchor="lm")
        paste(f, self.topic_bg, W - 70 - self.topic_bg.width // 2, 70)
        paste(f, self.topic, W - 70 - self.topic_bg.width // 2, 70)
        d = ImageDraw.Draw(f)
        d.rectangle((0, H - 8, int(W * t / self.total), H), fill=self.th["acc"] + (255,))
        if cap:
            if cap not in self.caps:
                if len(self.caps) > 30:
                    self.caps.clear()
                s = text_sprite(cap, font("mont", 46), stroke=5, stroke_fill=(0, 0, 0))
                self.caps[cap] = s
            s = self.caps[cap]
            bg = rounded(s.width + 30, s.height + 4, 16, (0, 0, 0, 120))
            paste(f, bg, W // 2, H - 110)
            paste(f, s, W // 2, H - 110)


def wipe(f, p, th):
    """Transición de barras diagonales (p de 0 a 1)."""
    d = ImageDraw.Draw(f)
    for i, col in enumerate((th["acc"], th["acc2"], INK)):
        q = ease_out(min(1, max(0, p * 1.3 - i * 0.12)))
        x = lerp(W + 500, -900, q)
        d.polygon([(x, 0), (x + 700, 0), (x + 400, H), (x - 300, H)], fill=col + (255,))


def chunk_caption(text, dur):
    words = text.split()
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(" ".join(cur)) > 38 or w.endswith((".", "?", ":", ";")) and len(cur) > 3:
            chunks.append(" ".join(cur)); cur = []
    if cur:
        if chunks and len(" ".join(cur)) < 14:
            chunks[-1] += " " + " ".join(cur)
        else:
            chunks.append(" ".join(cur))
    total = sum(len(c) for c in chunks)
    out, t = [], 0.0
    for c in chunks:
        d = dur * len(c) / total
        out.append((t, t + d, c)); t += d
    return out


# ------------------------------------------------------------------ montaje
def plan(video):
    timing = json.load(open(os.path.join(BUILD, video["id"], "timing.json")))
    scenes = [{"spec": {"type": "intro", "beats": []}, "start": 0.0, "dur": INTRO, "beats": []}]
    t = INTRO
    captions, clips = [], []
    for spec, beats in zip(video["scenes"], timing):
        start = t
        bt, cur = [], LEAD
        for b in beats:
            bt.append(cur)
            clips.append((start + cur, b["file"]))
            for a, z, c in chunk_caption(b["text"], b["dur"]):
                captions.append((start + cur + a, start + cur + z, c))
            cur += b["dur"] + GAP
        dur = cur - GAP + TAIL
        scenes.append({"spec": spec, "start": start, "dur": dur, "beats": bt})
        t += dur
    return scenes, captions, clips, t


def fmt_srt(x):
    h = int(x // 3600); m = int(x % 3600 // 60); s = x % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def render(video):
    th = THEMES[video["theme"]]
    scenes, captions, clips, total = plan(video)
    vdir = os.path.join(OUT, f'{video["id"]}-{video["slug"]}')
    os.makedirs(vdir, exist_ok=True)
    bdir = os.path.join(BUILD, video["id"])
    bg = Background(video["theme"], seed=int(video["id"]))
    hud = Hud(video, th, total)
    objs = [TYPES[s["spec"]["type"]](s["spec"], s["beats"], s["dur"], th) for s in scenes]

    # subtítulos SRT
    with open(os.path.join(vdir, "subtitulos.es.srt"), "w") as fh:
        for i, (a, z, c) in enumerate(captions, 1):
            fh.write(f"{i}\n{fmt_srt(a)} --> {fmt_srt(z)}\n{c}\n\n")

    if PREVIEW:
        for i, (s, o) in enumerate(zip(scenes, objs)):
            tt = s["dur"] * 0.92
            fr = bg.frame(s["start"] + tt); o.draw(fr, tt); hud.draw(fr, s["start"] + tt, None)
            fr.convert("RGB").save(os.path.join(bdir, f"preview_{i:02d}.jpg"), quality=85)
        return

    # audio
    sfx_times = [s["start"] for s in scenes[1:]]
    audio.mix(clips, sfx_times, total, os.path.join(bdir, "mix.wav"))

    nframes = int(math.ceil(total * FPS))
    tmp = os.path.join(bdir, "video.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", os.path.join(bdir, "mix.wav"),
                           "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "2600k", "-bufsize", "5200k",
                           "-tune", "animation", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                           "-movflags", "+faststart", "-shortest", tmp], stdin=subprocess.PIPE)
    si, ci = 0, 0
    for n in range(nframes):
        t = n / FPS
        while si + 1 < len(scenes) and t >= scenes[si + 1]["start"]:
            si += 1
        s, o = scenes[si], objs[si]
        lt = t - s["start"]
        fr = bg.frame(t)
        o.draw(fr, lt)
        while ci < len(captions) and captions[ci][1] < t:
            ci += 1
        cap = captions[ci][2] if ci < len(captions) and captions[ci][0] <= t else None
        if s["spec"]["type"] != "intro":
            hud.draw(fr, t, cap)
        # transición: barras que cruzan en el cambio de escena
        if si > 0 and lt < 0.45:
            wipe(fr, 0.5 + lt / 0.9, th)
        if si + 1 < len(scenes) and scenes[si + 1]["start"] - t < 0.225:
            wipe(fr, (0.225 - (scenes[si + 1]["start"] - t)) / 0.45, th)
        if t < 0.3:  # fundido de entrada
            fr = Image.blend(Image.new("RGBA", fr.size, (0, 0, 0, 255)), fr, t / 0.3)
        if total - t < 0.6:
            fr = Image.blend(Image.new("RGBA", fr.size, (0, 0, 0, 255)), fr, max(0, (total - t) / 0.6))
        ff.stdin.write(fr.convert("RGB").tobytes())
        if n % 900 == 0:
            print(video["id"], f"{n}/{nframes}", flush=True)
    ff.stdin.close(); ff.wait()
    final = os.path.join(vdir, f'{video["id"]}-{video["slug"]}.mp4')
    os.replace(tmp, final)
    thumbnail(video, os.path.join(vdir, "miniatura.png"))
    print("OK", final, round(total, 1), "s", flush=True)


def thumbnail(video, path):
    th = THEMES[video["theme"]]
    bg = Background(video["theme"], seed=int(video["id"]) + 50)
    f = bg.frame(3.0)
    # menos oscuro en la miniatura: más color
    d = ImageDraw.Draw(f)
    tb = video["thumb"]
    top = text_sprite(tb["top"], font("anton", 150), stroke=6, stroke_fill=INK)
    big = text_sprite(tb["big"], font("anton", 300 if len(tb["big"]) <= 8 else 200), fill=th["acc2"],
                      glow=th["acc"], glow_r=30, stroke=8, stroke_fill=INK)
    if big.width > W - 120:
        r = (W - 120) / big.width
        big = big.resize((int(big.width * r), int(big.height * r)), Image.LANCZOS)
    paste(f, top, W // 2, 260)
    paste(f, big, W // 2, 560)
    badge_t = text_sprite(tb["badge"], font("anton", 110), fill=WHITE)
    badge = rounded(badge_t.width + 40, badge_t.height + 10, 26, (230, 30, 50, 255), shadow=True)
    badge.alpha_composite(badge_t, (30 + 20, 30 + 5))
    badge = badge.rotate(-6, expand=True, resample=Image.BICUBIC)
    paste(f, badge, W - badge.width // 2 - 70, H - badge.height // 2 - 60)
    paste(f, text_sprite("GTA 6", font("anton", 120), fill=WHITE, glow=th["acc"], glow_r=20, stroke=5),
          260, H - 140)
    f.convert("RGB").resize((1280, 720), Image.LANCZOS).save(path, optimize=True)


if __name__ == "__main__":
    ids = sys.argv[1:]
    for v in VIDEOS:
        if not ids or v["id"] in ids:
            if os.environ.get("THUMB_ONLY"):
                vdir = os.path.join(OUT, f'{v["id"]}-{v["slug"]}'); os.makedirs(vdir, exist_ok=True)
                thumbnail(v, os.path.join(vdir, "miniatura.png")); continue
            render(v)
