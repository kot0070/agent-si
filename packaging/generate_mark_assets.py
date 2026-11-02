# Copyright (c) 2026 Ivan Soprun
"""Generate the Agent SI mark raster assets from src/agent_si/assets/mark.svg.

Stdlib only (struct + zlib): no Pillow, no network, no extra tool.
The SVG is the vector source of truth; this script mirrors its geometry
(outer rounded square #161b22 + #30363d border, inner square #0d1117,
heavy blue #2f81f7 "SI" strokes with round caps at ~47% of icon height,
small blue bar) in a tiny software rasterizer with 2x supersampling.

Sizes 16/24/32 get their own simplified, pixel-aligned drawing (no inner
square, no bar: just bold SI on the dark rounded square) so the letters
stay readable at real size. Emits:

  src/agent_si/assets/icon.ico   (PNG-compressed entries 16/24/32/48/64/128/256)
  src/agent_si/assets/mark_256.png
  --preview out.png              (dark + light strips, every size at REAL pixels)
"""
from __future__ import annotations

import argparse
import os
import struct
import zlib

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, ".."))
ASSETS = os.path.join(ROOT, "src", "agent_si", "assets")

OUTER_FILL = (22, 27, 34, 255)  # #161b22
BORDER = (48, 54, 61, 255)  # #30363d
INNER_FILL = (13, 17, 23, 255)  # #0d1117
BLUE = (47, 129, 247, 255)  # #2f81f7

SIZES = (16, 24, 32, 48, 64, 128, 256)
SMALL_SIZES = (16, 24, 32)

# "SI" strokes in 256-space (mirrors mark.svg path data).
_S_UPPER = ((148.0, 62.0), (120.0, 62.0), (98.0, 76.0), (98.0, 102.0))
_S_MID = ((98.0, 102.0), (98.0, 130.0), (148.0, 120.0), (148.0, 148.0))
_S_LOWER = ((148.0, 148.0), (148.0, 170.0), (128.0, 182.0), (102.0, 182.0))
_S_TAIL = ((102.0, 182.0), (92.0, 182.0), (84.0, 178.0), (78.0, 172.0))
_I_SEG = ((178.0, 62.0), (178.0, 182.0))
_STROKE_W = 24.0
_BAR = (104.0, 196.0, 48.0, 10.0, 5.0)  # x, y, w, h, r
_INNER = (46.0, 46.0, 164.0, 164.0, 38.0)  # x, y, w, h, r


def _cubic(p0, c1, c2, p1, n=20):
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1.0 - t
        x = (mt ** 3 * p0[0] + 3 * mt * mt * t * c1[0]
             + 3 * mt * t * t * c2[0] + t ** 3 * p1[0])
        y = (mt ** 3 * p0[1] + 3 * mt * mt * t * c1[1]
             + 3 * mt * t * t * c2[1] + t ** 3 * p1[1])
        pts.append((x, y))
    return pts


def _si_polyline():
    pts = []
    for seg in (_S_UPPER, _S_MID, _S_LOWER, _S_TAIL):
        pts.extend(_cubic(*seg))
    return pts

_SI_SEGS_256 = None


def _si_segs():
    global _SI_SEGS_256
    if _SI_SEGS_256 is None:
        poly = _si_polyline()
        _SI_SEGS_256 = ([(poly[i], poly[i + 1]) for i in range(len(poly) - 1)]
                        + [_I_SEG])
    return _SI_SEGS_256


