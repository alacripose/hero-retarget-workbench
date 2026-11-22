"""Remove joint elements that a DMX document declares more than once.

An S2V mesh export, and a merge of two rigs into one export, can write the same
bone as two joint elements.  The compiler then writes each join twice, and every
mask and clip that binds by index lands on the wrong one: this is the shape behind
the invisible tail and the rotated head and arms on Haze, measured as
**167 joint elements for 131 bones** in `haze_model_tail.dmx`.

The first declaration of a name is kept, in place.  Children of a later duplicate
are moved under the kept joint, so nothing is lost and nothing is invented.

  blender -b --factory-startup --python tools/dmx_dedupe_joints.py -- \\
      --dmx <file> [<file> ...] [--report <json>]
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


def _skeleton_model(root):
    if "skeleton" in root.keys():
        return root["skeleton"]
    stack = [root]
    while stack:
        node = stack.pop()
        if getattr(node, "type", "") == "DmeModel":
            return node
        for child in node["children"] if "children" in node.keys() else []:
            stack.append(child)
    raise SystemExit("no DmeModel")


def _joints_in_order(element) -> list:
    found = []
    for child in element["children"] if "children" in element.keys() else []:
        if getattr(child, "type", "") == "DmeJoint":
            found.append(child)
            found.extend(_joints_in_order(child))
    return found


def _dedupe_children(element, kept: dict, removed: list) -> None:
    """Rewrite every `children` list: first declaration wins, later ones fold in."""
    if "children" not in element.keys():
        return
    children = list(element["children"])
    survivors = []
    for child in children:
        if getattr(child, "type", "") != "DmeJoint":
            survivors.append(child)
            continue
        name = child.name
        if name in kept:
            keeper = kept[name]
            # Move this duplicate's own children under the kept joint.
            for grandchild in list(child["children"]) if "children" in child.keys() else []:
                if getattr(grandchild, "type", "") == "DmeJoint" and grandchild.name in kept:
                    continue
                if "children" not in keeper.keys():
                    keeper["children"] = _MAKE_ARRAY([], _ELEMENT_TYPE)
                keeper["children"].append(grandchild)
            removed.append(name)
            continue
        kept[name] = child
        survivors.append(child)
    element["children"] = _MAKE_ARRAY(survivors, _ELEMENT_TYPE)
    for child in survivors:
        if getattr(child, "type", "") == "DmeJoint":
            _dedupe_children(child, kept, removed)


def _dedupe(datamodel, path: Path) -> dict:
    document = datamodel.load(str(path))
    model = _skeleton_model(document.root)
    before = _joints_in_order(model)
    kept: dict = {}
    removed: list[str] = []
    _dedupe_children(model, kept, removed)

    # `jointList` is the flat list every consumer reads; rebuild it to the kept set,
    # in the document's own traversal order, so no duplicate survives there either.
    if "jointList" in model.keys():
        order = []
        for joint in _joints_in_order(model):
            if joint.name not in order:
                order.append(joint.name)
        by_name = {}
        for joint in _joints_in_order(model):
            by_name.setdefault(joint.name, joint)
        model["jointList"] = _MAKE_ARRAY([by_name[name] for name in order], _ELEMENT_TYPE)

    after = _joints_in_order(model)
    document.write(str(path), "binary", 9)
    return {
        "path": str(path),
        "elements_before": len(before),
        "elements_after": len(after),
        "removed": len(removed),
        "duplicated_names": sorted({name for name in removed}),
    }


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--dmx", nargs="+", required=True)
    parser.add_argument("--report", default="")
    return parser.parse_args(argv)


def main() -> int:
    args = _arguments()
    datamodel = _datamodel()
    global _MAKE_ARRAY, _ELEMENT_TYPE
    _MAKE_ARRAY = datamodel.make_array
    _ELEMENT_TYPE = datamodel.Element
    rows = []
    failed = []
    for path in (Path(item) for item in args.dmx):
        try:
            rows.append(_dedupe(datamodel, path))
        except Exception as error:  # noqa: BLE001 - report the file, keep the batch
            failed.append({"path": str(path), "error": f"{type(error).__name__}: {error}"})
    for row in rows:
        print(
            f"DEDUPE {Path(row['path']).name}: {row['elements_before']} -> {row['elements_after']} elements, "
            f"{row['removed']} duplicates removed",
            flush=True,
        )
    for row in failed:
        print(f"DEDUPE FAIL {row['path']}: {row['error']}", flush=True)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"files": rows, "failed": failed}, indent=2) + "\n", encoding="utf-8")
    return 0 if rows and not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
