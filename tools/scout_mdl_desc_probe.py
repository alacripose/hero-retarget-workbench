"""Field-by-field decode of the first two 212-byte entries at `localseqindex`.

Prints every (field offset, base) pair whose target lands on a printable string, so the descriptor's
label/activity positions and its offset base are read rather than assumed.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = Path("F:/Documents/scout.mdl")
OUT = ROOT / "data" / "probes" / "2026-11-24-scout-mdl-descriptor-fields.md"


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def printable(data: bytes, offset: int) -> str:
    if not (0 <= offset < len(data) - 2):
        return ""
    end = data.find(b"\x00", offset)
    if end < 0 or end - offset > 80 or end == offset:
        return ""
    text = data[offset:end].decode("latin-1", errors="replace")
    if all(32 <= ord(char) < 127 for char in text):
        return text
    return ""


def main() -> int:
    data = MODEL.read_bytes()
    size = len(data)
    base = i32(data, 192)
    lines = [
        "# 2026-11-24 — decoder probe: fields of the first two entries at localseqindex",
        "",
        f"- base {base}, size {size}",
        "",
    ]
    for index in range(3):
        desc = base + index * 212
        lines.append(f"## entry {index} at {desc}")
        lines.append(f"- ints: {[i32(data, desc + k) for k in range(0, 64, 4)]}")
        for field in range(0, 128, 4):
            value = i32(data, desc + field)
            for name, target in (
                ("desc", desc + value),
                ("desc+field", desc + field + value),
                ("base", base + value),
                ("file", value),
                ("end", size + value),
            ):
                text = printable(data, target)
                if text:
                    lines.append(f"  - +{field:<3} value {value:<12} {name:<10} -> {target} {text!r}")
        lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
