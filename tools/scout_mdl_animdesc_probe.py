"""Read frame counts from the anim descriptions the four sequence descriptors name.

The descriptors decode as 212-byte entries with every field 4 bytes later than `studio.h` (label at +4,
activity name at +8, numblends at +56, anim index block at +60). `numblends` is 1 for the motion clips
and 12 for the aim matrices, so the frame count is read per anim description and reported as the
sequence's maximum, next to the anim names.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = (Path("F:/Documents/scout.mdl"), Path("F:/Documents/scout_animations.mdl"))
OUT = ROOT / "data" / "probes" / "2026-11-24-scout-mdl-animdesc.md"
LABELS = ("PRIMARY_aimmatrix_idle", "PRIMARY_aimmatrix_run", "AttackStand_PRIMARY", "PRIMARY_reload_loop")
ANIM_DESC_SIZE = 100
FPS_OFFSET, FRAMES_OFFSET = 8, 16
NAME_OFFSET = 4


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


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
        "# 2026-11-24 — decoder probe: anim descriptions behind the four sequences",
        "",
        "Rule: sequence stride 212; label +4, activity name +8, flags +12, numblends +56,",
        "anim-index block +60 (desc-relative); animdesc stride 100 at header +184; frames +16, fps +8.",
        "",
    ]
    for model in MODELS:
        data = model.read_bytes()
        base = i32(data, 192)
        count = i32(data, 188)
        anim_base = i32(data, 184)
        anim_count = i32(data, 180)
        lines += [f"## {model}", "", f"- size {len(data)}, sequence table {base} x {count}, anim descriptions {anim_base} x {anim_count}", ""]
        rows = {}
        for index in range(count):
            desc = base + index * 212
            label = cstring(data, desc + i32(data, desc + 4))
            if label in LABELS:
                rows[label] = desc
        for name in LABELS:
            desc = rows.get(name)
            if desc is None:
                lines.append(f"- {name}: NOT FOUND")
                continue
            activity = cstring(data, desc + i32(data, desc + 8))
            flags = i32(data, desc + 12)
            numblends = i32(data, desc + 56)
            index_block = i32(data, desc + 60)
            at = desc + index_block
            anim_indices = [i16(data, at + 2 * blend) for blend in range(max(numblends, 1))]
            anims = []
            for anim_index in anim_indices:
                anim = anim_base + anim_index * ANIM_DESC_SIZE
                if 0 <= anim_index < anim_count and anim + ANIM_DESC_SIZE <= len(data):
                    anims.append(
                        {
                            "index": anim_index,
                            "name": cstring(data, anim + i32(data, anim + NAME_OFFSET)),
                            "frames": i32(data, anim + FRAMES_OFFSET),
                            "fps": round(f32(data, anim + FPS_OFFSET), 4),
                        }
                    )
            frames = [anim["frames"] for anim in anims if anim["frames"] > 0]
            lines += [
                f"### {name}",
                "",
                f"- descriptor {desc}, activity {activity!r}, flags {flags}",
                f"- numblends {numblends}, anim index block +{index_block} -> {at}",
                f"- anim indices {anim_indices[:12]}",
                f"- anim names/frames/fps: {[(a['name'], a['frames'], a['fps']) for a in anims][:12]}",
                f"- **declared frames: max {max(frames) if frames else 0}, distinct {sorted(set(frames))}**",
                "",
            ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
