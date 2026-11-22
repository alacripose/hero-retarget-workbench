"""Append every joint a render mesh declares that the model document lacks.

A model document's joint list is the skeleton the client binds meshes against, but
each `RenderMeshFile` carries its own joints: the hands and prop meshes here name
`magazine_L`, `finger_thumb_end_L`, `head_end` and friends that the body and tail
meshes never mention.  A joint a mesh weights but the model does not declare has no
slot to bind to; a joint the model declares and the mesh also declares must sit in the
same slot on both sides.

So: keep the model document's order byte-for-byte as it is, then append each missing
joint (with the declaring mesh's own rest and parent where that parent is already
present, otherwise as a root) after the last existing joint.  Appending at the end is
the only placement that cannot move a slot the meshes already bind by index.

  blender -b --factory-startup --python tools/skeleton_union.py -- \\
      --model <haze_model_tail.dmx> --meshes <a.dmx> --meshes <b.dmx> ... --out <union.dmx>
"""

from __future__ import annotations
import os

import argparse
import json
import sys
from pathlib import Path

PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))

_MAKE_ARRAY = None
_ELEMENT_TYPE = None


def _datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    return datamodel


def _model(root):
    return root["skeleton"] if "skeleton" in root.keys() else root


def _joint_list(model):
    return model["jointList"] if "jointList" in model.keys() else model["children"]


def _walk(element, parent=None, out=None):
    """Every joint in this document: the children tree first, then the flat jointList.

    A render mesh in this addon keeps its joints in the flat `jointList` (the guns declare
    `magazine_L/R`, the finger ends and `head_end` there, with no children tree), so a walk
    that only follows `children` silently reports "nothing to append" while the gate sees
    joints the model cannot resolve.
    """
    if out is None:
        out = []
    seen = {id(row[1]) for row in out}
    for child in element["children"] if "children" in element.keys() else []:
        if getattr(child, "type", "") != "DmeJoint":
            continue
        if id(child) not in seen:
            out.append((child.name, child, parent))
            seen.add(id(child))
        _walk(child, child.name, out)
    if "jointList" in element.keys():
        for child in element["jointList"]:
            if getattr(child, "type", "") != "DmeJoint" or id(child) in seen:
                continue
            out.append((child.name, child, None))
            seen.add(id(child))
    return out


def _clone(datamodel, element, remap):
    from clip_joint_align import _clone as clone_element  # noqa: WPS433

    return clone_element(datamodel, element, remap)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--meshes", action="append", default=[])
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    datamodel = _datamodel()
    global _MAKE_ARRAY, _ELEMENT_TYPE
    _MAKE_ARRAY, _ELEMENT_TYPE = datamodel.make_array, datamodel.Element
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    document = datamodel.load(args.model)
    model = _model(document.root)
    joints = _joint_list(model)
    present = {name for name, _, _ in _walk(model)}

    appended = []
    for mesh_path in args.meshes:
        mesh_doc = datamodel.load(mesh_path)
        mesh_model = _model(mesh_doc.root)
        for name, element, parent in _walk(mesh_model):
            if name in present:
                continue
            clone = _clone(datamodel, element, {})
            while "children" in clone.keys() and len(clone["children"]):
                clone["children"].pop()
            joints.append(clone)
            present.add(name)
            appended.append({"joint": name, "from": Path(mesh_path).name, "parent_in_mesh": parent})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    document.write(str(out), "binary", 9)
    total = len(_walk(_model(datamodel.load(str(out)).root)))
    print(f"UNION {out.name} {out.stat().st_size}b joints={total} appended={len(appended)}", flush=True)
    for row in appended[:8]:
        print(f"  + {row['joint']} (from {row['from']}, parent {row['parent_in_mesh']})", flush=True)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"model": args.model, "out": str(out), "joints": total, "appended": appended}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