def _in_rounded_rect(px, py, x, y, w, h, r):
    cx = min(max(px, x + r), x + w - r)
    cy = min(max(py, y + r), y + h - r)
    if px >= x + r and px <= x + w - r:
        return y <= py <= y + h
    if py >= y + r and py <= y + h - r:
        return x <= px <= x + w
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def _dist_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    t = ((px - ax) * dx + (py - ay) * dy) / denom if denom else 0.0
    t = min(max(t, 0.0), 1.0)
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def _render(size, ss=2, simple=False):
    """Render one size. simple=True: pixel-aligned tiny drawing."""
    import array as _arr

    k = 256.0 / size  # target-pixel space -> 256 design space
    if simple:
        # Own simple drawing: snapped SI, no inner square, no bar.
        ksmall = size / 256.0
        segs = [((round(ax * ksmall), round(ay * ksmall)),
                 (round(bx * ksmall), round(by * ksmall)))
                for (ax, ay), (bx, by) in _si_segs()]
        rad = max(2, round(size * 30 / 256)) / 2.0
        bw = 1 if size <= 24 else 2
        rr = round(size * 54 / 256)
    else:
        segs = _si_segs()
        rad = _STROKE_W / 2.0
    bx, by, bw_, bh, br = _BAR
    ix, iy, iw, ih, ir = _INNER

    def pixel(x, y):
        if simple:
            px = (x + 0.5) / ss
            py = (y + 0.5) / ss
            if not _in_rounded_rect(px, py, 0, 0, size, size, rr):
                return (0, 0, 0, 0)
            col = OUTER_FILL
            if not _in_rounded_rect(px, py, bw, bw,
                                    size - 2 * bw, size - 2 * bw,
                                    max(1, rr - bw)):
                col = BORDER
            for (ax, ay), (cx, cy) in segs:
                if _dist_seg(px, py, ax, ay, cx, cy) <= rad:
                    col = BLUE
                    break
            return col
        px = (x + 0.5) / ss * k
        py = (y + 0.5) / ss * k
        if not _in_rounded_rect(px, py, 8, 8, 240, 240, 54):
            return (0, 0, 0, 0)
        col = OUTER_FILL
        if not _in_rounded_rect(px, py, 12, 12, 232, 232, 50):
            col = BORDER
        if _in_rounded_rect(px, py, ix, iy, iw, ih, ir):
            col = INNER_FILL
        hit = _in_rounded_rect(px, py, bx, by, bw_, bh, br)
        if not hit:
            for (ax, ay), (cx, cy) in segs:
                if _dist_seg(px, py, ax, ay, cx, cy) <= rad:
                    hit = True
                    break
        if hit:
            col = BLUE
        return col

    w = size * ss
    acc = _arr.array("I", [0]) * (size * size * 4)
    for y in range(w):
        for x in range(w):
            r, g, b, a = pixel(x, y)
            tx, ty = x // ss, y // ss
            o = (ty * size + tx) * 4
            acc[o] += r
            acc[o + 1] += g
            acc[o + 2] += b
            acc[o + 3] += a
    n = ss * ss
    out = bytearray(size * size * 4)
    for i in range(size * size):
        a = (acc[i * 4 + 3] + n // 2) // n
        if a == 0:
            out[i * 4:i * 4 + 4] = b"\x00\x00\x00\x00"
            continue
        for kk in range(3):
            v = (acc[i * 4 + kk] + n // 2) // n
            out[i * 4 + kk] = min(255, max(0, v))
        out[i * 4 + 3] = min(255, max(0, a))
    return bytes(out)


def _png(rgba, size):
    raw = b"".join(
        b"\x00" + rgba[y * size * 4:(y + 1) * size * 4]
        for y in range(size)
    )
    comp = zlib.compress(raw, 9)

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def _ico(entries):
    head = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    body = b""
    blobs = b""
    for size, png in entries:
        w = 0 if size >= 256 else size
        body += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32,
                            len(png), offset + len(blobs))
        blobs += png
    return head + body + blobs


def _paste(canvas, cw, rgba, size, ox, oy):
    for y in range(size):
        for x in range(size):
            o = (y * size + x) * 4
            sa = rgba[o + 3] / 255.0
            if sa == 0:
                continue
            d = ((oy + y) * cw + (ox + x)) * 4
            for kk in range(3):
                canvas[d + kk] = int(rgba[o + kk] * sa
                                     + canvas[d + kk] * (1 - sa))
            canvas[d + 3] = 255


def _strip_preview(path):
    """One picture, dark strip + light strip, every size at REAL pixels."""
    order = (256, 64, 48, 32, 24, 16)
    pad, gap = 16, 16
    strip_w = pad * 2 + sum(order) + gap * (len(order) - 1)
    strip_h = pad * 2 + 256
    renders = {s: _render(s, simple=(s in SMALL_SIZES)) for s in order}
    canvas = bytearray(strip_w * strip_h * 2 * 4)
    for row, bg in enumerate(((13, 17, 23), (255, 255, 255))):
        base = row * strip_w * strip_h * 4
        for i in range(strip_w * strip_h):
            canvas[base + i * 4:base + i * 4 + 4] = bytes(
                [bg[0], bg[1], bg[2], 255])
        x = pad
        for s in order:
            y = pad + (256 - s) // 2
            row_arr = bytearray(canvas[base:base + strip_w * strip_h * 4])
            _paste(row_arr, strip_w, renders[s], s, x, y)
            canvas[base:base + strip_w * strip_h * 4] = bytes(row_arr)
            x += s + gap
    with open(path, "wb") as handle:
        handle.write(_png_strip(bytes(canvas), strip_w, strip_h * 2))
    return path


def _png_strip(raw_rgba, w, h_total):
    raw = b"".join(
        b"\x00" + raw_rgba[y * w * 4:(y + 1) * w * 4]
        for y in range(h_total)
    )
    comp = zlib.compress(raw, 9)

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h_total, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def build(preview_path=None):
    os.makedirs(ASSETS, exist_ok=True)
    entries = []
    png256 = b""
    for size in SIZES:
        rgba = _render(size, simple=(size in SMALL_SIZES))
        png = _png(rgba, size)
        entries.append((size, png))
        if size == 256:
            png256 = png
    with open(os.path.join(ASSETS, "icon.ico"), "wb") as handle:
        handle.write(_ico(entries))
    with open(os.path.join(ASSETS, "mark_256.png"), "wb") as handle:
        handle.write(png256)
    if preview_path:
        _strip_preview(preview_path)
    return entries


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default=None)
    args = ap.parse_args(argv)
    entries = build(preview_path=args.preview)
    print(f"wrote icon.ico sizes={sorted(s for s, _ in entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
