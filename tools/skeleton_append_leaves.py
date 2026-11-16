"""Append the mesh's `*_end` leaves after every other joint of a skeleton document.

The game's own `haze_skel.dmx` carries 98 joints and its body mesh weights 24 more leaves
(`head_end`, `finger_thumb_end_L`, `head_end`, `ball_end_L`, …) that only the **model document**
declares.  A skeleton we ship must name them or the client has no slot to bind those weights to
(`mesh-joint-not-in-skeleton`), and this port has already paid for the alternative twice:

* placing a leaf next to its parent in the tree moved `hand_L` from slot 20 to 21 and `hand_R`
  from 53 to 61, and the head, arms and tail rendered rotated (v15, 2026-11-16).  The client binds
  clips by index, so any joint inserted before another moves every index after it.
* the pinned Shiv skeleton (`pak93_dir.vpk`, sha256 `01efc18e…`) is the game's animation skeleton
  with the tail appended **after every stock joint, nothing re-ordered**, and its head, arms and
  tail are correct.

So the leaves go at the very end, as children of the model, exactly like the tail chain: the game's
98 keep slots 0..97, the tail takes 98..106, and the leaves fill 107.. and cannot move either.

  blender -b --factory-startup --python tools/skeleton_append_leaves.py -- \\
      --skeleton <doc.dmx> --mesh <haze_body.dmx> --out <doc.dmx> [--report <json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for entry in (str(REPO), str(REPO / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


def _datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    return datamodel


def _model(root):
    """The `DmeModel` this document keeps its joints in.

    A skeleton document keeps it under `skeleton`; a mesh document keeps its bind under `model`.
    """
    if "skeleton" in root.keys():
        return root["skeleton"]
    if "model" in root.keys():
        return root["model"]
    return root


def _joint_list(node):
    return node["jointList"] if "jointList" in node.keys() else node["children"]


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--mesh", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--nest-parents",
        action="store_true",
        help="hang each leaf under its parent bone instead of the root (the pinned Shiv shape)",
    )
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    datamodel = _datamodel()
    # `_clone` resolves nested element references through these two module globals.
    import dmx_tail_append as append_module  # noqa: WPS433

    append_module._MAKE_ARRAY = datamodel.make_array
    append_module._ELEMENT_TYPE = datamodel.Element
    _clone = append_module._clone

    from mathutils import Matrix, Quaternion, Vector  # noqa: WPS433

    def _transform_world(node, parents_world):
        transform = node["transform"] if "transform" in node.keys() else None
        if transform is None:
            return Matrix.Identity(4)
        position = transform["position"]
        if len(position) == 1:
            position = position[0]
        orientation = transform["orientation"]
        if len(orientation) == 1:
            orientation = orientation[0]
        local_ = Matrix.Translation(Vector(tuple(position))) @ Quaternion(tuple(orientation)).to_matrix().to_4x4()
        return (parents_world or Matrix.Identity(4)) @ local_

    def _worlds(model_element):
        worlds: dict[str, object] = {}

        def walk(node, parent_world):
            for child in node["children"] if "children" in node.keys() else []:
                if getattr(child, "type", "") != "DmeJoint":
                    continue
                worlds[child.name] = _transform_world(child, parent_world)
                walk(child, worlds[child.name])

        walk(model_element, None)
        return worlds

    document = datamodel.load(args.skeleton)
    model = _model(document.root)
    listed = _joint_list(model)
    names = [joint.name for joint in listed]
    # "Present" is measured on the TREE, not on `jointList`: a mesh leaf whose name is already
    # reachable must not be cloned again, or the document declares the same joint twice and the
    # gate refuses `skeleton-duplicate-joints` (measured on the first run of this tool).
    reachable: list[str] = []

    def _walk(node):
        for child in node["children"] if "children" in node.keys() else []:
            if getattr(child, "type", "") != "DmeJoint":
                continue
            reachable.append(child.name)
            _walk(child)

    _walk(model)
    present = set(reachable) | set(names)

    present_by_name: dict = {}

    def _index(node):
        for child in node["children"] if "children" in node.keys() else []:
            present_by_name[child.name] = child
            _index(child)

    _index(model)
    root_name = model["children"][0] if "children" in model.keys() and len(model["children"]) else None
    host = root_name if getattr(root_name, "type", "") == "DmeJoint" else model
    added: list[dict] = []
    for mesh_path in args.mesh:
        mesh = datamodel.load(mesh_path)
        # The bind is `model` on a mesh document; `skeleton` there is the extraction's own copy and
        # sits in a different frame (using it left `head_end` 41.8 units off the mesh bind).
        mesh_skeleton = (
            mesh.root["model"]
            if "model" in mesh.root.keys()
            else _model(mesh.root)
        )
        for joint in _joint_list(mesh_skeleton):
            if joint.name in present:
                continue
            clone = _clone(document, joint, {})
            # `jointList` and `children` are often the same array in this document flavour, and a
            # clone added to both is declared twice (`skeleton-duplicate-joints`).
            # A cloned joint still references the donor's own `children` array, and appending it
            # as a leaf then walked the donor subtree a second time (measured: the walk grew from
            # 107 to 141 with `weaponHier_L_IKTARGET` repeated at four depths).
            if "children" in clone.keys():
                clone["children"] = datamodel.make_array([], datamodel.Element)
            # The donor's rest is expressed in the donor's tree; the clone hangs off this
            # document's root, so its rest is recomputed to keep the same world pose.  Without
            # this the gate refuses `skeleton-rest-differs-from-model` on every appended leaf.
            donor_worlds = _worlds(mesh_skeleton)
            host_world = _worlds(model).get(host.name) if getattr(host, "type", "") == "DmeJoint" else None
            leaf_world = donor_worlds.get(joint.name)
            if leaf_world is not None:
                local_ = (host_world.inverted() if host_world is not None else Matrix.Identity(4)) @ leaf_world
                clone["transform"]["position"] = datamodel.Vector3(tuple(local_.to_translation()))
                clone["transform"]["orientation"] = datamodel.Quaternion((lambda q: (q[1], q[2], q[3], q[0]))(local_.to_quaternion()))
            listed.append(clone)
            # The pinned Shiv skeleton keeps every `*_end` leaf beside its parent in the tree and
            # lists it after the body joints.  `--nest-parents` reproduces that: the leaf hangs off
            # the same bone it hangs off in the mesh, so its own local rest is already correct.
            donor_parents = {}
            for node in _joint_list(mesh_skeleton):
                for child in node["children"] if "children" in node.keys() else []:
                    donor_parents[child.name] = node.name
            parent_name = donor_parents.get(joint.name) if args.nest_parents else None
            if parent_name and parent_name in present_by_name:
                present_by_name[parent_name]["children"].append(clone)
            else:
                host["children"].append(clone)
            names.append(joint.name)
            present.add(joint.name)
            added.append({"joint": joint.name, "mesh": Path(mesh_path).name, "slot": len(names) - 1})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    document.write(str(out), "binary", 9)

    reread = datamodel.load(str(out)).root
    written = [joint.name for joint in _joint_list(_model(reread))]
    report = {
        "skeleton": args.skeleton,
        "meshes": args.mesh,
        "out": str(out),
        "bytes": out.stat().st_size,
        "joints": len(written),
        "added": added,
        "appended_at_end": all(
            written.index(entry["joint"]) >= len(names) - len(added) for entry in added
        ),
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"SKELETON-LEAVES {out.name} joints={report['joints']} appended={len(added)} "
        f"at_end={report['appended_at_end']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
