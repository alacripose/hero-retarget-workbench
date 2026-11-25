"""Decode the parts of scout.mdl whose layout is independently checkable, then reuse the convention.

If the bone table decodes with descriptor-relative name offsets, the file uses Source 1 conventions and
the sequence table's placement is the only unknown. If it does not, the file stores offsets differently
and every table has to be read that way. Also dumps the bytes around `localseqindex` so the exact
element that disagrees with a 212-byte descriptor is visible.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = Path("F:/Documents/scout.mdl")
OUT = ROOT / "data" / "probes" / "2026-11-24-scout-mdl-header-and-bones.md"
BONE_SIZE = 216


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def cstring(data: bytes, offset: int) -> str:
    if not (0 <= offset < len(data)):
        return ""
    end = data.find(b"\x00", offset)
    return data[offset : end if end >= 0 else offset + 64].decode("latin-1", errors="replace")


def main() -> int:
    data = MODEL.read_bytes()
    size = len(data)
    bones_at = i32(data, 160)
    bone_count = i32(data, 156)
    seq_at = i32(data, 192)
    lines = [
        "# 2026-11-24 — decoder probe: scout.mdl header, bones, and the bytes at localseqindex",
        "",
        f"- size {size}, version {i32(data, 4)}, name {cstring(data, 12)}",
        f"- numbones {bone_count} @ {bones_at}, numlocalseq {i32(data, 188)} @ {seq_at}",
        "",
        "## bone table",
        "",
    ]
    for index in range(min(bone_count, 6)):
        bone = bones_at + index * BONE_SIZE
        name_index = i32(data, bone)
        relative = cstring(data, bone + name_index)
        absolute = cstring(data, name_index)
        lines.append(
            f"- bone {index} @ {bone}: sznameindex {name_index}, desc-relative {relative!r}, absolute {absolute!r}, "
            f"parent {i32(data, bone + 4)}"
        )
    lines += [
        "",
        "## bytes at localseqindex",
        "",
        f"- ints at {seq_at}: {[i32(data, seq_at + k) for k in range(0, 64, 4)]}",
        f"- floats at {seq_at}: {[round(f32(data, seq_at + k), 4) for k in range(0, 64, 4)]}",
        f"- int at +28: {i32(data, seq_at + 28)} (numlocalseq*212 = {i32(data, 188) * 212})",
        "",
        "## descriptor candidate at localseqindex, field by field",
        "",
    ]
    fields = [
        (0, "szlabelindex"),
        (4, "szactivitynameindex"),
        (8, "flags"),
        (12, "activity"),
        (16, "actweight"),
        (20, "numevents"),
        (24, "eventindex"),
        (52, "numblends"),
        (56, "animindexindex"),
        (60, "movementindex"),
        (92, "fadeintime"),
        (96, "fadeouttime"),
        (120, "lastframe"),
        (124, "nextseq"),
        (128, "pose"),
    ]
    for offset, name in fields:
        value = i32(data, seq_at + offset)
        lines.append(f"- +{offset:<3} {name:<20} {value}")
    lines += [
        "",
        "## same fields 4 bytes earlier (if the block starts before the descriptor)",
        "",
    ]
    for offset, name in fields:
        value = i32(data, seq_at - 4 + offset)
        lines.append(f"- +{offset:<3} {name:<20} {value}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
