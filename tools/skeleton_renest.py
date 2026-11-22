"""Re-nest a skeleton in a target hierarchy while every bone keeps its world pose.

Two facts measured in game on 2026-11-16 constrain this, and they conflict unless the tree is
rebuilt rather than replaced:

* the body renders upright only when the skeleton's own tree is the one the mesh bind was authored
  in (the game's tree folded it: v10);
* the head, arms and tail render unrotated only when the skeleton's `jointList` is the walk order
  the model presents (v6 and v9 kept a list that disagreed with their walk by 81 and 88 joints).

A bone's local rest is relative to its parent, so re-parenting with the game's rest values moves
the body.  This tool re-parents and then recomputes each bone's local transform as
`inverse(new_parent_world) @ old_world`, so the world pose is unchanged by construction — and it
verifies that on read-back, refusing if any joint moves.

    blender -b --python tools/skeleton_renest.py -- --skeleton <ours.dmx> --to <game_skel.dmx> \
        --out <renested.dmx> --report artifacts/receipts/x.json
"""


from __future__ import annotations
import os

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))


def datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel as module  # noqa: WPS433

    return module


def _model(element):
    if "model" in element.keys():
        return element["model"]
    for key in element.keys():
        child = element[key]
        if getattr(child, "type", "") == "DmeModel":
            return child
    return None


def _children(node) -> list:
    return list(node["children"]) if "children" in node.keys() else []


def _joints(model) -> list:
    out: list = []

    def walk(node):
        for child in _children(node):
            out.append(child)
            walk(child)

    walk(model)
    return out


def _parents(model) -> dict[str, str]:
    out: dict[str, str] = {}
    for joint in _joints(model):
        for child in _children(joint):
            out[child.name] = joint.name
    return out


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--to", required=True, help="the document whose hierarchy and list to adopt")
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    from mathutils import Matrix, Quaternion, Vector  # noqa: WPS433

    module = datamodel()
    loaded = module.load(args.skeleton)
    model = _model(loaded.root)
    target = _model(module.load(args.to).root)
    if model is None or target is None:
        raise SystemExit("skeleton-renest-needs-dme-model")

    bones = {joint.name: joint for joint in _joints(model)}
    old_parents = _parents(model)
    target_parents = _parents(target)
    target_order = [joint.name for joint in _joints(target)]

    def read_pair(transform):
        """A position and a quaternion, whichever shape the document stores them in.

        The game's own skeleton stores a plain `Vector3`/`Quaternion`; this tool writes the
        single-element arrays the compiled model expects, so both shapes are read here.
        """
        position = transform["position"]
        if len(position) == 1:
            position = position[0]
        orientation = transform["orientation"]
        if len(orientation) == 1:
            orientation = orientation[0]
        # The file stores x, y, z, w (`weaponHand_L` identity reads [0, 0, 0, 1]) and mathutils
    # takes w, x, y, z.  Reading the tuple as-is made every orientation wrong, which is why
    # the first re-tree attempt reported 129 joints moving by up to 10.7 units.
    return Vector(tuple(position)), Quaternion((orientation[3], orientation[0], orientation[1], orientation[2]))

    def local(joint):
        position, q = read_pair(joint["transform"])
        return Matrix.Translation(position) @ q.to_matrix().to_4x4()

    world: dict[str, object] = {}

    def resolve(name: str):
        if name not in world:
            parent = old_parents.get(name)
            world[name] = (resolve(parent) if parent else Matrix.Identity(4)) @ local(bones[name])
        return world[name]

    for name in bones:
        resolve(name)

    adopted = [name for name in target_order if name in bones]
    extra = [name for name in bones if name not in set(target_order)]
    order = adopted + extra
    parents = {}
    for name in order:
        if name in target_parents:
            parents[name] = target_parents[name]
        elif name in extra:
            parents[name] = old_parents.get(name)
        else:
            parents[name] = old_parents.get(name)

    children: dict[str, list[str]] = {name: [] for name in order}
    roots: list[str] = []
    for name in order:
        parent = parents.get(name)
        if parent and parent in children:
            children[parent].append(name)
        else:
            roots.append(name)

    walked: list[str] = []

    def emit(name: str) -> None:
        walked.append(name)
        for child in children[name]:
            emit(child)

    for name in roots:
        emit(name)
    if sorted(walked) != sorted(order):
        raise SystemExit(f"skeleton-renest-incomplete: walked {len(walked)} of {len(order)} joints")
    order = walked

    def world_of(name: str):
        parent = parents.get(name)
        return (world_of(parent) if parent else Matrix.Identity(4)) @ local(bones[name])

    # Recompute every local so the world pose is unchanged under the new parent.
    for name in order:
        parent = parents.get(name)
        desired = world[name]
        parent_world = world[parent] if parent else Matrix.Identity(4)
        new_local = parent_world.inverted() @ desired
        # The documents store a plain `Vector3`/`Quaternion` here, not a one-element array; a
        # single-element array reads back as a wrapper the rest of the toolchain cannot use.
        bones[name]["transform"]["position"] = module.Vector3(tuple(new_local.to_translation()))
        bones[name]["transform"]["orientation"] = module.Quaternion((lambda q: (q[1], q[2], q[3], q[0]))(new_local.to_quaternion()))

    element_type = type(_joints(model)[0])
    for name in order:
        joint = bones[name]
        # Every joint gets its children array, including the leaves that had none: guarding this on
        # `"children" in joint.keys()` left 129 of 131 joints un-parented in the written document,
        # which reads back as a flat skeleton with every joint at the root.
        joint["children"] = module.make_array([bones[child] for child in children[name]], element_type)
    model["children"] = module.make_array([bones[name] for name in roots], element_type)
    if "jointList" in model.keys():
        model["jointList"] = module.make_array([bones[name] for name in order], element_type)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    loaded.write(str(out), "binary", 9)

    # Read back and prove the pose did not move: same world matrix for every joint.
    check = module.load(str(out))
    check_model = _model(check.root)
    check_bones = {joint.name: joint for joint in _joints(check_model)}
    check_parents = _parents(check_model)
    moved = []

    def check_world(name: str):
        parent = check_parents.get(name)
        base = check_world(parent) if parent else Matrix.Identity(4)
        position, q = read_pair(check_bones[name]["transform"])
        return base @ Matrix.Translation(position) @ q.to_matrix().to_4x4()

    for name in order:
        if name not in check_bones:
            moved.append((name, "missing"))
            continue
        delta = max(
            abs(a - b)
            for row_a, row_b in zip(check_world(name), world[name])
            for a, b in zip(row_a, row_b)
        )
        if delta > 0.01:
            moved.append((name, round(delta, 4)))
    if moved:
        raise SystemExit(f"skeleton-renest-moved-the-pose: {moved[:6]}")

    written = [joint.name for joint in check_model["jointList"]] if "jointList" in check_model.keys() else order
    report = {
        "skeleton": str(args.skeleton),
        "to": str(args.to),
        "out": str(out),
        "bones": len(order),
        "adopted": len(adopted),
        "appended": extra,
        "list_is_walk": written == order,
        "pose_moved": 0,
        "bytes": out.stat().st_size,
    }
    if args.report:
        target_path = Path(args.report)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"SKELETON-RENEST {out.name} bones={len(order)} adopted={len(adopted)} "
        f"appended={len(extra)} list_is_walk={report['list_is_walk']} pose_moved=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
