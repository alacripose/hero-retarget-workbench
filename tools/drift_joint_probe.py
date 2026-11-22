"""Name the joints whose rest moved between a clip and the game's own body.

The release gate can only say *how many* joints drifted (`rest_drift_observed`); it cannot say
*which*, and the in-game report is specific: *"arms and head and tail rotated wrong"*. This probe
answers that directly, so a rebuild is aimed at the joints that actually moved rather than at the
whole clip.

    blender -b --factory-startup --python tools/drift_joint_probe.py -- \
        --clip artifacts/haze-tail/aligned7/item_stand_idle.dmx \
        --origin artifacts/haze-tail/bodies/item_stand_idle.dmx \
        --report artifacts/receipts/drift-item_stand_idle.json
"""

from __future__ import annotations
import os

import argparse
import json
import sys
from pathlib import Path

PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))
TOOLS = Path(__file__).resolve().parent


def datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel as module  # noqa: WPS433

    return module


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--degrees", type=float, default=0.5, help="report joints above this rotation")
    args = parser.parse_args(argv)

    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from tail_release_audit import _joint_table  # noqa: WPS433

    module = datamodel()
    here = _joint_table(module, args.clip)
    base = _joint_table(module, args.origin)
    rows = []
    for name, row in here.items():
        if name == "__order__" or name not in base:
            continue
        other = base[name]
        translation = max(abs(a - b) for a, b in zip(row["head"], other["head"]))
        dot = min(1.0, abs(sum(a * b for a, b in zip(row["orientation"], other["orientation"]))))
        degrees = 2.0 * __import__("math").degrees(__import__("math").acos(dot)) / 2.0
        if translation > 0.01 or degrees > args.degrees:
            rows.append({"joint": name, "translation": round(translation, 4), "degrees": round(degrees, 3)})
    rows.sort(key=lambda item: -max(item["translation"], item["degrees"]))
    print(f"DRIFT {len(rows)} joints moved between {Path(args.clip).name} and {Path(args.origin).name}")
    for row in rows[:20]:
        print(f"  {row['joint']:24s} translation {row['translation']:9.4f}  rotation {row['degrees']:8.3f} deg")
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"clip": args.clip, "origin": args.origin, "moved": rows}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
