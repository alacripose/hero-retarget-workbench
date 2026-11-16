"""Flatten armature DAGs out of a skeleton DMX, keeping every joint's world pose.

**Measured, not assumed.** `artifacts/haze-tail/haze_tailbones.flat2.dmx` carries a
`DmeDag` named `DMF Tail` above the appended tail chain.  The model the client binds
has no such element: `skeleton_model_order_probe.model_bone_tree` reads 131 bones
and none of them is `DMF Tail`, so the tail bones' *world* pose in the skeleton is
the dag's transform composed with their own, while the model places them straight
under `pelvis`.  That is the tail that still rotates: the chain is right, its frame
is not.

A DMX tree uses nesting as parenting, so dropping a dag means promoting its joint
children to the dag's parent and composing the dag's local transform into each of
them:

    local(child) = local(dag) @ local(child)

The world pose of every promoted joint is unchanged by construction, and this tool
verifies that on read-back before it reports success.  Nothing else is touched: no
joint is renamed, moved in the list, or re-parented across a joint.

    blender -b --factory-startup --python tools/skeleton_flatten_dags.py -- \
        --skeleton <in.dmx> --out <out.dmx> --report artifacts/receipts/<name>.json
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


def _model(element):
    for key in element.keys():
        child = element[key]
        if getattr(child, "type", "") == "DmeModel":
            return child
    return None


def _children(node) -> list:
    return list(node["children"]) if "children" in node.keys() else []


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    from mathutils import Matrix, Quaternion, Vector  # noqa: WPS433

    module = datamodel()
    loaded = module.load(args.skeleton)
    model = _model(loaded.root)
    if model is None:
        raise SystemExit("skeleton-flatten-needs-dme-model")

    def read_local(joint):
        position = joint["transform"]["position"]
        orientation = joint["transform"]["orientation"]
        if len(position) == 1:
            position = position[0]
        if len(orientation) == 1:
            orientation = orientation[0]
        return (
            Matrix.Translation(Vector(tuple(position)))
            @ Quaternion(tuple(orientation)).to_matrix().to_4x4()
        )

    def world_of(element):
        parent = _parent_of.get(element.name)
        return (world_of(_by_name[parent]) if parent else Matrix.Identity(4)) @ read_local(element)

    _by_name: dict[str, object] = {}
    _parent_of: dict[str, str] = {}

    def index(node):
        for child in _children(node):
            _by_name[child.name] = child
            _parent_of[child.name] = node.name if getattr(node, "type", "") == "DmeJoint" else _parent_of.get(node.name)
            index(child)

    index(model)
    before = {name: world_of(element) for name, element in _by_name.items() if getattr(element, "type", "") == "DmeJoint"}

    promoted = 0

    def flatten(node):
        nonlocal promoted
        kids = _children(node)
        element_type = type(kids[0]) if kids else None
        rebuilt = []
        for child in kids:
            if getattr(child, "type", "") == "DmeDag":
                dag_local = read_local(child)
                grandchildren = _children(child)
                for grandchild in grandchildren:
                    if getattr(grandchild, "type", "") == "DmeJoint":
                        # world stays; the dag's transform moves into the joint's own rest.
                        desired = world_of(grandchild)
                        parent_world = (
                            world_of(node) if getattr(node, "type", "") == "DmeJoint" else Matrix.Identity(4)
                        )
                        local = parent_world.inverted() @ desired
                        grandchild["transform"]["position"] = module.Vector3(tuple(local.to_translation()))
                        quaternion = local.to_quaternion()
                        grandchild["transform"]["orientation"] = module.Quaternion(
                            (quaternion[1], quaternion[2], quaternion[3], quaternion[0])
                        )
                        promoted += 1
                    rebuilt.append(grandchild)
                # keep walking into what the dag carried
                flatten(child)
                continue
            rebuilt.append(child)
            flatten(child)
        if element_type is not None:
            node["children"] = module.make_array(rebuilt, element_type)

    flatten(model)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    loaded.write(str(out), "binary", 9)

    # Read back: every joint must keep its world pose, and no DAG may remain.
    check = module.load(str(out))
    check_model = _model(check.root)
    remaining = []

    def scan(node):
        for child in _children(node):
            if getattr(child, "type", "") == "DmeDag":
                remaining.append(child.name)
            scan(child)

    scan(check_model)
    check_by_name = {}
    check_parent = {}

    def index_check(node, parent):
        for child in _children(node):
            check_by_name[child.name] = child
            check_parent[child.name] = parent
            index_check(child, child.name if getattr(child, "type", "") == "DmeJoint" else parent)

    index_check(check_model, None)

    def check_world(name):
        parent = check_parent.get(name)
        base = check_world(parent) if parent else Matrix.Identity(4)
        return base @ read_local(check_by_name[name])

    moved = []
    for name, expected in before.items():
        actual = check_world(name)
        delta = max(
            abs(a - b)
            for row_a, row_b in zip(actual, expected)
            for a, b in zip(row_a, row_b)
        )
        if delta > 0.01:
            moved.append((name, round(delta, 4)))
    if remaining:
        raise SystemExit(f"skeleton-flatten-left-dags: {remaining[:6]}")
    if moved:
        raise SystemExit(f"skeleton-flatten-moved-the-pose: {moved[:6]}")

    report = {
        "skeleton": str(args.skeleton),
        "out": str(out),
        "joints": len(before),
        "promoted": promoted,
        "dags_removed": len(_by_name) - len(before),
        "pose_moved": 0,
        "bytes": out.stat().st_size,
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"SKELETON-FLATTEN {out.name} joints={report['joints']} promoted={promoted} "
        f"dags_removed={report['dags_removed']} pose_moved=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
