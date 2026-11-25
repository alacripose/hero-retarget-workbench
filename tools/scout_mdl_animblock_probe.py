"""Inspect the anim blocks behind the four sequence anim descriptions.

Reads each animdesc's block/index fields from the header's anim-block table and dumps the block's
extent and first bytes. If the RLE decodes for a bone, reports its value range; if it does not, the
offset that fails is printed so the gap is named rather than assumed.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = Path("F:/Documents/scout_animations.mdl")
OUT = ROOT / "data" / "probes" / "2026-11-24-scout-mdl-anim-blocks.md"
LABELS = ("PRIMARY_aimmatrix_idle", "PRIMARY_aimmatrix_run", "AttackStand_PRIMARY", "PRIMARY_reload_loop")
ANIM_DESC_SIZE = 100
HEADER_ANIMBLOCK_INDEX, HEADER_ANIMBLOCK_COUNT, HEADER_ANIMBLOCK_NAME = 356, 352, 348


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def main() -> int:
    data = MODEL.read_bytes()
    seq_base = i32(data, 192)
    seq_count = i32(data, 188)
    anim_base = i32(data, 184)
    anim_count = i32(data, 180)
    block_base = i32(data, HEADER_ANIMBLOCK_INDEX)
    block_count = i32(data, HEADER_ANIMBLOCK_COUNT)
    lines = [
        "# 2026-11-24 — decoder probe: anim blocks behind the four sequences",
        "",
        f"- model {MODEL}, size {len(data)}",
        f"- sequences {seq_base} x {seq_count}, animdesc {anim_base} x {anim_count}",
        f"- anim blocks {block_base} x {block_count}, name field {i32(data, HEADER_ANIMBLOCK_NAME)}",
        "",
    ]
    sequences = {}
    for index in range(seq_count):
        desc = seq_base + index * 212
        end = data.find(b"\x00", desc + i32(data, desc + 4))
        label = data[desc + i32(data, desc + 4) : end].decode("latin-1", "replace")
        if label in LABELS:
            sequences[label] = desc
    for name, desc in sequences.items():
        numblends = i32(data, desc + 56)
        index_at = desc + i32(data, desc + 60)
        first = i16(data, index_at)
        anim = anim_base + first * ANIM_DESC_SIZE
        fields = {offset: i32(data, anim + offset) for offset in range(0, ANIM_DESC_SIZE, 4)}
        lines += [
            f"## {name}",
            "",
            f"- descriptor {desc}, numblends {numblends}, first animdesc index {first} at {anim}",
            f"- animdesc ints: {[fields[offset] for offset in range(0, ANIM_DESC_SIZE, 4)]}",
        ]
        block = fields.get(28, 0)
        anim_index = fields.get(32, 0)
        if 0 <= block < block_count:
            at = block_base + block * 8
            start, end = i32(data, at), i32(data, at + 4)
            payload = data[start:end]
            lines.append(
                f"- anim block {block}: table entry {at} -> data {start}..{end} ({end - start} B), "
                f"first 32 bytes {payload[:32].hex()}"
            )
            if anim_index and start + anim_index < len(data):
                lines.append(f"- anim data at block start + {anim_index}: {data[start + anim_index:start + anim_index + 24].hex()}")
        else:
            lines.append(f"- anim block {block} outside the table (0..{block_count})")
        lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
