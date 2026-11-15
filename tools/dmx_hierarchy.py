"""Print each joint's parent so two skeletons can be compared by hierarchy.

`dmx_joint_names.py` compares name order only.  The engine binds masks, clips and
the model skeleton by hierarchy as well, so a skeleton whose joints carry the
same names but different parents behaves differently.

  blender -b --python tools/dmx_hierarchy.py -- --dmx <file> [--dmx <file> ...] [--report <json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


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


def _parent(joint) -> str:
    for key in ("parent", "parentName"):
        try:
            value = joint[key]
        except Exception:
            continue
        if isinstance(value, str):
            return value
        return getattr(value, "name", "") or ""
    return ""


def main() -> int:
    args = _arguments()
    datamodel = _datamodel()
    payload = {}
    for path in args.dmx:
        model = datamodel.load(path)
        joints = _joints(model.root)
        parents = {joint.name: _parent(joint) for joint in joints}
        payload[path] = {"count": len(joints), "parents": parents}
        roots = [name for name, parent in parents.items() if not parent]
        print(f"HIERARCHY {Path(path).name} joints={len(joints)} roots={roots}", flush=True)
        for name in parents:
            if name.startswith("tail_") or name == "pelvis":
                print(f"  {name} <- {parents[name] or '(root)'}", flush=True)
    if len(payload) > 1:
        keys = list(payload)
        base = payload[keys[0]]["parents"]
        for other in keys[1:]:
            other_parents = payload[other]["parents"]
            shared = [name for name in base if name in other_parents]
            differing = [(name, base[name], other_parents[name]) for name in shared if base[name] != other_parents[name]]
            only_base = [name for name in base if name not in other_parents]
            print(
                f"COMPARE {Path(keys[0]).name} vs {Path(other).name}: shared {len(shared)} "
                f"differing_parents {len(differing)} only_in_base {len(only_base)}",
                flush=True,
            )
            for row in differing[:12]:
                print(f"  {row[0]}: {row[1]} != {row[2]}", flush=True)
            payload[other]["differing_parents"] = differing
            payload[other]["only_in_base"] = only_base
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
