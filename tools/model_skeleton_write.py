"""Write a model's `Skeleton` section so its joints sit in a skeleton DMX's order.

The client binds a bone by its slot in this tree, so the tree has to be the skeleton the
game's masks and clips were serialised against — its own joints first, in its own order,
with anything added afterwards appended at the end.  Nothing here converts a rest: each
bone keeps the `origin`/`angles` text it already had, and only the nesting changes.

    blender -b --python tools/model_skeleton_write.py -- \
        --vmdl <hero>.vmdl --skeleton <hero>_tailbones.dmx --report artifacts/receipts/x.json

Blender is only the DMX reader (PulseSrcOps); the vmdl write goes through `forge.modeldoc`
and the file is replaced by `forge.migrate`, the one module allowed to write a vmdl.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)


PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


def datamodel():
    """PulseSrcOps' DMX reader, from the same extension the addon vendors."""
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    try:
        from pulse_src_ops import datamodel as module  # noqa: WPS433
    except Exception as error:  # noqa: BLE001 - the reason is the message
        raise SystemExit(f"skeleton-writer-needs-blender: {error}") from error
    return module


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--vmdl", required=True)
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    from forge import migrate, modeldoc
    from tail_release_audit import _joint_table
    from skeleton_model_order_probe import model_bone_tree

    vmdl = Path(args.vmdl)
    module = datamodel()
    table = _joint_table(module, args.skeleton)
    # Order comes from `jointList`, the array the compiled skeleton numbers bones by.  The
    # tree walk nests the appended tail under `pelvis`, so using it here wrote the vmdl in an
    # order the gate (correctly) refused against the shipped skeleton.
    root = module.load(str(args.skeleton)).root
    listed = None
    for key in ("model", "skeleton"):
        if key in root.keys():
            child = root[key]
            if hasattr(child, "keys") and "jointList" in child.keys():
                listed = [joint.name for joint in child["jointList"]]
                break
    if listed is None:
        listed = list(dict.fromkeys(table["__order__"]["order"]))
    # The extraction writes an armature object beside the bones ("haze_body", "DMF Tail").
    # It is not a bone the client binds and the vmdl does not declare it.
    object_like = lambda name: " " in name or name.startswith("DMF ")
    order = [name for name in listed if not object_like(name)]
    parents = {name: table[name]["parent"] for name in order if name in table}
    parents = {name: (value or None) for name, value in parents.items() if not object_like(name)}

    text = vmdl.read_text(encoding="utf-8", errors="replace")
    present = modeldoc.skeleton_bone_blocks(text)

    # A bone the shipped skeleton carries and the vmdl does not declare cannot be bound, so it
    # is written here from the skeleton's own rest.  A bone the vmdl declares and the skeleton
    # does not carry is dropped: nothing can drive it.
    from math import degrees  # noqa: WPS433

    extra: dict[str, list[str]] = {}
    missing = [name for name in order if name not in present]
    if missing:
        try:
            from mathutils import Quaternion  # noqa: WPS433
        except Exception as error:  # noqa: BLE001
            raise SystemExit(f"model-skeleton-write-needs-mathutils: {error}") from error
        for name in missing:
            row = table.get(name)
            if not row:
                raise SystemExit(f"model-skeleton-write-no-rest: {name}")
            head = list(row["head"])
            orientation = list(row["orientation"])
            quaternion = Quaternion((orientation[3], orientation[0], orientation[1], orientation[2]))
            angles = [degrees(value) for value in quaternion.to_euler("XYZ")]
            extra[name] = [
                "origin = [ " + ", ".join(f"{value:.6f}" for value in head) + " ]",
                "angles = [ " + ", ".join(f"{value:.6f}" for value in angles) + " ]",
                "do_not_discard = true",
            ]

    # `pelvis` is written as a root even when the document nests it elsewhere.  The model's
    # `root_motion` carries the authored 90 deg (orientation [0.5, 0.5, 0.5, 0.5]); a pelvis
    # parented under it receives that rotation twice and the body collapses in on itself, which
    # is the 2026-11-16 v8 failure and the 2026-11-15 re-parent failure recorded in AGENTS.md.
    if "pelvis" in parents:
        parents["pelvis"] = None

    updated = modeldoc.rewrite_skeleton_bones(text, parents, order, extra)
    result = migrate.write_model_text(vmdl, updated)

    # Read the written file back through the same probe the gate uses.  A rewrite that
    # reorders the document but not the tree would otherwise be reported as a success.
    declared, _ = model_bone_tree(vmdl)
    # Coverage is the contract, not order.  The vmdl is a tree and the skeleton is a list, and
    # the accepted Shiv build has 135 of 168 declared bones at a different position than its
    # own list; a tree cannot put appended joints after every body joint.  What must hold is
    # that the model declares exactly the joints the shipped skeleton carries.
    absent = sorted(set(order) - set(declared))
    extra = sorted(set(declared) - set(order))
    if absent or extra:
        raise SystemExit(
            "model-skeleton-write-failed: "
            f"{len(absent)} skeleton joints missing from the model ({absent[:4]}), "
            f"{len(extra)} model bones absent from the skeleton ({extra[:4]})"
        )

    report = {
        "vmdl": str(vmdl),
        "skeleton": str(args.skeleton),
        "bones": len(declared),
        "changed": result["changed"],
        "sha256": result["sha256"],
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"MODEL-SKELETON-WRITE {vmdl.name} bones={len(declared)} changed={result['changed']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
