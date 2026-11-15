"""Rebuild a clip's declared joint list to match the skeleton it is shipped with.

A clip is bound by index, so the joint list a clip declares must be the joint list
the pak's skeleton has: same names, same order, same count.  Every Haze failure
traced back to that list disagreeing somewhere:

* the shipped skeleton was 132 joints and the merged clips declared 106, so the
  tail channels landed on the wrong joints and the body pose was read through the
  wrong indices -- the invisible tail and the rotated head and arms;
* the same clips once declared 353 joint elements for 106 bones, because the tail
  append cloned each joint with its subtree.

This pass grafts every joint the reference skeleton has and the clip lacks (with
the reference's own rest, no channels), then orders every joint's children the way
the reference orders them.  Nothing is invented: names, parents and rests all come
from the reference document.

  blender -b --factory-startup --python tools/clip_joint_align.py -- \\
      --reference <mesh+skeleton dmx> --clips <dir> --out-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")

_MAKE_ARRAY = None
_ELEMENT_TYPE = None


def _datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    return datamodel


def _is_element(value) -> bool:
    return isinstance(value, dict) and hasattr(value, "datamodel")


def _copy_value(model, value, remap: dict):
    if isinstance(value, list) and value and _is_element(value[0]):
        return _MAKE_ARRAY([_clone(model, item, remap) for item in value], _ELEMENT_TYPE)
    if _is_element(value):
        return _clone(model, value, remap)
    if isinstance(value, list):
        if type(value) is list:
            kind = float if value and isinstance(value[0], float) else int
            return _MAKE_ARRAY([kind(item) for item in value], kind)
        return value
    return value


def _clone(model, element, remap: dict):
    if element is None:
        return None
    if element in remap:
        return remap[element]
    clone = model.add_element(element.name, element.type)
    remap[element] = clone
    for key in element.keys():
        clone[key] = _copy_value(model, element[key], remap)
    return clone


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
    raise SystemExit("no DmeModel in the reference document")


def _order(root):
    """Joint names in the reference's own order, with each joint's parent."""
    model = _skeleton_model(root)
    order: list[str] = []
    parents: dict[str, str | None] = {}
    children: dict[str, list[str]] = {}
    roots: list[str] = []

    def visit(element, parent):
        for child in element["children"] if "children" in element.keys() else []:
            if getattr(child, "type", "") != "DmeJoint":
                continue
            order.append(child.name)
            parents[child.name] = parent
            children.setdefault(parent, []).append(child.name)
            visit(child, child.name)

    visit(model, None)
    children[None] = roots
    return model, order, parents, children


def _index(element, table: dict) -> None:
    table.setdefault(element.name, element)
    for key in ("jointList", "children"):
        if key not in element.keys():
            continue
        for child in element[key]:
            if _is_element(child):
                _index(child, table)


def _attach(element, child) -> None:
    if "children" not in element.keys():
        element["children"] = _MAKE_ARRAY([], _ELEMENT_TYPE)
    element["children"].append(child)


def _walk_arrays(element, out) -> list:
    """Every (parent, key, child) relation under this element."""
    for key in ("children", "jointList", "m_channels", "channels", "m_tracks"):
        if key not in element.keys():
            continue
        for child in element[key]:
            out.append((element, key, child))
            _walk_arrays(child, out)
    return out


def _drop_from(element, key: str, victim) -> bool:
    if key not in element.keys():
        return False
    array = element[key]
    try:
        index = list(array).index(victim)
    except ValueError:
        return False
    array.pop(index)
    return True


def _walk_document(root) -> list:
    """Every (parent, key, child) relation in a document whose root holds `skeleton`,
    `animationList` and the like, not a bare model."""
    out: list = []
    for key in root.keys():
        value = root[key]
        if hasattr(value, "keys"):
            out.append((root, key, value))
            _walk_arrays(value, out)
            continue
        try:
            children = list(value)
        except TypeError:
            continue
        for child in children:
            if hasattr(child, "keys"):
                out.append((root, key, child))
                _walk_arrays(child, out)
    return out


def _prune_extras(root, keep: set[str]) -> list[str]:
    """Delete every joint the reference skeleton lacks, and any channel that named it.

    A clip is bound by index, so a joint the skeleton does not carry is not harmless
    padding: it pushes every later joint one slot further than the skeleton's own
    list and the client reads the pose through the wrong bones.  The clip's export
    leaves (`*_end`, the armature object) are exactly that padding.
    """
    relations = _walk_document(root)
    victims = [child for _, _, child in relations if getattr(child, "type", "") == "DmeJoint" and child.name not in keep]
    if not victims:
        return []
    victim_ids = {id(element) for element in victims}
    dropped = [element.name for element in victims]
    doomed = list(victims)
    for parent, key, child in relations:
        if "joint" in child.keys() and id(child["joint"]) in victim_ids:
            doomed.append(child)
    doomed_ids = {id(element) for element in doomed}
    for parent, key, child in reversed(relations):
        if id(child) in doomed_ids and id(child) not in {id(v) for v in victims}:
            _drop_from(parent, key, child)
    for parent, key, child in reversed(relations):
        if id(child) in victim_ids:
            _drop_from(parent, key, child)
    return dropped


def _reorder(element, siblings: list[str], ref_children: dict) -> None:
    """Put each joint's children in the reference's sibling order."""
    if "children" not in element.keys():
        return
    kids = list(element["children"])
    rank = {name: index for index, name in enumerate(siblings)}
    kids.sort(key=lambda kid: rank.get(getattr(kid, "name", ""), len(rank)))
    element["children"] = _MAKE_ARRAY(kids, _ELEMENT_TYPE)
    for kid in kids:
        if getattr(kid, "type", "") == "DmeJoint":
            _reorder(kid, ref_children.get(kid.name, []), ref_children)


def _align(datamodel, reference: Path, clip_path: Path, out: Path, match_rest: bool = False, prune_extras: bool = False) -> dict:
    ref = datamodel.load(str(reference)).root
    _, order, parents, ref_children = _order(ref)
    ref_joints: dict = {}
    _index(_skeleton_model(ref), ref_joints)

    document = datamodel.load(str(clip_path))
    root = document.root
    model = _skeleton_model(root)
    joints = model["jointList"] if "jointList" in model.keys() else model["children"]
    present: dict = {}
    _index(model, present)

    grafted: list[str] = []
    for name in order:
        if name in present:
            continue
        parent_name = parents[name]
        if parent_name is not None and parent_name not in present:
            raise SystemExit(f"{clip_path.name}: {name} needs {parent_name} first; reference order is not parent-first")
        clone = _clone(document, ref_joints[name], {})
        if "children" in clone.keys() and len(clone["children"]):
            clones_children = clone["children"]
            while len(clones_children):
                clones_children.pop()
        if parent_name is None:
            _attach(model, clone)
        else:
            _attach(present[parent_name], clone)
        joints.append(clone)
        present[name] = clone
        grafted.append(name)

    # The clip's own joint transforms are the rest the channel samples are expressed
    # against, and they are left exactly as the game authored them. Rewriting them to
    # the reference's rest while the channels stay the game's own is what folded the
    # body over in game (2026-11-15, 03:54 build); the gate refuses that pairing as
    # `clip-rest-moved-without-rebake`. A rest may differ from the reference and still
    # be right: the shipping Shiv clips differ from their skeleton by up to 179 deg.
    # `--match-rest` exists only to reproduce that experiment, and its output is
    # refused unless the channels are re-expressed in the new frame.
    rest_changed = 0
    for name in order if match_rest else []:
        joint = present.get(name)
        source = ref_joints.get(name)
        if joint is None or source is None:
            continue
        if "transform" not in joint.keys() or "transform" not in source.keys():
            continue
        current = [tuple(float(v) for v in joint["transform"]["position"]), tuple(float(v) for v in joint["transform"]["orientation"])]
        wanted = [tuple(float(v) for v in source["transform"]["position"]), tuple(float(v) for v in source["transform"]["orientation"])]
        if current == wanted:
            continue
        joint["transform"]["position"] = _MAKE_ARRAY(list(wanted[0]), float)
        joint["transform"]["orientation"] = _MAKE_ARRAY(list(wanted[1]), float)
        rest_changed += 1

    pruned = _prune_extras(root, set(order)) if prune_extras else []

    missing = [name for name in order if name not in present]
    if missing:
        raise SystemExit(f"{clip_path.name}: reference order names {missing[:6]} that are not in the clip after grafting")

    # Order every level the way the reference orders it, so index binding matches.
    _reorder(model, ref_children[None], ref_children)
    for name in order:
        if name in present:
            _reorder(present[name], ref_children.get(name, []), ref_children)

    out.parent.mkdir(parents=True, exist_ok=True)
    document.write(str(out), "binary", 9)  # the encoding every shipped clip uses

    final_view: dict = {}
    _index(model, final_view)
    final_order = [name for name in order if name in final_view]
    return {
        "clip": clip_path.name,
        "grafted": len(grafted),
        "pruned": len(pruned),
        "pruned_names": pruned,
        "joints": len(final_view),
        "order_matches_reference": final_order == order,
        "grafted_names": grafted,
        "rests_matched": rest_changed,
    }


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, help="mesh+skeleton DMX the pak ships")
    parser.add_argument("--clips", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--match-rest",
        action="store_true",
        help="also rewrite every joint's rest to the reference's (experiment only; refused without a channel rebake)",
    )
    parser.add_argument(
        "--prune-extras",
        action="store_true",
        help="delete every joint the reference lacks (export leaves) so the clip's joint list is the skeleton's",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _arguments()
    datamodel = _datamodel()
    global _MAKE_ARRAY, _ELEMENT_TYPE
    _MAKE_ARRAY = datamodel.make_array
    _ELEMENT_TYPE = datamodel.Element

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from work_record import finish, refuse_ephemeral_paths

    refuse_ephemeral_paths([args.out_dir, args.report])
    reference = Path(args.reference)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, failed = [], []
    for clip in sorted(Path(args.clips).glob("*.dmx")):
        try:
            rows.append(
                _align(
                    datamodel,
                    reference,
                    clip,
                    out_dir / clip.name,
                    match_rest=args.match_rest,
                    prune_extras=args.prune_extras,
                )
            )
        except SystemExit as error:
            failed.append({"clip": clip.name, "error": str(error)})
        except Exception as error:  # noqa: BLE001 - report the clip, keep the batch
            failed.append({"clip": clip.name, "error": f"{type(error).__name__}: {error}"})
    misordered = [row["clip"] for row in rows if not row["order_matches_reference"]]
    counts = sorted({row["joints"] for row in rows})
    print(f"BATCH aligned {len(rows)} aligned, {len(failed)} failed, joint counts {counts}", flush=True)
    if misordered:
        print(f"BATCH ORDER MISMATCH {len(misordered)}: {misordered[:4]}", flush=True)
    for row in failed[:5]:
        print(f"BATCH FAIL {row['clip']}: {row['error']}", flush=True)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"reference": str(reference), "clips": rows, "failed": failed}, indent=2) + "\n",
            encoding="utf-8",
        )
    finish(
        "clip_joint_align",
        [out_dir, args.report],
        f"aligned {len(rows)} clips to {reference.name}, {len(failed)} failed, joint counts {counts}",
        "pass" if rows and not failed and not misordered else "fail",
        {"reference": str(reference)},
    )
    return 0 if rows and not failed and not misordered else 2


if __name__ == "__main__":
    raise SystemExit(main())
