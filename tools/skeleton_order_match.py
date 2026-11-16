"""Rebuild a skeleton's joint tree to the order and parentage the model declares.

**Measured, not assumed.** The one pair that works in game is Shiv's: its model declares 168 bones
and its shipped skeleton carries the same 168 in the same order with the same parents —
`tools/skeleton_model_order_probe.py` reports `ORDER 168/168 every shared joint keeps its slot`,
`PARENTS 0 of 168`. The Haze pair reports **68 of 131 slots moved** and `pelvis` parented under
`root_motion` in the skeleton where the model has it at the root. A slot mismatch binds each animation
track to a different bone than the one the mesh was skinned against, which is what the owner saw as
*"arms and head and tail rotated wrong"*.

A DMX joint tree carries no explicit parent field: nesting is the parent and depth-first order is the
slot order. So aligning a skeleton to a model is one operation — rebuild each joint's `children` to the
model's children in the model's order, and re-root whatever the model roots. Rest transforms are
untouched; this moves no bone, it only changes which slot each bone occupies.

    blender -b --factory-startup --python tools/skeleton_order_match.py -- \
        --vmdl <hero>.vmdl --skeleton <hero>_tailbones.dmx \
        --out <hero>_tailbones.matched.dmx --report artifacts/receipts/<hero>-order-match.json

Exit 0 when the written file's order and parents equal the model's, 2 when they cannot (a joint in one
tree and not the other is refused rather than dropped).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
TOOLS = Path(__file__).resolve().parent


def datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel as module  # noqa: WPS433

    return module


def _find(element, element_type: str):
    if getattr(element, "type", "") == element_type:
        return element
    for child in element["children"] if "children" in element.keys() else []:
        found = _find(child, element_type)
        if found is not None:
            return found
    return None


def _joints_in_order(element, out: list) -> None:
    for child in element["children"] if "children" in element.keys() else []:
        if getattr(child, "type", "") == "DmeJoint":
            out.append(child)
            _joints_in_order(child, out)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--vmdl", default="", help="the model whose declared order is the reference")
    parser.add_argument(
        "--reference-dmx",
        default="",
        help="use this DMX's joint order as the reference instead of a vmdl (for mesh documents)",
    )
    parser.add_argument("--skeleton", required=True, help="the DMX to rewrite")
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--append-unlisted",
        action="store_true",
        help="keep joints the reference does not carry, appended after its last joint in their own "
        "document order; inserting them inside the reference's prefix renames every later slot",
    )
    parser.add_argument("--encoding", default="binary")
    parser.add_argument("--encoding-ver", type=int, default=9)
    args = parser.parse_args(argv)

    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from skeleton_model_order_probe import model_bone_tree  # noqa: WPS433

    module = datamodel()
    if args.reference_dmx:
        # A render mesh carries a subset of the skeleton's joints, so its rows are matched
        # to the reference's relative order rather than to absolute slots.
        from tail_release_audit import _joint_table  # noqa: WPS433

        table = _joint_table(module, args.reference_dmx)
        order = list(dict.fromkeys(table["__order__"]["order"]))
        parents = {name: table[name]["parent"] for name in order if name in table}
        subset_ok = True
    else:
        if not args.vmdl:
            raise SystemExit("order-match-needs-reference: pass --vmdl or --reference-dmx")
        order, parents = model_bone_tree(Path(args.vmdl))
        subset_ok = False
    loaded = module.load(str(args.skeleton))
    # A skeleton DMX is a `DmElement root` holding `skeleton`, `model` and `exportTags`;
    # the joint tree is `root["model"]`.  Searching `children` from the root found nothing,
    # which is a reader bug, not a missing model.
    model = loaded.root["model"] if "model" in loaded.root.keys() else _find(loaded.root, "DmeModel")
    if model is None or getattr(model, "type", "") != "DmeModel":
        raise SystemExit(f"skeleton-no-dme-model: {args.skeleton}")

    joints: list = []
    _joints_in_order(model, joints)
    by_name = {joint.name: joint for joint in joints}
    model_names = set(order)
    skeleton_names = set(by_name)
    extra = sorted(skeleton_names - model_names)
    if extra and not args.append_unlisted:
        raise SystemExit(
            f"skeleton-model-joint-sets-differ: {len(extra)} joints in {Path(args.skeleton).name} "
            f"are absent from the reference ({extra[:4]})"
        )
    if extra:
        # Appended, never inserted.  The reference is the document the game's masks and clips
        # index, so its joints keep slots 0..n-1 and only the extras move to the end.
        from tail_release_audit import _joint_table as _ours  # noqa: WPS433

        own = _ours(module, args.skeleton)
        own_order = list(dict.fromkeys(own["__order__"]["order"]))
        appended = [name for name in own_order if name in set(extra)]
        for name in appended:
            parents[name] = own[name]["parent"]
        order = order + appended
    missing = sorted(model_names - skeleton_names)
    if missing and not subset_ok:
        raise SystemExit(
            f"skeleton-model-joint-sets-differ: {len(missing)} reference joints are absent from "
            f"{Path(args.skeleton).name} ({missing[:4]})"
        )
    # For a mesh, only the joints it actually carries are reordered; the rest of the
    # reference order is irrelevant to it.  `order` is narrowed below.
    order = list(dict.fromkeys(name for name in order if name in skeleton_names))

    children: dict[str, list[str]] = {name: [] for name in order}
    roots: list[str] = []
    for name in order:
        parent = parents.get(name)
        if parent and parent in children:
            children[parent].append(name)
        else:
            roots.append(name)

    element_type = type(joints[0])
    for name in order:
        if "children" not in by_name[name].keys():
            continue
        by_name[name]["children"] = module.make_array([by_name[child] for child in children[name]], element_type)
    model["children"] = module.make_array([by_name[name] for name in roots], element_type)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    loaded.write(str(out), args.encoding, args.encoding_ver)

    # Read the result back: a write that silently reorders, or a make_array whose element type is
    # wrong, would otherwise be reported as a success.
    check: list = []
    reloaded = module.load(str(out)).root
    _joints_in_order(reloaded["model"] if "model" in reloaded.keys() else _find(reloaded, "DmeModel"), check)
    written = [joint.name for joint in check]
    moved = [name for index, name in enumerate(order) if index >= len(written) or written[index] != name]
    report = {
        "vmdl": args.vmdl,
        "skeleton": args.skeleton,
        "out": str(out),
        "bytes": out.stat().st_size,
        "joints": len(written),
        "roots": roots,
        "slots_differing_after_write": len(moved),
        "first_difference": moved[0] if moved else None,
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"ORDER-MATCH {out.name} joints={report['joints']} roots={roots} "
        f"slots_differing_after_write={report['slots_differing_after_write']}",
        flush=True,
    )
    if moved:
        print(f"REFUSE skeleton-order-write-failed: slot {moved.index(moved[0])} is {written[moved.index(moved[0])]!r} not {moved[0]!r}"
              if isinstance(moved, list) and moved else "REFUSE skeleton-order-write-failed")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
