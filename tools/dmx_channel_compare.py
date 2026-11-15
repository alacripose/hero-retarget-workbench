"""Compare two animation DMX files channel by channel, without a rig.

The rig round trip is what corrupted the body values, so verification must not
use it either: this reads both files with the datamodel and compares each
(bone, attribute) log sample for sample.

  blender -b --python tools/dmx_channel_compare.py -- --a <clip.dmx> --b <clip.dmx> [--expect-extra tail_0,tail_1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--expect-extra", default="")
    return parser.parse_args(argv)


def _channels(datamodel, path: str) -> dict[tuple[str, str], list[float]]:
    model = datamodel.load(path)
    animations = model.root["animationList"]["animations"]
    clip = animations[0]
    out: dict[tuple[str, str], list[float]] = {}
    for channel in clip["channels"]:
        target = channel.get("toElement")
        bone = getattr(target, "name", "")
        attribute = str(channel.get("toAttribute", ""))
        layers = channel["log"]["layers"]
        values = list(layers[0]["values"]) if layers else []
        out[(bone, attribute)] = [float(value) if not isinstance(value, (list, tuple)) else tuple(float(v) for v in value) for value in values]
    return out


def _diff(left, right):
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return float("inf")
        worst = 0.0
        for a, b in zip(left, right):
            worst = max(worst, _diff(a, b))
        return worst
    if isinstance(left, tuple) and isinstance(right, tuple):
        if len(left) != len(right):
            return float("inf")
        return max((abs(a - b) for a, b in zip(left, right)), default=0.0)
    if isinstance(left, tuple) or isinstance(right, tuple):
        return float("inf")
    return abs(left - right)


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel

    a = _channels(datamodel, args.a)
    b = _channels(datamodel, args.b)
    shared = sorted(set(a) & set(b))
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    differing = []
    for key in shared:
        delta = _diff(a[key], b[key])
        if delta > 0:
            differing.append((delta, key))
    differing.sort(reverse=True)
    print(f"CHANNELS a={len(a)} b={len(b)} shared={len(shared)}")
    print(f"CHANNELS only-in-a({len(only_a)}): {[f'{bone}.{attr}' for bone, attr in only_a][:10]}")
    print(f"CHANNELS only-in-b({len(only_b)}): {[f'{bone}.{attr}' for bone, attr in only_b][:10]}")
    print(f"CHANNELS differing({len(differing)}): {[(f'{k[0]}.{k[1]}', round(v, 6)) for v, k in differing[:10]]}")
    expected = {name.strip() for name in args.expect_extra.split(",") if name.strip()}
    unexpected = [key for key in only_b if key[0] not in expected]
    print(f"CHANNELS unexpected extras({len(unexpected)}): {[f'{k[0]}.{k[1]}' for k in unexpected][:10]}")
    ok = not differing and not only_a and not unexpected
    print(f"CHANNELS {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
