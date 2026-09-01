"""Regenerate packaging/lapus.ico from the frontend's SVG mark.

Run when the mark changes:  python packaging/make_icon.py
Needs Pillow (`pip install pillow`) and cairosvg, neither of which is a
runtime dependency -- the .ico is checked in so a normal build needs neither.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ICON = REPO_ROOT / "packaging" / "lapus.ico"

# The mark, drawn directly rather than rasterised from the SVG, so this script
# has no dependencies at all: layered sheets with the top one lifted, the
# overlay model the app is built around.
ACCENT = (29, 78, 216)
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _draw(size: int) -> bytes:
    """One RGBA frame, as raw pixels."""
    pixels = bytearray()
    radius = size * 0.2
    bars = [
        (0.625, 0.719, 0.219, 0.656, 0.45),   # back sheet
        (0.453, 0.547, 0.219, 0.656, 0.70),   # middle sheet
        (0.250, 0.344, 0.281, 0.719, 1.00),   # lifted top sheet
    ]
    for y in range(size):
        for x in range(size):
            fx, fy = (x + 0.5) / size, (y + 0.5) / size
            # Rounded-square background.
            cx = min(x + 0.5, size - x - 0.5)
            cy = min(y + 0.5, size - y - 0.5)
            inside = True
            if cx < radius and cy < radius:
                inside = ((radius - cx) ** 2 + (radius - cy) ** 2) <= radius ** 2
            if not inside:
                pixels += bytes((0, 0, 0, 0))
                continue
            r, g, b = ACCENT
            for top, bottom, left, right, alpha in bars:
                if top <= fy < bottom and left <= fx < right:
                    r = round(r + (255 - r) * alpha)
                    g = round(g + (255 - g) * alpha)
                    b = round(b + (255 - b) * alpha)
                    break
            pixels += bytes((b, g, r, 255))  # BGRA, as the ICO format wants
    return bytes(pixels)


def _png(size: int, bgra: bytes) -> bytes:
    """Wrap raw pixels as a PNG (ICO accepts PNG frames from Vista onwards)."""
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter: none
        row = bgra[y * size * 4:(y + 1) * size * 4]
        for i in range(0, len(row), 4):
            b, g, r, a = row[i:i + 4]
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    frames = [(size, _png(size, _draw(size))) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, blobs = b"", b""
    for size, data in frames:
        entries += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset
        )
        blobs += data
        offset += len(data)
    ICON.write_bytes(header + entries + blobs)
    print(f"Wrote {ICON} ({ICON.stat().st_size:,} bytes, {len(frames)} sizes)")


if __name__ == "__main__":
    main()
