"""Layout probe for the Source 1 sequence table in `F:/Documents/scout.mdl`.

The header's `localseqindex` does not behave like the table start: at that offset the first int is
the negative of its own position. This probe treats the table as an unknown layout and tests the
relationships a descriptor can use:

  * label offset relative to the descriptor (`desc + offset == label`)
  * label offset relative to a fixed base (find bases shared by all four known labels)
  * a stride/start whose descriptors point into the label string blob

It prints the evidence; it does not assert a layout. Writes `data/probes/2026-11-24-scout-mdl-sequence-layout.md`.
"""
from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = [Path("F:/Documents/scout.mdl"), Path("F:/Documents/scout_animations.mdl")]
LABELS = ("PRIMARY_aimmatrix_idle", "PRIMARY_aimmatrix_run", "AttackStand_PRIMARY", "PRIMARY_reload_loop")
NOTE = ROOT / "data" / "probes" / "2026-11-24-scout-mdl-sequence-layout.md"


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def main() -> int:
    lines = ["# 2026-11-24 — decoder probe: the sequence table in scout.mdl", ""]
    for path in MODELS:
        data = path.read_bytes()
        size = len(data)
        version = i32(data, 4)
        header = {
            "numlocalanim": i32(data, 180),
            "localanimindex": i32(data, 184),
            "numlocalseq": i32(data, 188),
            "localseqindex": i32(data, 192),
        }
        labels = {name: data.find(name.encode()) for name in LABELS}
        lines += [
            f"## {path}",
            "",
            f"- size {size}, version {version}, header {header}",
            f"- labels: {labels}",
            f"- sequence table byte size from header: {header['numlocalseq'] * 212} (212-byte descriptor)",
            "",
        ]
        seq_at = header["localseqindex"]
        lines.append(f"- ints at localseqindex ({seq_at}): " + str([i32(data, seq_at + k) for k in range(0, 40, 4)]))
        lines.append(f"- int at +28 (numlocalseq*212?): {i32(data, seq_at + 28)} vs {header['numlocalseq'] * 212}")
        lines.append("")

        # 1) descriptor-relative labels
        hits = {name: [] for name in LABELS}
        for position in range(0, size - 4, 4):
            value = i32(data, position)
            if not (0 < value < size):
                continue
            target = position + value
            for name, at in labels.items():
                if at >= 0 and target == at:
                    hits[name].append(position)
        lines.append("- descriptor-relative label hits: " + str({k: v[:4] for k, v in hits.items()}))

        # 2) shared fixed base: label_abs - offset_value
        bases = Counter()
        for position in range(0, size - 4, 4):
            value = i32(data, position)
            if not (0 < value < size):
                continue
            for at in labels.values():
                if at < 0:
                    continue
                delta = at - value
                if 0 <= delta < size:
                    bases[delta] += 1
        lines.append(f"- most common (label_abs - int_value) bases: {bases.most_common(6)}")

        # 3) start/stride whose descriptors point into a label cluster
        lo = min(at for at in labels.values() if at >= 0) - 2000
        hi = max(at for at in labels.values() if at >= 0) + 2000
        best = []
        for stride in (196, 200, 204, 208, 212, 216, 220, 224):
            for start in range(0, size - stride * 4, 4):
                score = 0
                for index in range(0, header["numlocalseq"], 17):
                    desc = start + index * stride
                    if desc + 4 > size:
                        break
                    label_at = desc + i32(data, desc)
                    if lo <= label_at <= hi:
                        score += 1
                if score >= 4:
                    best.append((score, stride, start))
        best.sort(reverse=True)
        lines.append(f"- best (score, stride, start) pointing into the label cluster: {best[:6]}")
        lines.append("")

    NOTE.parent.mkdir(parents=True, exist_ok=True)
    NOTE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
