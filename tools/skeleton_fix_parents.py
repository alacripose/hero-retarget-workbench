"""Give a grafted skeleton document the game's own parents, and chain the tail.

Measured on `haze_model_tail.dmx`, the skeleton the last Haze pak shipped:

    pelvis          root_motion       ->  None              (became a root)
    weaponHand_L    arm_L_IKTARGET    ->  hand_L
    weaponHand_R    arm_R_IKTARGET    ->  hand_R
    tail_0..tail_7  chained in Tengu  ->  all children of pelvis (flat)

Every one of those is a frame change, not a detail. `pelvis` as a root bypasses
`root_motion`, which puts the body under the pelvis in the wrong frame; `weaponHand`
under `hand_L` instead of `arm_L_IKTARGET` is the head-and-arms rotation; a flat
tail chain has no chain to swing, so the tail lies down.

This tool restores the game's parent for every joint the stock skeleton has, and
chains the tail joints in the order the tail mesh weights them:

    tail_0 <- pelvis, tail_1 <- tail_0, ..., tail_end <- tail_7

Rests and channels are untouched; only `children` lists are rebuilt, so a joint's
own head stays where the mesh was skinned to it.

  blender -b --python tools/skeleton_fix_parents.py -- \
      --stock <game skeleton dmx> --doc <mesh+skeleton dmx> --tail <tail mesh dmx> \
      --out <dmx> --report <json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
for candidate in (PULSE_DIR, REPO / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def _datamodel():
    from pulse_src_ops import datamodel  # noqa: WPS433

    return datamodel


def _walk(element, parent: str | None, order: list[str], parents: dict[str, str | None]) -> None:
    for child in element["children"] if "children" in element.keys() else []:
        if getattr(child, "type", "") != "DmeJoint":
            continue
        order.append(child.name)
        parents[child.name] = parent
        _walk(child, child.name, order, parents)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock", required=True, help="the game's own skeleton DMX")
    parser.add_argument("--doc", required=True, help="the mesh+skeleton DMX to correct")
    parser.add_argument("--tail", required=True, help="the tail mesh DMX, for the chain order")
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--fix-rest",
        action="store_true",
        help="also copy the stock document's rest for shared joints (experiment only: a mesh document's rest is its bind)",
    )
    args = parser.parse_args(argv)
    fix_rest = bool(args.fix_rest)

    datamodel = _datamodel()
    from tail_release_audit import _joint_table  # noqa: WPS433

    stock = _joint_table(datamodel, args.stock)
    tail_table = _joint_table(datamodel, args.tail)
    tail_order = [name for name in tail_table["__order__"]["order"] if name.startswith("tail_")]
    if not tail_order:
        raise SystemExit("skeleton-fix: the tail mesh names no tail_* joints")

    document = datamodel.load(args.doc)
    from tail_release_audit import _find  # noqa: WPS433

    model = _find(document.root, "DmeModel")
    if model is None:
        raise SystemExit("skeleton-fix: no DmeModel in this document")

    order: list[str] = []
    parents: dict[str, str | None] = {}
    _walk(model, None, order, parents)
    elements: dict[str, object] = {}

    def index(element) -> None:
        for child in element["children"] if "children" in element.keys() else []:
            if getattr(child, "type", "") == "DmeJoint":
                elements[child.name] = child
                index(child)

    index(model)

    # What each joint's parent must be: the game's own parent where it has one,
    # the chain order for the tail.
    # Start from the document's own parents so a joint the stock skeleton does not
    # name (a leaf this port added, `head_end`, `ball_end_L`) keeps its place; only
    # the joints with a measured defect are re-pointed.
    wanted: dict[str, str | None] = dict(parents)
    for name in order:
        if name in stock["__order__"]["order"]:
            wanted[name] = stock[name]["parent"]
    for index_, name in enumerate(tail_order):
        if name in elements:
            wanted[name] = tail_order[index_ - 1] if index_ else "pelvis"
    if "pelvis" in stock["__order__"]["order"]:
        wanted["pelvis"] = stock["pelvis"]["parent"]

    changed = [
        {"joint": name, "from": parents.get(name), "to": parent}
        for name, parent in wanted.items()
        if parents.get(name) != parent
    ]

    # A rest in a mesh document is the skinning bind, NOT a value to be matched to
    # another document. Restoring 76 rests here (pelvis by 54 units / 60 deg, taken
    # from `haze_skel.dmx`) shredded the body in game: the mesh is bound to those
    # heads, so moving them tears the bind apart. `--fix-rest` stays for reproducing
    # that experiment and is off by default.
    rests = []
    for name in order if fix_rest else []:
        if name not in stock["__order__"]["order"] or name not in elements:
            continue
        element, source = elements[name], stock[name]
        if "transform" not in element.keys():
            continue
        current = (
            tuple(round(float(value), 4) for value in element["transform"]["position"]),
            tuple(round(float(value), 4) for value in element["transform"]["orientation"]),
        )
        wanted_rest = (tuple(source["head"]), tuple(source["orientation"]))
        if current == wanted_rest:
            continue
        element["transform"]["position"] = datamodel.make_array(list(source["head"]), float)
        element["transform"]["orientation"] = datamodel.make_array(list(source["orientation"]), float)
        rests.append({"joint": name, "was": current[0], "now": list(source["head"])})

    # Rebuild every children list: non-joint children stay, joint children follow
    # the wanted parent, ordered the way the document already ordered them.
    # Order every level the way the game orders it, then the tail chain, then whatever
    # this port added. Re-parenting weaponHand under arm_*_IKTARGET without the
    # sibling order made the gate's `joint-order-diverges` fire: two joints in the
    # wrong place in a list the client binds by index.
    ordered_names: list[str] = [name for name in stock["__order__"]["order"] if name in elements]
    ordered_names += [name for name in tail_order if name in elements and name not in set(ordered_names)]
    ordered_names += [name for name in order if name not in set(ordered_names)]
    rank = {name: place for place, name in enumerate(ordered_names)}
    for element in [model, *elements.values()]:
        if "children" not in element.keys():
            continue
        # The model element is a root: joints whose parent is None hang off it.
        owner = None if element is model else getattr(element, "name", None)
        kept = [child for child in element["children"] if getattr(child, "type", "") != "DmeJoint"]
        attached = [
            elements[name]
            for name in sorted(elements, key=lambda key: rank.get(key, 10_000))
            if wanted.get(name) == owner
        ]
        element["children"] = datamodel.make_array(kept + attached, datamodel.Element)

    # The document carries the skeleton twice: the DmeModel tree the client walks and
    # a flat `jointList` under `root["skeleton"]`. Rebuilding only the tree left the
    # list in the old order and the gate saw an order divergence between the model's
    # list and the skeleton's tree. Both views must be the same order.
    joint_list_synced = False
    walk_order: list[str] = []
    walk_parents: dict[str, str | None] = {}
    _walk(model, None, walk_order, walk_parents)
    skeleton_element = document.root["skeleton"] if "skeleton" in document.root.keys() else None
    if skeleton_element is not None and "jointList" in skeleton_element.keys():
        existing = list(skeleton_element["jointList"])
        flat = [elements[name] for name in walk_order if name in elements]
        if len(flat) == len(existing):
            skeleton_element["jointList"] = datamodel.make_array(flat, datamodel.Element)
            joint_list_synced = True

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    document.write(str(out), "binary", 9)

    receipt = {
        "stock": args.stock,
        "doc": args.doc,
        "tail": args.tail,
        "tail_order": tail_order,
        "changed": changed,
        "rests_restored": rests,
        "joint_list_synced": joint_list_synced,
        "out": str(out),
        "bytes": out.stat().st_size,
    }
    for row in changed:
        print(f"PARENT {row['joint']}: {row['from']} -> {row['to']}", flush=True)
    for row in rests:
        print(f"REST {row['joint']}: was {row['was']} -> {row['now']}", flush=True)
    print(f"SKELETON-FIX {len(changed)} parents and {len(rests)} rests corrected -> {out}", flush=True)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
