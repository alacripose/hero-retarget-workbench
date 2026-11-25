"""Pin the sequence table start by matching descriptor label fields against known sequence names.

The header's `localseqindex` puts the table's byte size (`numlocalseq * 212`) 28 bytes into the block,
which means the block begins *before* the descriptors. This tries every 4-byte start in a window
around it, both offset conventions (`desc + label_offset` and plain `label_offset`), and reports the
start at which a descriptor's label is one of the four known Scout sequence names.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = Path("F:/Documents/scout.mdl")
LABELS = ("PRIMARY_aimmatrix_idle", "PRIMARY_aimmatrix_run", "AttackStand_PRIMARY", "PRIMARY_reload_loop")
OUT = ROOT / "data" / "probes" / "2026-11-24-scout-mdl-sequence-start.md"
STRIDE = 212


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def cstring(data: bytes, offset: int) -> str:
    if not (0 <= offset < len(data)):
        return ""
    end = data.find(b"\x00", offset)
    return data[offset : end if end >= 0 else offset + 64].decode("latin-1", errors="replace")


def main() -> int:
    data = MODEL.read_bytes()
    seq_count = i32(data, 188)
    base = i32(data, 192)
    labels_at = {name: data.find(name.encode()) for name in LABELS}
    lines = [
        "# 2026-11-24 — decoder probe: which byte starts the sequence table",
        "",
        f"- model {MODEL}, size {len(data)}, version {i32(data, 4)}, numlocalseq {seq_count}, localseqindex {base}",
        f"- known label offsets: {labels_at}",
        f"- table bytes if 212-byte descriptors: {seq_count * STRIDE}, found at {base + 28}",
        "",
        "## starts whose labels match a known sequence name",
        "",
    ]
    found = []
    for start in range(base - 32, base + 224, 4):
        for index in range(seq_count):
            desc = start + index * STRIDE
            if desc + STRIDE > len(data):
                break
            raw = i32(data, desc)
            for mode, label_abs in (("desc-relative", desc + raw), ("absolute", raw)):
                for name, expected in labels_at.items():
                    if expected >= 0 and label_abs == expected:
                        found.append((start, index, name, mode))
    lines.append(f"- matches: {found}")
    lines.append("")

    # Field sanity at the best candidate: labels printable, anim index in range, lastframe plausible.
    candidates = sorted({row[0] for row in found}) or [base]
    lines += ["## field sanity per candidate start", ""]
    for start in candidates:
        printable = 0
        anim_ok = 0
        names = []
        for index in range(seq_count):
            desc = start + index * STRIDE
            if desc + STRIDE > len(data):
                break
            label = cstring(data, desc + i32(data, desc))
            if label and all(32 <= ord(char) < 127 for char in label):
                printable += 1
                if index < 6 or label in LABELS:
                    names.append(label)
            anim_offset = i32(data, desc + 56)
            if 0 < anim_offset < STRIDE * 4:
                anim_ok += 1
        lines.append(f"- start {start}: printable labels {printable}/{seq_count}, animindex offsets in range {anim_ok}/{seq_count}")
        lines.append(f"  - first labels: {names[:8]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
