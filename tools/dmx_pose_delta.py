"""Compare two animation DMX files as poses, not as numbers.

`tools/dmx_channel_compare.py` compares each component, which is right for the
structural question but wrong for orientation: a quaternion and its negation are
the same rotation and read as a 2.0 difference. That makes a correct aim cell look
broken. This measures the actual angle between two rotations, and the actual
distance between two positions, so "does our clip pose the body the way the
game's does" has a numeric answer in degrees.

  blender -b --python tools/dmx_pose_delta.py -- --a <ours.dmx> --b <game.dmx>
"""

from __future__ import annotations
import os

import argparse
import math
import sys
from pathlib import Path

PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--angle", type=float, default=0.5, help="degrees that still count as the same pose")
    parser.add_argument("--distance", type=float, default=0.05, help="units that still count as the same pose")
    return parser.parse_args(argv)


def _channels(datamodel, path: str) -> dict[tuple[str, str], list]:
    model = datamodel.load(path)
    clip = model.root["animationList"]["animations"][0]
    out: dict[tuple[str, str], list] = {}
    for channel in clip["channels"]:
        target = channel.get("toElement")
        bone = getattr(target, "name", "")
        attribute = str(channel.get("toAttribute", ""))
        layers = channel["log"]["layers"]
        values = []
        for value in (layers[0]["values"] if layers else []):
            if isinstance(value, (list, tuple)):
                values.append(tuple(float(part) for part in value))
            else:
                values.append(float(value))
        out[(bone, attribute)] = values
    return out


def _angle_degrees(a, b) -> float:
    """Rotation angle between two quaternions, sign-insensitive."""
    if len(a) != 4 or len(b) != 4:
        return float("inf")
    # DMX orientations are x, y, z, w.
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    dot = abs(ax * bx + ay * by + az * bz + aw * bw)
    dot = min(1.0, max(-1.0, dot))
    return math.degrees(2.0 * math.acos(dot))


def _distance(a, b) -> float:
    if len(a) != len(b):
        return float("inf")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _worst(left, right, measure) -> float:
    if not left or not right:
        return float("inf")
    if len(left) != len(right):
        # Different sample counts: compare on the shared normalised span so the
        # question stays "same pose at the same phase", not "same file layout".
        worst = 0.0
        count = min(len(left), len(right))
        for index in range(count):
            li = round(index * (len(left) - 1) / max(1, count - 1))
            ri = round(index * (len(right) - 1) / max(1, count - 1))
            worst = max(worst, measure(left[li], right[ri]))
        return worst
    return max((measure(l, r) for l, r in zip(left, right)), default=0.0)


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel

    a = _channels(datamodel, args.a)
    b = _channels(datamodel, args.b)
    shared = sorted(set(a) & set(b))
    rotations, positions, other = [], [], []
    for key in shared:
        bone, attribute = key
        if attribute == "orientation":
            rotations.append((_worst(a[key], b[key], _angle_degrees), bone))
        elif attribute == "position":
            positions.append((_worst(a[key], b[key], _distance), bone))
        else:
            other.append((_worst(a[key], b[key], _distance), f"{bone}.{attribute}"))
    rotations.sort(reverse=True)
    positions.sort(reverse=True)
    other.sort(reverse=True)
    print(f"POSE shared={len(shared)} only-in-ours={len(set(a) - set(b))} only-in-game={len(set(b) - set(a))}")
    print("POSE worst rotations(deg):", [(bone, round(value, 3)) for value, bone in rotations[:8]])
    print("POSE worst positions:", [(bone, round(value, 4)) for value, bone in positions[:8]])
    if other:
        print("POSE worst other:", [(name, round(value, 4)) for value, name in other[:5]])
    bad_rotation = [item for item in rotations if item[0] > args.angle]
    bad_position = [item for item in positions if item[0] > args.distance]
    print(
        f"POSE rotations-over-{args.angle}deg={len(bad_rotation)} "
        f"positions-over-{args.distance}={len(bad_position)}"
    )
    ok = not bad_rotation and not bad_position
    print(f"POSE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
