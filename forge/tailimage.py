"""A tiny PNG writer for tail-chain thumbnails, with no image dependency."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

Point = tuple[float, float, float]


def _project(points: list[Point]) -> list[tuple[float, float]]:
    if not points:
        return []
    ranges = []
    for axis in range(3):
        values = [point[axis] for point in points]
        ranges.append(max(values) - min(values))
    # A tail may hang down (Z), trail behind (Y), or spread sideways (X). Use the
    # two axes that actually contain the chain instead of assuming front view.
    axes = sorted(range(3), key=ranges.__getitem__, reverse=True)[:2]
    return [(point[axes[0]], point[axes[1]]) for point in points]


def _line(buffer: list[list[tuple[int, int, int, int]]], x0: int, y0: int, x1: int, y1: int) -> None:
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        if 0 <= y0 < len(buffer) and 0 <= x0 < len(buffer[0]):
            buffer[y0][x0] = (235, 238, 245, 255)
            if x0 + 1 < len(buffer[0]):
                buffer[y0][x0 + 1] = (210, 216, 228, 255)
        if x0 == x1 and y0 == y1:
            break
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def write_tail_png(path: Path | str, chains: list[list[Point]], size: int = 160) -> Path | None:
    """Draw every chain into one transparent PNG and return its path."""
    flat = [point for chain in chains for point in chain]
    if not flat:
        return None
    raw = _project(flat)
    xs = [point[0] for point in raw]
    ys = [point[1] for point in raw]
    span_x = max(max(xs) - min(xs), 1e-6)
    span_y = max(max(ys) - min(ys), 1e-6)
    pad = size * 0.14
    scale = min((size - 2 * pad) / span_x, (size - 2 * pad) / span_y)
    offset_x = (size - span_x * scale) / 2
    offset_y = (size - span_y * scale) / 2
    pixels: list[list[tuple[int, int, int, int]]] = [
        [(0, 0, 0, 0) for _ in range(size)] for _ in range(size)
    ]
    index = 0
    for chain in chains:
        if not chain:
            continue
        projected = raw[index : index + len(chain)]
        index += len(chain)
        screen = [
            (
                int(offset_x + (x - min(xs)) * scale),
                int(size - 1 - (offset_y + (y - min(ys)) * scale)),
            )
            for x, y in projected
        ]
        for start, end in zip(screen, screen[1:]):
            _line(pixels, start[0], start[1], end[0], end[1])
        for x, y in screen:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if 0 <= y + dy < size and 0 <= x + dx < size:
                        pixels[y + dy][x + dx] = (255, 255, 255, 255)

    rows = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in pixels)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return target
