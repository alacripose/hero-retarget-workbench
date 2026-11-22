"""Build the shipped skeleton DMX from the game's own rest, plus the tail chain.

The clips are the game's own channel data, so the rest they are played against has
to be the game's rest too. Earlier builds compiled the skeleton from a Blender
export of the tail-bearing rig, and that rest is not the game's: `root_motion`
comes out identity instead of the authored rotation, and `pelvis` comes out Z-up
instead of the game's Y-up. An additive aim layer composes against that rest, so a
skeleton that differs there can carry every clip verbatim and still pitch the body
when the camera looks up.

This loads the game's skeleton DMX and appends the seven tail joints from the
tail-bearing one, keeping every body joint exactly as the game ships it. The tail
joints are children of `pelvis`, so their own local transforms are relative and do
not depend on the root convention.

  blender -b --python tools/skeleton_with_tail.py -- \
      --skel <game shiv_skel.dmx> --tail <tailbones.dmx> --out <out.dmx> [--report <json>]
"""

from __future__ import annotations
import os

import argparse
import json
import sys
from pathlib import Path

PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))
TAIL_BONES = ("tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skel", required=True)
    parser.add_argument("--tail", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--encoding", default="binary")
    parser.add_argument("--encoding-ver", type=int, default=9)
    return parser.parse_args(argv)


def _joints(root):
    skeleton = root["skeleton"]
    return skeleton["jointList"] if "jointList" in skeleton else skeleton["children"]


def _is_element(value) -> bool:
    return isinstance(value, dict) and hasattr(value, "datamodel")


def _clone(model, element, make_array, element_type, remap: dict):
    if element is None:
        return None
    if element in remap:
        return remap[element]
    clone = model.add_element(element.name, element.type)
    remap[element] = clone
    for key in element.keys():
        value = element[key]
        if isinstance(value, list) and value and _is_element(value[0]):
            clone[key] = make_array([_clone(model, item, make_array, element_type, remap) for item in value], element_type)
        elif _is_element(value):
            clone[key] = _clone(model, value, make_array, element_type, remap)
        else:
            clone[key] = value
    return clone


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel

    skel = datamodel.load(args.skel)
    tail = datamodel.load(args.tail)
    skel_joints = _joints(skel.root)
    tail_joints = _joints(tail.root)
    tail_by_name = {joint.name: joint for joint in tail_joints}
    have = {joint.name for joint in skel_joints}
    if any(name in have for name in TAIL_BONES):
        raise RuntimeError("the game skeleton already declares tail bones")

    pelvis = next((joint for joint in skel_joints if joint.name == "pelvis"), None)
    if pelvis is None:
        raise RuntimeError("the game skeleton has no pelvis")

    remap: dict = {}
    added = []
    for name in TAIL_BONES:
        joint = tail_by_name.get(name)
        if joint is None:
            raise RuntimeError(f"the tail skeleton lacks {name}")
        clone = _clone(skel, joint, datamodel.make_array, datamodel.Element, remap)
        pelvis["children"].append(clone)
        skel_joints.append(clone)
        added.append(name)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    skel.write(str(out), args.encoding, args.encoding_ver)

    joints = _joints(datamodel.load(str(out)).root)
    report = {
        "skel": args.skel,
        "tail": args.tail,
        "out": str(out),
        "bytes": out.stat().st_size,
        "joints": len(joints),
        "added": added,
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"SKELTON {out.name} {report['bytes']}b joints={report['joints']} added={len(added)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
