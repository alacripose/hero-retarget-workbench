"""Give every shipped clip a moving tail, from the project's authored tail motion.

`dmx_tail_append.py` added the seven tail joints and their channels, but the values
it wrote are the tail's *rest*: measured on ten shipped clips, every tail channel
spread is 0.0 or 4e-6, so the tail is drawn at one pose for the whole game. A tail
that never moves is the same defect as a tail that is not drawn whenever the rest
pose sits inside the body.

The motion here is not invented per clip. It is the authored tail curve that lives
in `…/shiv_tail_anim/…/clips/weapon_stand_idle.dmx` — the only authored tail
animation the project has — sampled as a delta from its own first frame, resampled
onto each clip's own time base, and composed onto that clip's existing tail pose.
Body channels are never touched, so the 181-clip body sweep keeps its result.

  blender -b --python tools/tail_motion_apply.py -- \
      --source <authored tail clip.dmx> --clips artifacts/shiv-appended2 \
      --out artifacts/shiv-tailed [--only clip1,clip2]
"""

from __future__ import annotations
import os

import argparse
import json
import math
import sys
from pathlib import Path

PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))
TAIL = ("tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--clips", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", default="")
    parser.add_argument("--amplitude", type=float, default=1.0)
    parser.add_argument("--report", default="artifacts/receipts/tail-motion-apply.json")
    return parser.parse_args(argv)


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def _normalise(q):
    norm = math.sqrt(sum(component * component for component in q)) or 1.0
    return tuple(component / norm for component in q)


def _power(q, exponent):
    x, y, z, w = _normalise(q)
    angle = 2.0 * math.acos(max(-1.0, min(1.0, w)))
    sine = math.sqrt(max(0.0, 1.0 - w * w))
    if sine < 1e-9:
        return q
    axis = (x / sine, y / sine, z / sine)
    half = angle * exponent * 0.5
    return (axis[0] * math.sin(half), axis[1] * math.sin(half), axis[2] * math.sin(half), math.cos(half))


def _channels(clip) -> dict:
    rows = {}
    for channel in clip["channels"]:
        target = channel.get("toElement")
        rows[(getattr(target, "name", ""), str(channel.get("toAttribute", "")))] = channel
    return rows


def _values(channel) -> list:
    layers = channel["log"]["layers"]
    return [list(map(float, row)) if isinstance(row, (list, tuple)) else [float(row)] for row in layers[0]["values"]] if layers else []


def _times(channel) -> list[float]:
    layer = channel["log"]["layers"][0]
    if "times" in layer.keys():
        return [float(value) for value in layer["times"]]
    return [float(index) for index in range(len(_values(channel)))]


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel

    authored = datamodel.load(args.source)
    source_clip = authored.root["animationList"]["animations"][0]
    source = {}
    for (name, attribute), channel in _channels(source_clip).items():
        if name not in TAIL or attribute != "orientation":
            continue
        values = [tuple(_normalise(row)) for row in _values(channel)]
        times = _times(channel)
        if len(values) < 2:
            continue
        base = values[0]
        source[name] = {
            "times": times,
            "deltas": [_qmul(_qconj(base), value) for value in values],
        }

    wanted = [name.strip() for name in args.only.split(",") if name.strip()]
    clips = [path for path in sorted(Path(args.clips).glob("*.dmx")) if not wanted or path.stem in wanted]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    applied = []
    skipped = []
    for path in clips:
        model = datamodel.load(str(path))
        clip = model.root["animationList"]["animations"][0]
        rows = _channels(clip)
        touched = 0
        for name, curve in source.items():
            channel = rows.get((name, "orientation"))
            if channel is None:
                continue
            times = _times(channel)
            values = _values(channel)
            if not values:
                continue
            start = times[0] if times else 0.0
            end = times[-1] if times else 1.0
            span = (end - start) or 1.0
            source_span = (curve["times"][-1] - curve["times"][0]) or 1.0
            layer = channel["log"]["layers"][0]
            rows_out = layer["values"]
            for index, row in enumerate(values):
                phase = ((times[index] - start) / span) if times else index / max(1, len(values) - 1)
                position = phase % 1.0
                sample_at = curve["times"][0] + position * source_span
                nearest = min(range(len(curve["times"])), key=lambda i: abs(curve["times"][i] - sample_at))
                delta = _power(curve["deltas"][nearest], args.amplitude)
                composed = _qmul(tuple(row), delta)
                for slot, component in enumerate(_normalise(composed)):
                    rows_out[index][slot] = component
                touched += 1
        destination = out / path.name
        model.write(str(destination), "binary", 9)
        if destination.exists():
            applied.append({"clip": path.name, "samples": touched})
        else:
            skipped.append(path.name)

    receipt = {
        "schema": "hero-retarget-workbench.tail-motion/1",
        "source": args.source,
        "clips_in": len(clips),
        "clips_out": len(applied),
        "skipped": skipped[:20],
        "joints_with_motion": sorted(source.keys()),
        "amplitude": args.amplitude,
        "detail": applied[:20],
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"TAILMOTION joints={len(source)} clips_in={len(clips)} clips_out={len(applied)} skipped={len(skipped)}")
    return 0 if applied else 1


if __name__ == "__main__":
    raise SystemExit(main())
