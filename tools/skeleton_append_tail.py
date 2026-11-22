"""Append a tail chain to the game's own skeleton, keeping its joint order.

The pinned Shiv skeleton is the game's animation skeleton with the tail joints
appended after every stock joint; nothing is re-ordered.  An export of the Blender
rig cannot be used for that: it carries an extra armature object joint and lists
the `*_end` leaves where Blender put them, so every index after the first
divergence moves, and the client binds clips by index.

  blender -b --python tools/skeleton_append_tail.py -- \
      --game-skel <haze_skel.dmx> --tail <tailbones.dmx> --out <haze_tailbones.dmx> [--report <json>]

The stock skeleton's bone masks are kept as they are; a mask that names a joint the
rig does not carry is reported, not silently rewritten.
"""

from __future__ import annotations
import os

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-skel", required=True)
    parser.add_argument("--tail", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--parent", default="pelvis")
    parser.add_argument("--extra", default="", help="comma-separated donor joints to carry over (e.g. weaponHand_L)")
    parser.add_argument("--extra-donor", default="", help="DMX that declares the --extra joints")
    parser.add_argument("--report", default="")
    return parser.parse_args(argv)


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    from dmx_tail_append import _clone, _copy_value, _is_element, _tail_chain  # noqa: WPS433

    global _MAKE_ARRAY, _ELEMENT_TYPE
    _MAKE_ARRAY = datamodel.make_array
    _ELEMENT_TYPE = datamodel.Element
    # `_clone` resolves nested element references through these two module globals.
    import dmx_tail_append as append_module

    append_module._MAKE_ARRAY = _MAKE_ARRAY
    append_module._ELEMENT_TYPE = _ELEMENT_TYPE

    game = datamodel.load(args.game_skel)
    tail = datamodel.load(args.tail)
    root = game.root
    skeleton = root["skeleton"]
    stock = skeleton["jointList"] if "jointList" in skeleton else skeleton["children"]
    stock_names = [joint.name for joint in stock]
    if args.parent not in stock_names:
        raise SystemExit(f"{args.parent!r} is not a joint of {args.game_skel}")

    tail_joints = tail.root["skeleton"]
    tail_list = tail_joints["jointList"] if "jointList" in tail_joints else tail_joints["children"]
    chain = _tail_chain(tail_list)
    if not chain:
        raise SystemExit("the tail file declares no tail chain")
    tail_by_name = {joint.name: joint for joint in tail_list}
    missing = [name for name in chain if name not in tail_by_name]
    if missing:
        raise SystemExit(f"the tail file lacks {missing}")

    remap: dict = {}
    # A mask in the game's own skeleton document can name a joint the mesh skeleton
    # does not carry (Haze's masks name weaponHand_L/R).  Shipping such a skeleton
    # makes the client log "Couldn't find bone ... while serializing bone mask" and
    # then crash, so the joint is carried over instead of the mask being edited.
    extras = [name.strip() for name in args.extra.split(",") if name.strip()]
    if extras:
        if not args.extra_donor:
            raise SystemExit("--extra needs --extra-donor")
        donor = datamodel.load(args.extra_donor)
        donor_skeleton = donor.root["skeleton"]
        donor_joints = donor_skeleton["jointList"] if "jointList" in donor_skeleton else donor_skeleton["children"]
        donor_by_name = {joint.name: joint for joint in donor_joints}
        for name in extras:
            if name in donor_by_name:
                joint = _clone(game, donor_by_name[name], remap)
                # A cloned joint that hangs off nothing is listed in the joint array
                # but not reachable from the root, so the compiler leaves it out of
                # the bone table: the game then logs "Couldn't find bone (...) while
                # serializing bone mask" and crashes.  parent it under its hand.
                host = None
                if name.endswith("_L") and "hand_L" in stock_names:
                    host = next(item for item in stock if item.name == "hand_L")
                elif name.endswith("_R") and "hand_R" in stock_names:
                    host = next(item for item in stock if item.name == "hand_R")
                if host is not None:
                    host["children"].append(joint)
                stock.append(joint)
                stock_names.append(name)
            elif name not in stock_names:
                raise SystemExit(f"{name!r} is in neither {args.game_skel} nor {args.extra_donor}")
    parent = next(joint for joint in stock if joint.name == args.parent)
    added = []
    for name in chain:
        if name in stock_names:
            added.append({"bone": name, "joint": "existing"})
            continue
        joint = _clone(game, tail_by_name[name], remap)
        parent["children"].append(joint)
        stock.append(joint)
        stock_names.append(name)
        added.append({"bone": name, "joint": "added"})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    game.write(str(out), "binary", 9)

    written = datamodel.load(str(out)).root["skeleton"]
    written_joints = written["jointList"] if "jointList" in written else written["children"]
    names = [joint.name for joint in written_joints]
    masks = []
    for key in written.keys():
        if "mask" in key.lower():
            masks.append(key)
    payload = {
        "game_skel": args.game_skel,
        "tail": args.tail,
        "out": str(out),
        "bytes": out.stat().st_size,
        "stock_joints": len(stock_names) - len([entry for entry in added if entry["joint"] == "added"]),
        "joints": len(names),
        "parent": args.parent,
        "chain": chain,
        "added": added,
        "order_preserved": names[: len(stock_names) - len(added)] == stock_names[: len(stock_names) - len(added)],
        "mask_keys": masks,
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"SKELETON {out.name} {payload['bytes']}b joints={payload['joints']} chain={len(chain)} masks={len(masks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
