"""Print a DMX's joint list, in order, so two skeletons can be compared by name.

`forge.tails.dmx_bone_names` reads NUL-separated name runs, which is enough to
classify a tail but not to compare a clip with the skeleton it will bind to. This
opens the file through PulseSrcOps' datamodel (the same reader the append and the
export use) and prints the joints in file order.

  blender -b --python tools/dmx_joint_names.py -- --dmx <file> [--dmx <file> ...] [--report <json>]
"""

from __future__ import annotations
import os

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))


def _datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    return datamodel


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--dmx", action="append", default=[])
    parser.add_argument("--report", default="")
    return parser.parse_args(argv)


def _joints(root):
    skeleton = root["skeleton"]
    return skeleton["jointList"] if "jointList" in skeleton else skeleton["children"]


def main() -> int:
    args = _arguments()
    datamodel = _datamodel()
    payload = {}
    for path in args.dmx:
        model = datamodel.load(path)
        names = [joint.name for joint in _joints(model.root)]
        payload[path] = {"count": len(names), "joints": names}
        print(f"JOINTS {path} {len(names)}", flush=True)
    if len(payload) > 1:
        keys = list(payload)
        base = payload[keys[0]]["joints"]
        for other in keys[1:]:
            names = payload[other]["joints"]
            missing = [name for name in base if name not in names]
            extra = [name for name in names if name not in base]
            same_order = base == names
            print(
                f"COMPARE {Path(keys[0]).name} vs {Path(other).name}: "
                f"missing {len(missing)} extra {len(extra)} same_order {same_order}",
                flush=True,
            )
            if missing:
                print(f"  missing {missing[:12]}", flush=True)
            if extra:
                print(f"  extra {extra[:12]}", flush=True)
            payload[other]["missing_from_base"] = missing
            payload[other]["extra_over_base"] = extra
            payload[other]["same_order"] = same_order
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
