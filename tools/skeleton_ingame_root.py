"""Put the game's own root and pelvis rest into the 168-bone tail skeleton.

Measured: our tail skeleton differs from the game's in exactly two joints.
`root_motion` is identity where the game carries the authored rotation, and
`pelvis` sits at `(0, 0, 61.52)` with a negated orientation where the game has
`(0, 61.52, 0)` and `(0.5, 0.5, 0.5, 0.5)`. A build compiled on the game's rest
(140 bones plus the tail chain) lost the look-up rotation the owner reported, and
also lost the tail: the model's own skeleton has 168 bones, so a 147-bone skeleton
does not match it.

This keeps the 168-bone skeleton the model expects and replaces only those two
rests with the game's, which is the part that decides how an additive aim rotation
composes. Every other joint, the parent tree, and the tail chain are untouched.

  blender -b --python tools/skeleton_ingame_root.py -- \
      --skel <tailbones.dmx> --game <game shiv_skel.dmx> --out <out.dmx> [--report <json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
TARGETS = ("root_motion", "pelvis")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skel", required=True)
    parser.add_argument("--game", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--encoding", default="binary")
    parser.add_argument("--encoding-ver", type=int, default=9)
    # The tail chain was authored against the old pelvis frame; the game's pelvis
    # is a 120-degree rotation about (1,1,1) away from it, so the tail rest has to
    # be re-expressed or it sits inside the body.
    parser.add_argument("--tail-rotate", default="")
    # The model's own bind skeleton has `pelvis` at the top level, beside
    # `root_motion`, not under it. The authored 90-degree `root_motion` rotation
    # therefore never reaches the body: that is why the model stands upright, and
    # why parenting pelvis under root_motion lays the body flat.
    parser.add_argument("--pelvis-root", action="store_true")
    # The model's bind pelvis is the Z-up rest this skeleton already carries, so
    # only the root rotation is missing from it; this leaves the pelvis rest alone.
    parser.add_argument("--root-only", action="store_true")
    return parser.parse_args(argv)


TAIL = ("tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end")


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _rotate_vector(q, vector):
    x, y, z, w = q
    vx, vy, vz = (float(vector[0]), float(vector[1]), float(vector[2]))
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def _joints(root):
    skeleton = root["skeleton"]
    return skeleton["jointList"] if "jointList" in skeleton else skeleton["children"]


def _by_name(model) -> dict:
    return {joint.name: joint for joint in _joints(model.root)}


def _set_vector(vector, values) -> None:
    for index, value in enumerate(values):
        vector[index] = float(value)


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel

    skel = datamodel.load(args.skel)
    game = datamodel.load(args.game)
    ours = _by_name(skel)
    theirs = _by_name(game)

    changed = {}
    for name in (("root_motion",) if args.root_only else TARGETS):
        if name not in ours or name not in theirs:
            raise RuntimeError(f"{name} is missing from one of the skeletons")
        mine = ours[name]["transform"]
        theirs_transform = theirs[name]["transform"]
        before = {
            "position": [round(float(value), 4) for value in mine["position"]],
            "orientation": [round(float(value), 4) for value in mine["orientation"]],
        }
        _set_vector(mine["position"], theirs_transform["position"])
        _set_vector(mine["orientation"], theirs_transform["orientation"])
        after = {
            "position": [round(float(value), 4) for value in mine["position"]],
            "orientation": [round(float(value), 4) for value in mine["orientation"]],
        }
        changed[name] = {"before": before, "after": after}

    if args.pelvis_root:
        root_joint = ours["root_motion"]
        pelvis_joint = ours["pelvis"]
        children = root_joint["children"]
        kept = [child for child in children if getattr(child, "name", "") != "pelvis"]
        removed = len(children) - len(kept)
        while len(children):
            children.pop()
        for child in kept:
            children.append(child)
        container = skel.root["skeleton"]
        siblings = container["children"]
        siblings.append(pelvis_joint)
        changed["pelvis_to_root"] = {"removed_from_root_motion": removed, "siblings": len(siblings)}

    if args.tail_rotate:
        q = tuple(float(part) for part in args.tail_rotate.replace(";", ",").split(",") if part.strip())
        if len(q) != 4:
            raise SystemExit("--tail-rotate needs x,y,z,w")
        rotated = []
        for name in TAIL:
            joint = ours[name]["transform"]
            position = _rotate_vector(q, joint["position"])
            orientation = _qmul(q, tuple(float(value) for value in joint["orientation"]))
            _set_vector(joint["position"], position)
            _set_vector(joint["orientation"], orientation)
            rotated.append(name)
        changed["tail_rotated"] = rotated

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    skel.write(str(out), args.encoding, args.encoding_ver)
    joints = _joints(datamodel.load(str(out)).root)
    report = {
        "skel": args.skel,
        "game": args.game,
        "out": str(out),
        "bytes": out.stat().st_size,
        "joints": len(joints),
        "changed": changed,
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"ROOTREST {out.name} {report['bytes']}b joints={report['joints']} changed={sorted(changed)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
