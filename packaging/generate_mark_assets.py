# Copyright (c) 2026 Ivan Soprun
"""Generate the Agent SI mark raster assets from src/agent_si/assets/mark.svg.

Stdlib only (struct + zlib): no Pillow, no network, no extra tool.
The SVG is the vector source of truth; this script mirrors its geometry
(outer rounded square #161b22 + #30363d border, inner square #0d1117,
blue #2f81f7 "SI" strokes with round caps, small blue bar) in a tiny
software rasterizer with 2x supersampling, then writes:

  src/agent_si/assets/icon.ico   (PNG-compressed entries 16/24/32/48/64/128/256)
  src/agent_si/assets/mark_256.png

16 px stays readable: strokes are chunky with round caps and the bar is
kept; verify with the upscaled preview this script can also emit
(see --preview out.png, nearest-neighbour x8 of the 16 px entry).
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

# "SI" strokes in 256-space (mirrors mark.svg path data).
_S_UPPER = ((138.0, 104.0), (122.0, 104.0), (112.0, 111.0), (112.0, 121.0))
_S_MID = ((112.0, 121.0), (112.0, 137.0), (144.0, 134.0), (144.0, 151.0))
_S_LOWER = ((144.0, 151.0), (144.0, 161.0), (134.0, 168.0), (120.0, 168.0))
_S_TAIL = ((120.0, 168.0), (111.0, 168.0), (103.0, 165.0), (98.0, 160.0))
_I_SEG = ((162.0, 104.0), (162.0, 168.0))
_STROKE_W = 17.0
_BAR = (112.0, 184.0, 48.0, 11.0, 5.5)  # x, y, w, h, r


def _cubic(p0, c1, c2, p1, n=16):
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


def _render(size, ss=2):
    w = size * ss
    k = 256.0 / size  # target-pixel space -> 256 design space
    s_poly = _si_polyline()
    segs = [(s_poly[i], s_poly[i + 1]) for i in range(len(s_poly) - 1)]
    segs.append(_I_SEG)
    rad = _STROKE_W / 2.0
    bx, by, bw, bh, br = _BAR

    def pixel(x, y):
        px = (x + 0.5) / ss * k
        py = (y + 0.5) / ss * k
        # Outside the outer tile: transparent.
        if not _in_rounded_rect(px, py, 8, 8, 240, 240, 54):
            return (0, 0, 0, 0)
        col = OUTER_FILL
        # Border ring: within 2px of the outer edge.
        if not _in_rounded_rect(px, py, 12, 12, 232, 232, 50):
            col = BORDER
        if _in_rounded_rect(px, py, 52, 52, 152, 152, 34):
            col = INNER_FILL
        hit = _in_rounded_rect(px, py, bx, by, bw, bh, br)
        if not hit:
            for (ax, ay), (cx, cy) in segs:
                if _dist_seg(px, py, ax, ay, cx, cy) <= rad:
                    hit = True
                    break
        if hit:
            col = BLUE
        return col

    # Supersampled render then box average.
    import array as _arr

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
        # Un-premultiply lightly: colours are opaque except edges.
        a = (acc[i * 4 + 3] + n // 2) // n
        if a == 0:
            out[i * 4:i * 4 + 4] = b"\x00\x00\x00\x00"
            continue
        for k in range(3):
            v = (acc[i * 4 + k] + n // 2) // n
            out[i * 4 + k] = min(255, max(0, v))
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
    # entries: list of (size, png_bytes); PNG-compressed ICO (Vista+).
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


def build(preview_path=None):
    os.makedirs(ASSETS, exist_ok=True)
    entries = []
    png256 = b""
    for size in SIZES:
        rgba = _render(size)
        png = _png(rgba, size)
        entries.append((size, png))
        if size == 256:
            png256 = png
    with open(os.path.join(ASSETS, "icon.ico"), "wb") as handle:
        handle.write(_ico(entries))
    with open(os.path.join(ASSETS, "mark_256.png"), "wb") as handle:
        handle.write(png256)
    if preview_path:
        # Nearest-neighbour x8 upscale of the 16 px entry for eye check.
        rgba16 = _render(16)
        big = bytearray(128 * 128 * 4)
        for y in range(128):
            for x in range(128):
                src = ((y // 8) * 16 + (x // 8)) * 4
                dst = (y * 128 + x) * 4
                big[dst:dst + 4] = rgba16[src:src + 4]
        with open(preview_path, "wb") as handle:
            handle.write(_png(bytes(big), 128))
    return entries


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default=None)
    args = ap.parse_args(argv)
    entries = build(preview_path=args.preview)
    print("wrote icon.ico sizes=%s" % sorted(s for s, _ in entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
