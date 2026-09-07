#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Мультфильм: зелёный совёнок-полиглот пьёт кофе на стуле, ему становится
нехорошо, он мчится в туалет и... облегчается. Комедия в мультяшном стиле.

Кадры рисуются на Pillow, звук синтезируется на numpy, всё склеивается ffmpeg.
Запуск:  python3 make_video.py [выходной_файл.mp4]
"""

import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import imageio_ffmpeg

# ---------------------------------------------------------------- настройки

W, H, FPS = 960, 540, 24
S = 2                      # суперсэмплинг для сглаживания
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

GREEN      = (122, 205, 60)
GREEN_D    = (72, 148, 33)
GREEN_SICK = (150, 178, 118)
BELLY      = (226, 245, 200)
BELLY_SICK = (216, 226, 186)
ORANGE     = (255, 182, 44)
ORANGE_D   = (222, 134, 16)
INK        = (38, 38, 44)
WHITE      = (255, 255, 255)

_font_cache = {}


def font(size):
    key = int(size * S)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_PATH, key)
    return _font_cache[key]


def lerp(a, b, t):
    return a + (b - a) * t


def mixc(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(lerp(a[i], b[i], t))) for i in range(3))


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


def clamp01(t):
    return max(0.0, min(1.0, t))


# ------------------------------------------------- примитивы (единицы -> S)

def ell(d, cx, cy, rx, ry, fill=None, outline=None, w=3):
    d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S],
              fill=fill, outline=outline, width=max(1, int(w * S)))


def rect(d, x0, y0, x1, y1, fill=None, outline=None, w=3, r=0):
    box = [x0 * S, y0 * S, x1 * S, y1 * S]
    if r:
        d.rounded_rectangle(box, radius=r * S, fill=fill, outline=outline,
                            width=max(1, int(w * S)))
    else:
        d.rectangle(box, fill=fill, outline=outline, width=max(1, int(w * S)))


def poly(d, pts, fill=None, outline=None, w=3):
    d.polygon([(x * S, y * S) for x, y in pts], fill=fill, outline=outline,
              width=max(1, int(w * S)))


def line(d, pts, fill=INK, w=3):
    d.line([(x * S, y * S) for x, y in pts], fill=fill,
           width=max(1, int(w * S)), joint="curve")


def arc(d, cx, cy, rx, ry, a0, a1, fill=INK, w=3):
    d.arc([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S],
          a0, a1, fill=fill, width=max(1, int(w * S)))


def text(d, x, y, s, size=28, fill=INK, anchor="mm", stroke=0, stroke_fill=WHITE):
    d.text((x * S, y * S), s, font=font(size), fill=fill, anchor=anchor,
           stroke_width=int(stroke * S), stroke_fill=stroke_fill)


def new_layer(w=W, h=H):
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


# ------------------------------------------------------------------ совёнок

OW, OH = 320, 360          # размер слоя персонажа в единицах
OCX, OCY = OW / 2, OH / 2  # центр слоя


def render_owl(*, eyes="open", pupil=(0, 0), beak="closed", sick=0.0,
               belly=0.0, arms="down", feet="stand", phase=0.0, sweat=0,
               brows=0.0, mug=None, strain=0.0):
    """Рисует совёнка на прозрачном слое. Центр тела — в центре слоя."""
    img, d = new_layer(OW, OH)
    body_c = mixc(GREEN, GREEN_SICK, sick)
    body_d = mixc(GREEN_D, (86, 112, 66), sick)
    belly_c = mixc(BELLY, BELLY_SICK, sick)

    x0, y0 = OCX, OCY
    br = 1.0 + belly * 0.18

    # лапы
    fy = y0 + 92
    if feet == "run":
        a = math.sin(phase) * 30
        b = -a
        for dx, off, sw in ((-18, a, 1), (20, b, -1)):
            fx = x0 + dx + off * 1.0
            fyy = fy + 22 - abs(off) * 0.5
            line(d, [(x0 + dx * 0.5, fy - 18), (fx, fyy)], body_d, 10)
            ell(d, fx + sw * 7, fyy + 7, 18, 10, ORANGE, ORANGE_D, 3)
    elif feet == "sit":
        for dx in (-34, 34):
            ell(d, x0 + dx, fy + 4, 18, 10, ORANGE, ORANGE_D, 3)
    elif feet == "hidden":
        pass
    else:
        for dx in (-30, 30):
            ell(d, x0 + dx, fy + 8, 20, 11, ORANGE, ORANGE_D, 3)

    # хвостовые пёрышки
    poly(d, [(x0 - 12, y0 + 74), (x0 + 12, y0 + 74), (x0 + 2, y0 + 108)],
         body_d, body_d, 2)

    # тело
    ell(d, x0, y0 + 8, 76 * br, 82 * (1 + belly * 0.06), body_c, body_d, 4)
    # ушки
    poly(d, [(x0 - 58, y0 - 50), (x0 - 36, y0 - 86), (x0 - 18, y0 - 58)],
         body_c, body_d, 4)
    poly(d, [(x0 + 58, y0 - 50), (x0 + 36, y0 - 86), (x0 + 18, y0 - 58)],
         body_c, body_d, 4)
    # животик
    ell(d, x0, y0 + 30, 50 * br, 52 * (1 + belly * 0.10), belly_c, None, 0)

    # крылья
    if arms == "clutch":
        ell(d, x0 - 46, y0 + 34, 26, 17, body_c, body_d, 3)
        ell(d, x0 + 46, y0 + 34, 26, 17, body_c, body_d, 3)
    elif arms == "up":
        ell(d, x0 - 82, y0 - 26, 16, 34, body_c, body_d, 3)
        ell(d, x0 + 82, y0 - 26, 16, 34, body_c, body_d, 3)
    elif arms == "run":
        a = math.sin(phase) * 26
        ell(d, x0 - 74, y0 + 6 - a, 14, 30, body_c, body_d, 3)
        ell(d, x0 + 74, y0 + 6 + a, 14, 30, body_c, body_d, 3)
    elif arms == "hold":
        ell(d, x0 - 74, y0 + 16, 15, 30, body_c, body_d, 3)
        ell(d, x0 + 70, y0 + 2, 16, 28, body_c, body_d, 3)
    else:
        ell(d, x0 - 74, y0 + 14, 15, 32, body_c, body_d, 3)
        ell(d, x0 + 74, y0 + 14, 15, 32, body_c, body_d, 3)

    # глаза
    ex, ey = 30, 24
    px, py = pupil
    if eyes in ("open", "wide", "dizzy"):
        r = 25 if eyes == "open" else 30
        for sgn in (-1, 1):
            cx = x0 + sgn * ex
            cy = y0 - ey
            ell(d, cx, cy, r, r, WHITE, body_d, 3)
            if eyes == "dizzy":
                arc(d, cx, cy, 13, 13, 0, 360, INK, 4)
                arc(d, cx, cy, 7, 7, 0, 360, INK, 4)
            else:
                pr = 12 if eyes == "open" else 9
                ell(d, cx + px, cy + py, pr, pr, INK)
                ell(d, cx + px - pr * 0.35, cy + py - pr * 0.4, pr * 0.3,
                    pr * 0.3, WHITE)
    elif eyes == "closed_happy":
        for sgn in (-1, 1):
            arc(d, x0 + sgn * ex, y0 - ey + 8, 22, 18, 190, 350, INK, 5)
    elif eyes == "closed_squeeze":
        for sgn in (-1, 1):
            arc(d, x0 + sgn * ex, y0 - ey - 8, 22, 18, 20, 160, INK, 6)
    elif eyes == "relief":
        for sgn in (-1, 1):
            arc(d, x0 + sgn * ex, y0 - ey + 4, 22, 16, 195, 345, INK, 5)
    elif eyes == "worried":
        for sgn in (-1, 1):
            cx = x0 + sgn * ex
            cy = y0 - ey
            ell(d, cx, cy, 26, 22, WHITE, body_d, 3)
            ell(d, cx + px, cy + py + 4, 10, 10, INK)

    # брови
    if brows > 0.01:
        for sgn in (-1, 1):
            bx = x0 + sgn * ex
            by = y0 - ey - 30
            line(d, [(bx - sgn * 20, by + 8 * brows),
                     (bx + sgn * 18, by - 6 * brows)], INK, 5)

    # клюв
    by = y0 + 6
    if beak == "closed":
        poly(d, [(x0 - 17, by - 4), (x0 + 17, by - 4), (x0, by + 22)],
             ORANGE, ORANGE_D, 3)
    elif beak == "smile":
        poly(d, [(x0 - 19, by - 6), (x0 + 19, by - 6), (x0, by + 20)],
             ORANGE, ORANGE_D, 3)
        arc(d, x0, by + 2, 17, 14, 20, 160, ORANGE_D, 3)
    elif beak in ("open", "wide"):
        h = 30 if beak == "open" else 46
        wdt = 22 if beak == "open" else 30
        ell(d, x0, by + h * 0.45, wdt * 0.92, h * 0.55, (150, 46, 46),
            ORANGE_D, 3)
        ell(d, x0, by + h * 0.72, wdt * 0.45, h * 0.22, (206, 92, 96), None, 0)
        poly(d, [(x0 - wdt, by - 12), (x0 + wdt, by - 12), (x0, by + 4)],
             ORANGE, ORANGE_D, 3)
    elif beak == "flat":
        line(d, [(x0 - 18, by + 2), (x0 + 18, by + 2)], ORANGE_D, 6)
        poly(d, [(x0 - 15, by - 6), (x0 + 15, by - 6), (x0, by + 10)],
             ORANGE, ORANGE_D, 3)

    # напряжение — щёчки красные
    if strain > 0.01:
        c = (int(240), int(120 - 40 * strain), int(120 - 40 * strain))
        for sgn in (-1, 1):
            ell(d, x0 + sgn * 60, y0 + 2, 16, 11, c, None, 0)

    # капельки пота
    for i in range(sweat):
        ang = -0.9 + i * 0.75
        sx = x0 + math.cos(ang) * 78
        sy = y0 - 42 + math.sin(ang) * 30 + (i % 2) * 8
        poly(d, [(sx, sy - 12), (sx + 7, sy + 5), (sx - 7, sy + 5)],
             (150, 210, 255), (70, 140, 210), 2)
        ell(d, sx, sy + 5, 7, 6, (150, 210, 255), (70, 140, 210), 2)

    # кружка в крыле
    if mug is not None:
        mx, my = mug
        draw_mug(d, x0 + mx, y0 + my, 1.0)

    return img


def draw_mug(d, cx, cy, s=1.0, tilt=0.0):
    w_, h_ = 30 * s, 32 * s
    arc(d, cx + w_ * 0.95, cy, 12 * s, 12 * s, 250, 110, (245, 245, 245), 5)
    rect(d, cx - w_ / 2, cy - h_ / 2, cx + w_ / 2, cy + h_ / 2,
         (250, 250, 250), (120, 120, 130), 3, r=6 * s)
    ell(d, cx, cy - h_ / 2 + 2, w_ / 2 - 2, 5 * s, (86, 52, 30), (60, 36, 20), 2)


def mug_layer(s=1.0, angle=0.0):
    img, d = new_layer(120, 120)
    draw_mug(d, 60, 60, s)
    if abs(angle) > 1e-3:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=False)
    return img


def paste_layer(base, layer, cx, cy):
    base.alpha_composite(layer, (int(cx * S - layer.width / 2),
                                 int(cy * S - layer.height / 2)))


def paste_owl(base, layer, cx, cy, scale=1.0, angle=0.0, flip=False):
    im = layer
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if abs(scale - 1.0) > 1e-3:
        nw = max(2, int(im.width * scale))
        nh = max(2, int(im.height * scale))
        im = im.resize((nw, nh), Image.LANCZOS)
    if abs(angle) > 1e-3:
        im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
    base.alpha_composite(im, (int(cx * S - im.width / 2),
                              int(cy * S - im.height / 2)))


# --------------------------------------------------------- комикс-эффекты

def burst(d, cx, cy, r, label, size=30, fill=(255, 232, 90),
          edge=(60, 50, 20), tcol=INK, spikes=11, rot=0.0):
    pts = []
    for i in range(spikes * 2):
        a = rot + i * math.pi / spikes
        rr = r if i % 2 == 0 else r * 0.62
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.85))
    poly(d, pts, fill, edge, 4)
    text(d, cx, cy, label, size=size, fill=tcol, anchor="mm")


def bubble(d, cx, cy, label, size=26, tail=(0, 1)):
    f = font(size)
    tw = d.textlength(label, font=f) / S
    w_ = tw / 2 + 22
    h_ = size * 0.9 + 16
    rect(d, cx - w_, cy - h_, cx + w_, cy + h_, WHITE, INK, 3, r=16)
    tx, ty = tail
    poly(d, [(cx + tx * 14 - 10, cy + ty * (h_ - 3)),
             (cx + tx * 14 + 10, cy + ty * (h_ - 3)),
             (cx + tx * 30, cy + ty * (h_ + 26))], WHITE, INK, 3)
    text(d, cx, cy, label, size=size, fill=INK, anchor="mm")


def speed_lines(d, cx, cy, n=9, length=120, spread=110, seed=0, col=(70, 70, 80)):
    rnd = np.random.RandomState(seed)
    for i in range(n):
        y = cy - spread / 2 + spread * (i + rnd.rand() * 0.4) / n
        ln = length * (0.5 + rnd.rand())
        line(d, [(cx, y), (cx - ln, y)], col, 3)


def steam(d, cx, cy, t, n=3, amp=9, height=70, col=(215, 215, 220), alpha=170):
    for i in range(n):
        ph = t * 2.2 + i * 1.5
        pts = []
        for k in range(11):
            u = k / 10
            pts.append((cx + (i - (n - 1) / 2) * 14 + math.sin(ph + u * 5) * amp * u,
                        cy - u * height))
        line(d, pts, col + (alpha,), 4)


def stink(d, cx, cy, t, n=4, col=(150, 200, 110, 150)):
    for i in range(n):
        ph = t * 3.0 + i * 1.1
        pts = []
        for k in range(12):
            u = k / 11
            pts.append((cx + (i - (n - 1) / 2) * 22 + math.sin(ph + u * 6) * 12 * u,
                        cy - u * 110 - (i % 2) * 10))
        line(d, pts, col, 5)


def shake(img, dx, dy):
    if dx or dy:
        return ImageChops.offset(img, int(dx * S), int(dy * S))
    return img


def finish(img):
    return img.convert("RGB").resize((W, H), Image.LANCZOS)


def fade(img, k):
    """k=0 — чёрный кадр, k=1 — как есть."""
    if k >= 0.999:
        return img
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(black, img, max(0.0, k))


# -------------------------------------------------------------- фоны сцен

def room_bg():
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rect(d, 0, 0, W, 372, (243, 228, 205))
    rect(d, 0, 372, W, H, (176, 132, 92))
    rect(d, 0, 360, W, 376, (152, 110, 74))
    for x in range(0, W, 80):                       # доски пола
        line(d, [(x, 376), (x - 60, H)], (158, 116, 78), 2)
    # картина
    rect(d, 90, 90, 250, 210, (250, 246, 236), (120, 92, 60), 6, r=4)
    ell(d, 150, 160, 26, 26, (255, 214, 120))
    poly(d, [(105, 200), (170, 128), (235, 200)], (150, 200, 140), None, 0)
    # окно
    rect(d, 690, 70, 880, 230, (176, 222, 248), (235, 235, 240), 8, r=6)
    line(d, [(785, 70), (785, 230)], (235, 235, 240), 6)
    line(d, [(690, 150), (880, 150)], (235, 235, 240), 6)
    # тумбочка с книжкой
    rect(d, 700, 250, 850, 380, (150, 106, 68), (110, 76, 46), 4, r=6)
    rect(d, 720, 232, 830, 252, (196, 72, 62), (140, 48, 40), 3, r=4)
    text(d, 775, 242, "A B C", size=13, fill=WHITE, anchor="mm")
    return img


def chair(d, cx, base_y, back=True, front=True):
    if back:
        rect(d, cx - 96, base_y - 232, cx + 96, base_y - 40,
             (168, 118, 72), (112, 76, 44), 4, r=14)
        rect(d, cx - 78, base_y - 212, cx + 78, base_y - 60,
             (192, 144, 98), (112, 76, 44), 3, r=10)
        rect(d, cx - 84, base_y, cx - 66, base_y + 84, (140, 96, 56),
             (104, 68, 40), 3, r=4)
        rect(d, cx + 66, base_y, cx + 84, base_y + 84, (140, 96, 56),
             (104, 68, 40), 3, r=4)
    if front:
        rect(d, cx - 100, base_y - 18, cx + 100, base_y + 8, (182, 132, 86),
             (112, 76, 44), 4, r=10)
        rect(d, cx - 92, base_y + 8, cx - 74, base_y + 92, (156, 108, 64),
             (108, 72, 42), 3, r=4)
        rect(d, cx + 74, base_y + 8, cx + 92, base_y + 92, (156, 108, 64),
             (108, 72, 42), 3, r=4)


def corridor_bg(scroll):
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rect(d, 0, 0, W, 372, (232, 236, 242))
    rect(d, 0, 250, W, 372, (196, 208, 222))
    rect(d, 0, 244, W, 254, (150, 164, 182))
    rect(d, 0, 372, W, H, (168, 150, 132))
    rect(d, 0, 366, W, 378, (128, 112, 96))
    period = 340
    off = -(scroll % period)
    for k in range(-1, W // period + 3):
        x = off + k * period
        rect(d, x + 40, 150, x + 160, 372, (192, 160, 118), (140, 112, 78), 4, r=6)
        ell(d, x + 146, 268, 6, 6, (240, 210, 90))
        rect(d, x + 210, 96, x + 300, 176, (250, 246, 238), (150, 126, 92), 5, r=4)
        text(d, x + 255, 136, "¡Hola!", size=20, fill=(120, 140, 190), anchor="mm")
    for x in range(0, W + 60, 60):                  # плитки пола
        line(d, [(x - (scroll % 60), 378), (x - (scroll % 60) - 40, H)],
             (150, 132, 116), 2)
    return img


def wc_door(d, cx, base_y=372, open_amt=0.0):
    rect(d, cx - 78, base_y - 250, cx + 78, base_y, (120, 178, 210),
         (76, 124, 152), 5, r=8)
    rect(d, cx - 58, base_y - 226, cx + 58, base_y - 120, (146, 198, 226),
         (76, 124, 152), 3, r=6)
    rect(d, cx - 30, base_y - 214, cx + 30, base_y - 158, (250, 250, 240),
         (76, 124, 152), 3, r=4)
    text(d, cx, base_y - 186, "WC", size=30, fill=(60, 100, 130), anchor="mm")
    ell(d, cx + 56, base_y - 96, 8, 8, (240, 208, 90), (170, 140, 40), 2)
    if open_amt > 0.01:
        poly(d, [(cx - 78, base_y - 250), (cx - 78 + 156 * open_amt, base_y - 232),
                 (cx - 78 + 156 * open_amt, base_y - 16), (cx - 78, base_y)],
             (24, 24, 30), (20, 20, 24), 3)


def bathroom_bg():
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rect(d, 0, 0, W, 392, (206, 232, 238))
    for x in range(0, W + 1, 60):
        line(d, [(x, 0), (x, 392)], (188, 218, 226), 2)
    for y in range(0, 393, 60):
        line(d, [(0, y), (W, y)], (188, 218, 226), 2)
    rect(d, 0, 392, W, H, (176, 196, 202))
    for x in range(-40, W + 80, 76):
        line(d, [(x, 392), (x - 56, H)], (160, 180, 188), 2)
    line(d, [(0, 392), (W, 392)], (140, 162, 170), 3)
    # дверь слева
    rect(d, 40, 108, 190, 392, (136, 186, 214), (86, 130, 158), 5, r=6)
    rect(d, 60, 128, 170, 250, (158, 204, 228), (86, 130, 158), 3, r=4)
    ell(d, 172, 268, 8, 8, (240, 208, 90), (170, 140, 40), 2)
    # держатель с бумагой
    rect(d, 700, 236, 712, 262, (170, 178, 186), (130, 140, 150), 2, r=3)
    ell(d, 742, 258, 34, 34, (252, 252, 250), (206, 210, 214), 3)
    ell(d, 742, 258, 11, 11, (206, 210, 214), (180, 186, 192), 2)
    poly(d, [(776, 250), (798, 300), (770, 300)], (252, 252, 250),
         (214, 218, 222), 2)
    return img


def toilet(d, cx, base_y, back=False, front=False):
    if back:
        # бачок
        rect(d, cx - 90, base_y - 280, cx + 90, base_y - 146, (250, 250, 248),
             (194, 198, 204), 4, r=12)
        ell(d, cx + 66, base_y - 258, 12, 9, (188, 194, 200), (152, 158, 164), 2)
        line(d, [(cx - 66, base_y - 168), (cx + 66, base_y - 168)],
             (222, 226, 232), 3)
        # чаша и постамент
        poly(d, [(cx - 74, base_y - 152), (cx + 74, base_y - 152),
                 (cx + 48, base_y - 56), (cx - 48, base_y - 56)],
             (246, 248, 250), (194, 198, 204), 4)
        rect(d, cx - 46, base_y - 62, cx + 46, base_y - 4, (238, 240, 244),
             (194, 198, 204), 4, r=10)
        ell(d, cx, base_y, 62, 14, (228, 232, 236), (188, 194, 200), 3)
    if front:
        ell(d, cx, base_y - 146, 80, 28, (252, 252, 250), (194, 198, 204), 4)
        ell(d, cx, base_y - 146, 60, 18, (204, 224, 236), (184, 190, 196), 3)


# ------------------------------------------------------------------ сцены

T1, T2, T3, T4, T5 = 0.0, 5.5, 10.0, 14.0, 22.0
TOTAL = 24.0

ROOM = None
BATH = None


def scene_coffee(u):
    """Совёнок сидит на стуле и пьёт кофе."""
    img = Image.new("RGBA", (W * S, H * S), (255, 255, 255, 255))
    img.alpha_composite(ROOM)
    d = ImageDraw.Draw(img)

    cx, base = 470, 360
    chair(d, cx, base, back=True, front=False)

    sips = [(1.1, 1.9), (3.0, 3.8)]
    lift, drinking = 0.0, False
    for a, b in sips:
        if a <= u <= b:
            drinking = True
            k = (u - a) / (b - a)
            lift = math.sin(k * math.pi) ** 0.6
    breathe = math.sin(u * 2.0) * 2.0

    mug_pos = (lerp(60, 26, lift), lerp(14, -2, lift))
    blink = (u % 2.7) > 2.55
    eyes = "closed_happy" if (drinking and lift > 0.45) or blink else "open"
    beak = "smile" if drinking and lift > 0.45 else "closed"
    px = math.sin(u * 0.8) * 4

    owl = render_owl(eyes=eyes, pupil=(px, 2), beak=beak, feet="sit",
                     arms="hold", mug=mug_pos)
    oy = 262 + breathe
    paste_owl(img, owl, cx, oy, 1.0, math.sin(u * 1.3) * 1.2)

    chair(d, cx, base, back=False, front=True)

    over, do = new_layer()
    steam(do, cx + mug_pos[0], oy + mug_pos[1] - 20, u,
          n=3, amp=8, height=64 - lift * 20)
    img.alpha_composite(over)

    if 2.0 < u < 3.0:
        bubble(d, cx + 190, 200, "Ммм, вкусно!", 26, tail=(-1, 1))
    if 4.0 < u < 5.2:
        bubble(d, cx + 205, 200, "Ещё глоточек…", 24, tail=(-1, 1))

    if u < 3.0:
        k = clamp01(min(u / 0.6, (3.0 - u) / 0.6))
        t_img, td = new_layer()
        text(td, W / 2, 52, "КОФЕ-БРЕЙК", size=44,
             fill=(58, 132, 30, int(255 * k)), anchor="mm",
             stroke=3, stroke_fill=(255, 255, 255, int(235 * k)))
        img.alpha_composite(t_img)

    return img, 0.0, 0.0


def scene_sick(u):
    """Животику плохо."""
    img = Image.new("RGBA", (W * S, H * S), (255, 255, 255, 255))
    img.alpha_composite(ROOM)
    d = ImageDraw.Draw(img)
    cx, base = 470, 360

    rumble = clamp01((u - 0.4) / 1.2)
    sick = clamp01((u - 0.5) / 1.6) * 0.9
    belly = rumble * (0.5 + 0.5 * math.sin(u * 9.0))
    sweat = 0 if u < 1.0 else (1 if u < 1.6 else (2 if u < 2.4 else 3))
    sh = rumble * 3.5 * math.sin(u * 26.0)

    # кружка выскальзывает
    fall_t = 1.5
    has_mug = u < fall_t
    chair(d, cx, base, back=True, front=False)

    jump = 0.0
    if u > 3.6:
        jump = ease_out(clamp01((u - 3.6) / 0.6)) * 46

    if u < 2.6:
        eyes = "wide" if u > 0.6 else "open"
        beak = "flat" if u < 1.4 else "open"
    else:
        eyes = "wide"
        beak = "wide"

    owl = render_owl(eyes=eyes, pupil=(0, -3 if u > 1.0 else 0), beak=beak,
                     sick=sick, belly=belly, sweat=sweat, brows=clamp01(u - 0.8),
                     arms="hold" if has_mug else "clutch", feet="sit",
                     mug=(60, 14) if has_mug else None)
    oy = 262 - jump + math.sin(u * 8) * rumble * 2
    paste_owl(img, owl, cx, oy, 1.0, math.sin(u * 17) * rumble * 3)

    chair(d, cx, base, back=False, front=True)

    # падение кружки
    if fall_t <= u < fall_t + 0.55:
        k = (u - fall_t) / 0.55
        mx = cx + 60 + k * 56
        my = 276 + 300 * k * k
        paste_layer(img, mug_layer(1.0, -k * 150), mx, min(my, 384))
    elif u >= fall_t + 0.55:
        k = clamp01((u - fall_t - 0.55) / 0.4)
        ell(d, cx + 112, 392, 34 + 10 * k, 9 + 3 * k, (110, 74, 42), (78, 50, 28), 2)
        paste_layer(img, mug_layer(1.0, -150), cx + 116, 380)
        if k < 1:
            for i in range(5):
                a = -2.6 + i * 0.5
                ell(d, cx + 112 + math.cos(a) * 40 * k, 388 + math.sin(a) * 26 * k,
                    5, 5, (110, 74, 42))
    if fall_t + 0.5 < u < fall_t + 1.0:
        burst(d, cx + 190, 350, 54, "ДЗЫНЬ!", 24, (255, 240, 140), (120, 90, 20))

    if 0.7 < u < 2.0:
        bubble(d, cx - 230, 210, "гурр-гурррр…", 24, tail=(1, 1))
    if 2.3 < u < 3.3:
        burst(d, cx - 210, 190, 92, "ОЙ-ЁЙ-ЁЙ!", 26, (255, 210, 90),
              (150, 90, 10), 12, rot=0.2)
    if u > 3.3:
        bubble(d, cx - 195, 170, "МНЕ СРОЧНО НАДО!", 24, tail=(1, 1))

    if u > 1.2:
        ov, do = new_layer()
        for i in range(3):
            a = 0.6 + i * 0.5
            r = 26 + 10 * math.sin(u * 8 + i)
            arc(do, cx + 4, 300, r, r * 0.7, 200 + i * 20, 340 - i * 20,
                (90, 150, 60, 150), 4)
        img.alpha_composite(ov)

    return img, sh, sh * 0.4


def scene_run(u):
    """Забег по коридору."""
    prog = clamp01(u / 2.9)
    scroll = 1500 * ease_out(prog)
    img = Image.new("RGBA", (W * S, H * S), (255, 255, 255, 255))
    img.alpha_composite(corridor_bg(scroll))
    d = ImageDraw.Draw(img)

    door_x = 1180 - scroll * 0.413
    if door_x < W + 120:
        wc_door(d, door_x, 372, open_amt=clamp01((u - 3.05) / 0.25)
                if u < 3.35 else max(0.0, 1 - (u - 3.35) / 0.2))

    ph = u * 22
    ox = 360 + (door_x - 150 - 360) * ease_in_out(clamp01((u - 2.75) / 0.5))
    oy = 250 - abs(math.sin(ph)) * 16
    gone = u > 3.28

    if not gone:
        ov, do = new_layer()
        speed_lines(do, ox - 60, oy, 10, 150, 150, seed=int(u * 24) % 7,
                    col=(90, 100, 120, 190))
        img.alpha_composite(ov)
        owl = render_owl(eyes="wide", pupil=(9, -2), beak="wide", sick=0.65,
                         sweat=3, brows=1.0, arms="run", feet="run", phase=ph,
                         belly=0.3)
        paste_owl(img, owl, ox, oy, 1.0, -12 + math.sin(ph) * 3)
        for i in range(3):                       # пыль из-под лап
            k = ((u * 3 + i * 0.33) % 1.0)
            ell(d, ox - 40 - k * 90, 352 - k * 10, 12 + k * 18, 9 + k * 12,
                (222, 218, 210), (196, 192, 186), 2)

    if 0.5 < u < 1.6:
        bubble(d, 430, 120, "ПРОПУСТИТЕ!!!", 26, tail=(-1, 1))
    if 3.3 < u < 3.9:
        burst(d, door_x - 190, 150, 86, "ХЛОП!", 30, (255, 226, 110),
              (140, 100, 20), 10, rot=0.3)

    sh = 2.4 * math.sin(u * 30) if not gone else 6 * math.exp(-(u - 3.3) * 9)
    return img, sh * 0.4, sh


def scene_toilet(u):
    """Сцена облегчения — комиксовая, без подробностей."""
    img = Image.new("RGBA", (W * S, H * S), (255, 255, 255, 255))
    img.alpha_composite(BATH)
    d = ImageDraw.Draw(img)
    cx, base = 470, 392

    toilet(d, cx, base, back=True)

    strain = 1.0 if 0.8 < u < 5.0 else 0.0
    pushes = [1.05, 2.0, 2.9, 3.7, 4.5]
    kick = 0.0
    for p in pushes:
        if 0 <= u - p < 0.45:
            kick = max(kick, (1 - (u - p) / 0.45))

    if u < 0.7:
        eyes, beak, sweat = "wide", "open", 2
    elif u < 5.0:
        eyes = "closed_squeeze"
        beak = "wide" if kick > 0.2 else "open"
        sweat = 3
    elif u < 6.4:
        eyes, beak, sweat = "relief", "smile", 0
    else:
        eyes, beak, sweat = "closed_happy", "smile", 0

    sick = 0.75 if u < 5.0 else max(0.0, 0.75 - (u - 5.0) * 0.9)
    belly = (0.5 * kick) if u < 5.0 else -0.0

    standing = u > 6.9
    if standing:
        k = ease_out(clamp01((u - 6.9) / 0.5))
        ocx = cx + 172 * k
        ocy = lerp(178, 292, k)
        owl = render_owl(eyes="closed_happy", beak="smile", sick=0.0,
                         arms="up" if u > 7.3 else "down", feet="stand")
        toilet(d, cx, base, front=True)
        paste_owl(img, owl, ocx, ocy, 1.0, 0)
    else:
        owl = render_owl(eyes=eyes, pupil=(0, 2), beak=beak, sick=sick,
                         belly=belly, sweat=sweat, brows=strain,
                         arms="clutch" if u < 5.0 else "down",
                         feet="hidden", strain=strain * (0.5 + 0.5 * kick))
        paste_owl(img, owl, cx, 178 - kick * 4, 1.0, math.sin(u * 30) * strain * 2.5)
        toilet(d, cx, base, front=True)
        for sgn in (-1, 1):                       # лапки свисают
            wob = math.sin(u * 26 + sgn) * 4 * strain
            line(d, [(cx + sgn * 34, 256), (cx + sgn * 46 + wob, 306)],
                 mixc(GREEN_D, (86, 112, 66), sick), 10)
            ell(d, cx + sgn * 52 + wob, 312, 18, 10, ORANGE, ORANGE_D, 3)

    # напряжённые линии вокруг
    if 0.8 < u < 5.0:
        ov, do = new_layer()
        for i in range(10):
            a = i * math.pi / 5 + u
            r0 = 106 + kick * 16
            do_x, do_y = cx + math.cos(a) * r0, 172 + math.sin(a) * r0 * 0.8
            line(do, [(do_x, do_y),
                      (cx + math.cos(a) * (r0 + 26 + kick * 20),
                       172 + math.sin(a) * (r0 + 26 + kick * 20) * 0.8)],
                 (60, 60, 70, 170), 4)
        img.alpha_composite(ov)

    labels = ["ПФФФ!", "БУЛЬ-БУЛЬ!", "БДЫЩ!", "ПЛЮХ!", "ПЛЮХ-ПЛЮХ-ПЛЮХ!"]
    for i, p in enumerate(pushes):
        if 0 <= u - p < 0.7:
            k = (u - p) / 0.7
            side = -1 if i % 2 == 0 else 1
            burst(d, cx + side * 250, 130 + (i % 3) * 42,
                  70 + 26 * math.sin(k * math.pi), labels[i],
                  22 + int(6 * math.sin(k * math.pi)),
                  (255, 232, 96), (140, 100, 16), 11, rot=i * 0.4)

    if 2.0 < u < 6.0:                              # «ароматные» завитушки
        ov, do = new_layer()
        stink(do, cx - 150, 250, u, n=2)
        stink(do, cx + 150, 250, u + 0.7, n=2)
        img.alpha_composite(ov)

    if 5.2 < u < 6.6:
        bubble(d, cx + 250, 132, "Уфф… полегчало!", 24, tail=(-1, 1))
        for i in range(6):                         # искорки облегчения
            a = i * 1.05 + u
            sx, sy = cx + math.cos(a) * 150, 150 + math.sin(a * 1.3) * 50
            poly(d, [(sx, sy - 12), (sx + 4, sy - 4), (sx + 12, sy),
                     (sx + 4, sy + 4), (sx, sy + 12), (sx - 4, sy + 4),
                     (sx - 12, sy), (sx - 4, sy - 4)], (255, 236, 120),
                 (230, 190, 40), 2)

    if 6.4 < u < 7.0:
        burst(d, cx - 130, 150, 62, "СМЫВ!", 22, (170, 220, 250), (60, 120, 170))
    if u > 7.4:
        bubble(d, 640, 468, "Вывод: кофе — маленькими глоточками!", 24,
               tail=(0, -1))

    sh = 0.0
    if 0.8 < u < 5.0:
        sh = 5.5 * kick * math.sin(u * 40) + 1.2 * math.sin(u * 22) * strain
    return img, sh * 0.5, sh


def scene_end(u):
    img = Image.new("RGBA", (W * S, H * S), (86, 176, 46, 255))
    d = ImageDraw.Draw(img)
    for i in range(14):
        ell(d, (i * 97) % W, (i * 61) % H, 30, 30, (98, 190, 56))
    owl = render_owl(eyes="closed_happy", beak="smile",
                     arms="up" if (u % 0.8) < 0.4 else "down", feet="stand")
    paste_owl(img, owl, W / 2, 300 - abs(math.sin(u * 3)) * 10, 0.95, 0)
    text(d, W / 2, 108, "КОНЕЦ", size=64, fill=WHITE, anchor="mm",
         stroke=4, stroke_fill=(50, 120, 26))
    text(d, W / 2, 468, "Пейте кофе с умом", size=26, fill=WHITE, anchor="mm")
    return img, 0.0, 0.0


def frame(t):
    if t < T2:
        img, dx, dy = scene_coffee(t - T1)
    elif t < T3:
        img, dx, dy = scene_sick(t - T2)
    elif t < T4:
        img, dx, dy = scene_run(t - T3)
    elif t < T5:
        img, dx, dy = scene_toilet(t - T4)
    else:
        img, dx, dy = scene_end(t - T5)

    img = shake(img, dx, dy)
    out = finish(img)

    k = 1.0
    k = min(k, clamp01(t / 0.5))                    # появление из черноты
    k = min(k, clamp01((TOTAL - t) / 0.8))          # уход в черноту
    for cut in (T3, T4, T5):                        # склейки между сценами
        k = min(k, clamp01(abs(t - cut) / 0.18))
    return fade(out, k)


# -------------------------------------------------------------------- звук

SR = 44100


class Audio:
    def __init__(self, seconds):
        self.buf = np.zeros(int(SR * seconds) + SR, dtype=np.float64)
        self.rng = np.random.RandomState(7)

    def _add(self, t0, sig):
        i = int(t0 * SR)
        if i < 0:
            sig = sig[-i:]
            i = 0
        j = min(len(self.buf), i + len(sig))
        self.buf[i:j] += sig[:j - i]

    def _env(self, n, a=0.01, d=0.2, s=0.7, r=0.2):
        t = np.linspace(0, 1, n)
        return np.clip(np.minimum(t / max(a, 1e-4), 1.0), 0, 1) * \
            np.exp(-np.linspace(0, 1, n) * 0) * (1 - t) ** 0.0 * \
            np.clip((1 - t) / max(r, 1e-4), 0, 1) ** 0.6 * s + \
            0 * d

    def tone(self, t0, dur, f0, f1=None, amp=0.2, wave="sine", vib=0.0,
             vibf=6.0, decay=2.0):
        n = int(dur * SR)
        t = np.arange(n) / SR
        f1 = f0 if f1 is None else f1
        f = np.linspace(f0, f1, n) * (1 + vib * np.sin(2 * np.pi * vibf * t))
        ph = 2 * np.pi * np.cumsum(f) / SR
        if wave == "saw":
            y = 2 * ((ph / (2 * np.pi)) % 1.0) - 1
        elif wave == "square":
            y = np.sign(np.sin(ph))
        else:
            y = np.sin(ph)
        env = np.exp(-t * decay) * np.clip(t / 0.005, 0, 1)
        self._add(t0, y * env * amp)

    def noise(self, t0, dur, amp=0.2, lp=0.15, hp=0.0, shape=None, decay=1.5):
        n = int(dur * SR)
        x = self.rng.randn(n)
        y = np.zeros(n)
        acc = 0.0
        for_a = lp
        # однополюсный ФНЧ
        b = np.empty(n)
        for i in range(n):
            acc += for_a * (x[i] - acc)
            b[i] = acc
        y = b
        if hp > 0:
            acc2 = 0.0
            c = np.empty(n)
            for i in range(n):
                acc2 += hp * (y[i] - acc2)
                c[i] = y[i] - acc2
            y = c
        t = np.arange(n) / SR
        env = np.exp(-t * decay) * np.clip(t / 0.01, 0, 1)
        if shape is not None:
            env = env * shape(t / max(dur, 1e-6))
        self._add(t0, y * env * amp)

    def thump(self, t0, amp=0.5, f=70):
        self.tone(t0, 0.35, f * 1.6, f * 0.6, amp, decay=12)
        self.noise(t0, 0.08, amp * 0.25, lp=0.4, decay=30)

    def sip(self, t0):
        self.noise(t0, 0.55, 0.11, lp=0.05, hp=0.02, decay=1.2,
                   shape=lambda u: np.sin(np.pi * u) ** 0.7)
        self.tone(t0 + 0.45, 0.18, 240, 120, 0.14, decay=14)   # глоток
        self.tone(t0 + 0.62, 0.16, 210, 100, 0.11, decay=14)

    def rumble(self, t0, dur, amp=0.35):
        n = int(dur * SR)
        t = np.arange(n) / SR
        y = (np.sin(2 * np.pi * 48 * t + 3 * np.sin(2 * np.pi * 1.7 * t)) * 0.6 +
             np.sin(2 * np.pi * 31 * t + 2 * np.sin(2 * np.pi * 0.9 * t)) * 0.4)
        mod = 0.45 + 0.55 * np.abs(np.sin(2 * np.pi * 1.3 * t))
        env = np.clip(t / 0.3, 0, 1) * np.clip((dur - t) / 0.4, 0, 1)
        self._add(t0, y * mod * env * amp)

    def blurp(self, t0, dur=0.5, amp=0.34, f=95):
        """Комичный «пффф» — пила с сильным вибрато."""
        self.tone(t0, dur, f * 1.35, f * 0.7, amp, wave="saw",
                  vib=0.22, vibf=17, decay=3.2)
        self.noise(t0, dur * 0.8, amp * 0.20, lp=0.10, decay=4)

    def plop(self, t0, amp=0.4):
        self.tone(t0, 0.22, 520, 90, amp, decay=22)
        self.noise(t0 + 0.02, 0.18, amp * 0.35, lp=0.25, decay=18)

    def flush(self, t0, dur=2.4, amp=0.3):
        n = int(dur * SR)
        t = np.arange(n) / SR
        x = self.rng.randn(n)
        acc = 0.0
        y = np.empty(n)
        for i in range(n):
            a = 0.05 + 0.25 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.8 * (i / SR)))
            acc += a * (x[i] - acc)
            y[i] = acc
        env = np.clip(t / 0.25, 0, 1) * np.clip((dur - t) / 1.0, 0, 1)
        self._add(t0, y * env * amp)
        self.tone(t0, dur * 0.7, 180, 90, amp * 0.25, decay=1.4)

    def save(self, path):
        y = self.buf
        peak = np.max(np.abs(y)) or 1.0
        y = np.tanh(y / max(peak, 0.9) * 1.4) * 0.85
        pcm = (y * 32767).astype("<i2")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())


def build_audio(path):
    a = Audio(TOTAL)
    # сцена 1 — кофе
    a.sip(T1 + 1.15)
    a.sip(T1 + 3.05)
    # сцена 2 — в животе неспокойно
    a.rumble(T2 + 0.4, 3.4, 0.42)
    a.tone(T2 + 2.05, 0.5, 700, 300, 0.16, decay=8)      # звон кружки
    a.tone(T2 + 2.10, 0.4, 1250, 640, 0.10, decay=10)
    a.noise(T2 + 2.05, 0.35, 0.16, lp=0.5, decay=9)
    a.tone(T2 + 3.6, 0.35, 300, 800, 0.15, decay=6)      # подскок
    # сцена 3 — бег
    for i in range(14):
        a.thump(T3 + 0.15 + i * 0.23, 0.28, 90 + (i % 2) * 25)
    a.noise(T3 + 3.32, 0.5, 0.4, lp=0.35, decay=9)       # хлопок двери
    a.thump(T3 + 3.32, 0.5, 55)
    # сцена 4 — облегчение
    for i, p in enumerate([1.05, 2.0, 2.9, 3.7, 4.5]):
        a.blurp(T4 + p, 0.42 + 0.12 * (i % 2), 0.32, 100 - i * 8)
        a.plop(T4 + p + 0.30, 0.34)
        if i >= 2:
            a.plop(T4 + p + 0.46, 0.26)
    a.rumble(T4 + 0.8, 4.2, 0.18)
    a.noise(T4 + 5.15, 1.1, 0.10, lp=0.06, decay=1.1,
            shape=lambda u: np.sin(np.pi * u) ** 0.5)     # выдох облегчения
    a.flush(T4 + 6.4, 2.3, 0.32)
    # финал
    a.tone(T5 + 0.1, 0.22, 523, 523, 0.18, decay=6)
    a.tone(T5 + 0.32, 0.22, 659, 659, 0.18, decay=6)
    a.tone(T5 + 0.54, 0.5, 784, 784, 0.20, decay=4)
    a.save(path)
    return path


# -------------------------------------------------------------------- main

def main():
    global ROOM, BATH
    out = sys.argv[1] if len(sys.argv) > 1 else "duolingo_coffee.mp4"
    tmp = os.environ.get("VIDEO_TMP", "/tmp")
    wav = os.path.join(tmp, "cartoon_audio.wav")

    print("Синтезирую звук…", flush=True)
    build_audio(wav)

    ROOM = room_bg()
    BATH = bathroom_bg()

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-",
           "-i", wav,
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-shortest", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    total = int(TOTAL * FPS)
    for i in range(total):
        img = frame(i / FPS)
        proc.stdin.write(img.tobytes())
        if i % 24 == 0:
            print(f"  кадр {i}/{total}", flush=True)
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg завершился с кодом {rc}")
    print(f"Готово: {out}")


if __name__ == "__main__":
    main()
