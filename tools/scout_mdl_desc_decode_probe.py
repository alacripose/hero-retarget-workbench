"""Decode the 212-byte entries with the label/activity positions the field probe found, and look for
the four Scout sequences' declared frame counts.

Rule under test: label = entry + i32(entry + 4), activity = entry + i32(entry + 8). The four known
labels are used as the acceptance test; then every int/float field of those four entries is printed so
the frame-count field can be identified by agreeing with independent evidence (SMD frames 21/20/1/1).
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = (Path("F:/Documents/scout.mdl"), Path("F:/Documents/scout_animations.mdl"))
OUT = ROOT / "data" / "probes" / "2026-11-24-scout-mdl-sequence-decode.md"
LABELS = ("PRIMARY_aimmatrix_idle", "PRIMARY_aimmatrix_run", "AttackStand_PRIMARY", "PRIMARY_reload_loop")


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def cstring(data: bytes, offset: int) -> str:
    if not (0 <= offset < len(data)):
        return ""
    end = data.find(b"\x00", offset)
    if end < 0 or end == offset or end - offset > 96:
        return ""
    text = data[offset:end].decode("latin-1", errors="replace")
    return text if all(32 <= ord(char) < 127 for char in text) else ""


def main() -> int:
    lines = [
        "# 2026-11-24 — decoder probe: sequence descriptors and their frame fields",
        "",
        "Rule under test: label = entry + i32(entry + 4), activity = entry + i32(entry + 8), stride 212.",
        "",
    ]
    for model in MODELS:
        data = model.read_bytes()
        base = i32(data, 192)
        count = i32(data, 188)
        lines += [f"## {model}", "", f"- base {base}, count {count}, stride 212", ""]
        entries = []
        printable = 0
        for index in range(count):
            desc = base + index * 212
            label = cstring(data, desc + i32(data, desc + 4))
            activity = cstring(data, desc + i32(data, desc + 8))
            if label:
                printable += 1
            entries.append((index, desc, label, activity))
        lines.append(f"- labels decoded as printable: {printable}/{count}")
        lines.append(f"- first 6: {[(row[0], row[2], row[3]) for row in entries[:6]]}")
        lines.append("")
        for name in LABELS:
            row = next((entry for entry in entries if entry[2] == name), None)
            if row is None:
                lines.append(f"- {name}: NOT FOUND")
                continue
            index, desc, label, activity = row
            lines.append(f"### {name} — entry {index} at {desc}, activity {activity!r}")
            ints = [i32(data, desc + offset) for offset in range(0, 212, 4)]
            floats = [round(f32(data, desc + offset), 4) for offset in range(0, 212, 4)]
            lines.append(f"- ints: {ints}")
            lines.append(f"- floats: {floats}")
            lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
