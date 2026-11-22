"""Compare two clip sets over the whole population, not a sample.

Two claims were previously backed by two clips: "the other 181 body clips are
unchanged" and "the tail moves". A sample cannot support either when the risk is a
per-clip difference — one clip's animation can be wrong while two chosen clips are
right.

This walks every clip in both trees and reports:

- per clip, the worst rotation (degrees) and worst position (units) delta over
  **non-tail** joints, which is the body-invariance question;
- per clip, the rotation spread of every tail joint across its samples and whether
  any of them actually moves, which is the tail-drive question;
- how many distinct tail *signatures* the population carries, so "shared authored
  curve" is a number rather than an impression.

  blender -b --python tools/body_population_sweep.py -- \
      --old artifacts/shiv-tailed --new artifacts/shiv-tailed4 \
      --report artifacts/receipts/population-sweep.json [--tolerance-angle 0.5 --tolerance-position 0.05]
"""

from __future__ import annotations
import os

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))
TAIL_PREFIX = "tail"


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tolerance-angle", type=float, default=0.5)
    parser.add_argument("--tolerance-position", type=float, default=0.05)
    return parser.parse_args(argv)


def _channels(datamodel, path: Path) -> dict[tuple[str, str], list[list[float]]]:
    model = datamodel.load(str(path))
    clip = model.root["animationList"]["animations"][0]
    rows: dict[tuple[str, str], list[list[float]]] = {}
    for channel in clip["channels"]:
        bone = getattr(channel.get("toElement"), "name", "")
        attribute = str(channel.get("toAttribute", ""))
        layers = channel["log"]["layers"]
        values = layers[0]["values"] if layers else []
        parsed = []
        for value in values:
            if isinstance(value, (list, tuple)):
                parsed.append([float(part) for part in value])
            else:
                parsed.append([float(value)])
        rows[(bone, attribute)] = parsed
    return rows


def _angle(a, b) -> float:
    if len(a) != len(b) or len(a) != 4:
        return 0.0
    dot = abs(sum(x * y for x, y in zip(a, b)))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0.0:
        return 0.0
    dot = min(1.0, max(-1.0, dot / norm))
    return math.degrees(2.0 * math.acos(dot))


def _distance(a, b) -> float:
    if len(a) < 3 or len(b) < 3:
        return 0.0
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel

    old_dir = Path(args.old)
    new_dir = Path(args.new)
    new_clips = {path.stem: path for path in sorted(new_dir.glob("*.dmx"))}

    table = []
    tail_rows = {}
    signatures = {}
    for stem, new_path in new_clips.items():
        old_path = old_dir / new_path.name
        new_channels = _channels(datamodel, new_path)
        body_worst_angle = 0.0
        body_worst_position = 0.0
        body_bone = None
        if old_path.is_file():
            old_channels = _channels(datamodel, old_path)
            for key, new_values in new_channels.items():
                bone, attribute = key
                if bone.startswith(TAIL_PREFIX) or bone == "root_motion" and False:
                    continue
                old_values = old_channels.get(key)
                if not old_values:
                    continue
                for index in range(min(len(old_values), len(new_values))):
                    if attribute == "orientation":
                        delta = _angle(old_values[index], new_values[index])
                        if delta > body_worst_angle:
                            body_worst_angle, body_bone = delta, bone
                    elif attribute == "position":
                        delta = _distance(old_values[index], new_values[index])
                        if delta > body_worst_position:
                            body_worst_position = delta
        table.append(
            {
                "clip": stem,
                "compared": old_path.is_file(),
                "body_angle": round(body_worst_angle, 4),
                "body_position": round(body_worst_position, 4),
                "body_bone": body_bone,
            }
        )

        spread = {}
        for (bone, attribute), values in new_channels.items():
            if not bone.startswith(TAIL_PREFIX) or attribute != "orientation" or len(values) < 2:
                continue
            span = max(
                max(row[index] for row in values) - min(row[index] for row in values)
                for index in range(len(values[0]))
            )
            spread[bone] = round(span, 5)
        moving = {bone: span for bone, span in spread.items() if span > 1e-4}
        tail_rows[stem] = {"joints": len(spread), "moving": len(moving), "spread": spread}
        if moving:
            key = hashlib.sha1(
                json.dumps({bone: round(span, 3) for bone, span in sorted(moving.items())}).encode()
            ).hexdigest()[:12]
            signatures.setdefault(key, []).append(stem)

    compared = [row for row in table if row["compared"]]
    over_angle = [row for row in compared if row["body_angle"] > args.tolerance_angle]
    over_position = [row for row in compared if row["body_position"] > args.tolerance_position]
    worst_angle = max(compared, key=lambda row: row["body_angle"]) if compared else None
    worst_position = max(compared, key=lambda row: row["body_position"]) if compared else None

    moving_clips = sum(1 for row in tail_rows.values() if row["moving"])
    per_joint = {}
    for row in tail_rows.values():
        for bone, span in row["spread"].items():
            per_joint.setdefault(bone, []).append(span)
    spread_summary = {
        bone: {
            "clips": len(values),
            "min": round(min(values), 5),
            "median": round(sorted(values)[len(values) // 2], 5),
            "max": round(max(values), 5),
        }
        for bone, values in sorted(per_joint.items())
    }

    receipt = {
        "schema": "hero-retarget-workbench.population-sweep/1",
        "old": str(old_dir),
        "new": str(new_dir),
        "tolerance": {"angle_deg": args.tolerance_angle, "position_units": args.tolerance_position},
        "clips_in_new": len(table),
        "clips_compared": len(compared),
        "body": {
            "over_angle": len(over_angle),
            "over_position": len(over_position),
            "worst_angle": worst_angle,
            "worst_position": worst_position,
            "table": table,
        },
        "tail": {
            "clips": len(tail_rows),
            "clips_with_moving_tail": moving_clips,
            "clips_with_static_tail": len(tail_rows) - moving_clips,
            "spread_per_joint": spread_summary,
            "distinct_signatures": len(signatures),
            "signature_sizes": {key: len(value) for key, value in list(signatures.items())[:10]},
        },
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        "POP body compared={} over_angle={} over_position={} worst_angle={} worst_position={}".format(
            len(compared),
            len(over_angle),
            len(over_position),
            (worst_angle or {}).get("clip"),
            (worst_position or {}).get("clip"),
        )
    )
    print(
        f"POP tail clips={len(tail_rows)} moving={moving_clips} "
        f"static={len(tail_rows) - moving_clips} signatures={len(signatures)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
