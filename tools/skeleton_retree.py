"""Re-tree a skeleton DMX to a parent map, keeping every joint's world pose.

The model the client binds (`m_modelSkeleton`) is a tree; the animation skeleton is another tree.
When they disagree about a joint's parent, the clip drives that joint from one frame while the mesh
was skinned under another — the head, arms and tail rotate.  The one pair measured correct in game is
Shiv's, where model and skeleton carry the same 168 bones in the same slots with the same parents.

The parent map comes from `skeleton_model_order_probe.model_bone_tree`, dumped to JSON:

    blender -b --factory-startup --python tools/skeleton_retree.py -- \
        --skeleton <in.dmx> --parents <parents.json> --out <out.dmx> --report <json>

World poses are preserved by construction: each joint's local rest is recomputed as
`inverse(new_parent_world) @ old_world`, where every world is read from the input document.  The
tool re-reads its own output and refuses when any joint moved, when the written tree is not the
requested one, or when a joint is left out of the tree.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


def datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel as module  # noqa: WPS433

    return module


def _model(root):
    for key in root.keys():
        child = root[key]
        if getattr(child, "type", "") == "DmeModel":
            return child
    raise SystemExit("skeleton-retree-needs-dme-model")


def _pair(transform):
    from mathutils import Quaternion, Vector  # noqa: WPS433

    position = transform["position"]
    orientation = transform["orientation"]
    if len(position) == 1:
        position = position[0]
    if len(orientation) == 1:
        orientation = orientation[0]
    # The file stores x, y, z, w (`weaponHand_L` identity reads [0, 0, 0, 1]) and mathutils
    # takes w, x, y, z.  Reading the tuple as-is made every orientation wrong, which is why
    # the first re-tree attempt reported 129 joints moving by up to 10.7 units.
    return Vector(tuple(position)), Quaternion((orientation[3], orientation[0], orientation[1], orientation[2]))


def _local(joint):
    from mathutils import Matrix  # noqa: WPS433

    position, quaternion = _pair(joint["transform"])
    return Matrix.Translation(position) @ quaternion.to_matrix().to_4x4()


def _walk(model):
    found: list = []
    parents: dict[str, str | None] = {}

    def visit(node, name):
        for child in node["children"]:
            found.append(child)
            parents[child.name] = name
            visit(child, child.name)

    visit(model, None)
    return found, parents


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--parents", required=True, help="JSON {joint: parent or null}")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--object-root",
        default="",
        help="the extraction's own armature object (a DAG, not a bone) to leave out of the "
        "skeleton; every other joint must be placed by --parents or the tool refuses",
    )
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    from mathutils import Matrix  # noqa: WPS433

    module = datamodel()
    loaded = module.load(args.skeleton)
    model = _model(loaded.root)
    joints, old_parents = _walk(model)
    dropped = {args.object_root.strip()} if args.object_root.strip() else set()
    by_name = {joint.name: joint for joint in joints if joint.name not in dropped}
    wanted = json.loads(Path(args.parents).read_text(encoding="utf-8"))
    wanted = {name: parent for name, parent in wanted.items() if name in by_name}
    missing = [name for name in by_name if name not in wanted]
    if missing:
        raise SystemExit(f"skeleton-retree-parents-incomplete: {missing[:6]}")

    world: dict[str, object] = {}

    def world_of(name: str):
        if name not in world:
            parent = old_parents.get(name)
            world[name] = (world_of(parent) if parent else Matrix.Identity(4)) @ _local(by_name[name])
        return world[name]

    for name in by_name:
        world_of(name)

    # Write the new locals.  Everything is computed from the input document before any write.
    new_local: dict[str, object] = {}
    for name, parent in wanted.items():
        base = world[parent] if parent else Matrix.Identity(4)
        new_local[name] = base.inverted() @ world[name]

    for name, matrix in new_local.items():
        quaternion = matrix.to_quaternion()
        by_name[name]["transform"]["position"] = module.Vector3(tuple(matrix.to_translation()))
        by_name[name]["transform"]["orientation"] = module.Quaternion(
            (quaternion[1], quaternion[2], quaternion[3], quaternion[0])
        )

    children: dict[str, list[str]] = {name: [] for name in by_name}
    roots: list[str] = []
    for name, parent in wanted.items():
        if parent and parent in children:
            children[parent].append(name)
        else:
            roots.append(name)
    element_type = type(next(iter(by_name.values())))
    for name, joint in by_name.items():
        joint["children"] = module.make_array([by_name[child] for child in children[name]], element_type)
    model["children"] = module.make_array([by_name[name] for name in roots], element_type)
    # `jointList` is the slot order a clip and a mask bind by, so it is rewritten too: leaving the
    # input's list behind kept the extraction's `haze_body` object in slot order (132 joints) while
    # the tree carried 131.
    if "jointList" in model.keys():
        listed = [joint.name for joint in model["jointList"]]
        kept = [name for name in listed if name in by_name]
        kept += [name for name in by_name if name not in set(kept)]
        model["jointList"] = module.make_array([by_name[name] for name in kept], element_type)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    loaded.write(str(out), "binary", 9)

    check = module.load(str(out))
    check_model = _model(check.root)
    check_joints, check_parents = _walk(check_model)
    check_by_name = {joint.name: joint for joint in check_joints}
    refused_parents = [
        name for name, parent in wanted.items() if check_parents.get(name) != parent
    ]
    if refused_parents:
        raise SystemExit(f"skeleton-retree-wrote-another-tree: {refused_parents[:6]}")

    moved = []

    def check_world(name: str):
        parent = check_parents.get(name)
        base = check_world(parent) if parent else Matrix.Identity(4)
        return base @ _local(check_by_name[name])

    for name in wanted:
        delta = max(
            abs(a - b)
            for row_a, row_b in zip(check_world(name), world[name])
            for a, b in zip(row_a, row_b)
        )
        if delta > 0.01:
            moved.append((name, round(delta, 4)))
    if moved:
        raise SystemExit(f"skeleton-retree-moved-the-pose: {moved[:6]}")

    report = {
        "skeleton": str(args.skeleton),
        "parents": str(args.parents),
        "out": str(out),
        "joints": len(by_name),
        "roots": roots,
        "reparented": sum(1 for name, parent in wanted.items() if old_parents.get(name) != parent),
        "pose_moved": 0,
        "bytes": out.stat().st_size,
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"SKELETON-RETREE {out.name} joints={report['joints']} roots={len(roots)} "
        f"reparented={report['reparented']} pose_moved=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
