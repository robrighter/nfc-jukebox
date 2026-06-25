#!/usr/bin/env python3
"""Generate app icons for NFC Jukebox.

A vinyl record on the project's 1970s hi-fi palette. Renders at 4x and
downsamples for crisp anti-aliased edges. Outputs favicons, an apple-touch
icon, and PWA (incl. maskable) icons into nfc_jukebox/static/.

Run:  python scripts/make_icons.py
Requires Pillow.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "..", "nfc_jukebox", "static")
ICONS = os.path.join(STATIC, "icons")

SS = 4  # supersample factor

# palette
WOOD_TOP = (58, 44, 30)
WOOD_BOT = (26, 18, 12)
DISC = (18, 13, 9)
GROOVE = (46, 36, 24)
AMBER_TOP = (255, 177, 82)
AMBER_BOT = (255, 138, 30)
HOLE = (20, 14, 9)


def _vgrad(w: int, h: int, top, bot) -> Image.Image:
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = c
    return g


def _radial_gradient(d: int, inner, outer) -> Image.Image:
    g = Image.new("RGB", (d, d))
    px = g.load()
    c = (d - 1) / 2
    maxr = (d / 2) ** 0.5 * (d / 2) ** 0  # placeholder
    maxr = ((c) ** 2 + (c) ** 2) ** 0.5
    for y in range(d):
        for x in range(d):
            r = ((x - c) ** 2 + (y - c) ** 2) ** 0.5 / maxr
            r = min(1.0, r)
            px[x, y] = tuple(int(inner[i] + (outer[i] - inner[i]) * r) for i in range(3))
    return g


def draw_icon(size: int, full_bleed: bool, disc_frac: float) -> Image.Image:
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ---- background ----
    bg = _vgrad(S, S, WOOD_TOP, WOOD_BOT).convert("RGBA")
    if full_bleed:
        img.paste(bg, (0, 0))
    else:
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255
        )
        img.paste(bg, (0, 0), mask)

    # ---- vinyl disc ----
    cx = cy = S / 2
    R = S * disc_frac / 2
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=DISC)

    # grooves (concentric rings)
    rings = 7
    for i in range(rings):
        rr = R * (0.50 + 0.065 * i)
        if rr >= R:
            break
        w = max(1, int(S * 0.004))
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=GROOVE, width=w)

    # specular sheen: soft translucent band across the disc
    sheen = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    sd.ellipse(
        [cx - R * 1.05, cy - R * 1.7, cx + R * 0.2, cy + R * 0.1],
        fill=(255, 255, 255, 26),
    )
    discmask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(discmask).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
    img.paste(sheen, (0, 0), Image.composite(sheen.split()[3], Image.new("L", (S, S), 0), discmask))

    # ---- label (amber) ----
    lr = R * 0.40
    label = _radial_gradient(int(lr * 2) + 2, AMBER_TOP, AMBER_BOT).convert("RGBA")
    lmask = Image.new("L", label.size, 0)
    ImageDraw.Draw(lmask).ellipse([0, 0, label.size[0] - 1, label.size[1] - 1], fill=255)
    img.paste(label, (int(cx - lr), int(cy - lr)), lmask)
    # label edge ring
    d.ellipse([cx - lr, cy - lr, cx + lr, cy + lr], outline=(120, 70, 20), width=max(1, int(S * 0.004)))

    # NFC "signal" arcs on the label (three concentric arcs)
    for i in range(3):
        ar = lr * (0.30 + 0.22 * i)
        d.arc(
            [cx - ar, cy - ar, cx + ar, cy + ar],
            start=-50, end=50,
            fill=(60, 35, 12), width=max(1, int(S * 0.006)),
        )

    # ---- center hole ----
    hr = R * 0.05
    d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=HOLE)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    os.makedirs(ICONS, exist_ok=True)

    # PWA icons
    draw_icon(512, full_bleed=False, disc_frac=0.86).save(os.path.join(ICONS, "icon-512.png"))
    draw_icon(192, full_bleed=False, disc_frac=0.86).save(os.path.join(ICONS, "icon-192.png"))
    # maskable: full-bleed bg + extra safe padding around the disc
    draw_icon(512, full_bleed=True, disc_frac=0.64).save(os.path.join(ICONS, "icon-maskable-512.png"))
    # apple touch: opaque, slight padding
    draw_icon(180, full_bleed=True, disc_frac=0.80).save(os.path.join(ICONS, "apple-touch-icon.png"))
    # favicons
    draw_icon(32, full_bleed=False, disc_frac=0.92).save(os.path.join(ICONS, "favicon-32.png"))
    draw_icon(16, full_bleed=False, disc_frac=0.94).save(os.path.join(ICONS, "favicon-16.png"))
    # multi-size .ico at static root
    ico = draw_icon(48, full_bleed=False, disc_frac=0.92)
    ico.save(os.path.join(STATIC, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])

    print("icons written to", os.path.normpath(ICONS))


if __name__ == "__main__":
    main()
