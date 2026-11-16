"""Compare two skeleton documents by the list the client actually indexes.

A `.vnmskel` stores bone masks as numeric ids and carries no bone names, so the only contract
that matters between a shipped skeleton and the game's own is the order of `jointList`.  This
probe answers three questions with one document each:

* does the candidate keep the reference's joints at the same slots (`prefix_kept`)?
* what is the first shared joint that moved (`first_shift`)?
* which joints does the candidate carry that the reference does not (`appended`), and are any
  of them *before* the reference's last joint (an insertion, not an append)?

    blender -b --python tools/skeleton_identity_probe.py -- \
        --reference <game>_skel.dmx --candidate <shipped>_tailbones.dmx \
        --report artifacts/receipts/identity.json

Reading DMX is PulseSrcOps'; nothing here parses a compiled resource or writes a file.
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
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    try:
        from pulse_src_ops import datamodel as module  # noqa: WPS433
    except Exception as error:  # noqa: BLE001
        raise SystemExit(f"identity-probe-needs-blender: {error}") from error
    return module


def _joint_list(root) -> list[str]:
    # The list is not always under `model`: a skeleton document keeps it on the element the
    # extraction wrote, which can be `skeleton` or a plain DmElement.  Ask every top-level
    # child rather than assuming one key, and say which key answered.
    # Prefer the `model` element: a skeleton document can carry a second `jointList` on a
    # sibling (`skeleton`) that is not the one the model binds against, and reading whichever
    # key comes first made a correct file look shifted by one slot.
    for key in ("model", "skeleton"):
        if key in root.keys():
            child = root[key]
            if hasattr(child, "keys") and "jointList" in child.keys():
                return [joint.name for joint in child["jointList"]]
    if "jointList" in root.keys():
        return [joint.name for joint in root["jointList"]]
    for key in root.keys():
        child = root[key]
        if hasattr(child, "keys") and "jointList" in child.keys():
            return [joint.name for joint in child["jointList"]]
    raise SystemExit("identity-probe-no-jointlist")


def compare(reference: list[str], candidate: list[str]) -> dict:
    slots = {name: index for index, name in enumerate(candidate)}
    shared = [name for name in reference if name in slots]
    shifted = [(name, index, slots[name]) for index, name in enumerate(reference) if name in slots and slots[name] != index]
    appended = [name for name in candidate if name not in set(reference)]
    first_append_slot = next((i for i, name in enumerate(candidate) if name in set(appended)), None)
    return {
        "reference_joints": len(reference),
        "candidate_joints": len(candidate),
        "shared": len(shared),
        "prefix_kept": candidate[: len(reference)] == reference,
        "first_shift": shifted[0] if shifted else None,
        "shifted": len(shifted),
        "appended": appended,
        "first_appended_slot": first_append_slot,
        "appended_before_reference_end": first_append_slot is not None and first_append_slot < len(reference),
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--rests",
        action="store_true",
        help="also compare each shared joint's rest head/orientation and parent between the two",
    )
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--candidate-vmdl",
        action="store_true",
        help="read the candidate's declared bones from a vmdl's Skeleton section instead of a DMX",
    )
    args = parser.parse_args(argv)

    module = datamodel()
    reference = _joint_list(module.load(args.reference).root)
    if args.candidate_vmdl:
        from skeleton_model_order_probe import model_bone_tree  # noqa: WPS433

        candidate, _parents = model_bone_tree(Path(args.candidate))
    else:
        candidate = _joint_list(module.load(args.candidate).root)
    result = compare(reference, candidate)
    result.update({"reference": args.reference, "candidate": args.candidate})
    if args.rests:
        from tail_release_audit import _joint_table  # noqa: WPS433

        here = _joint_table(module, args.reference)
        there = _joint_table(module, args.candidate)
        moved = []
        parent_moved = []
        for name in reference:
            if name not in there or name not in here:
                continue
            delta = max(abs(a - b) for a, b in zip(here[name]["head"], there[name]["head"]))
            dot = abs(sum(a * b for a, b in zip(here[name]["orientation"], there[name]["orientation"])))
            if delta > 0.01 or (1.0 - dot) > 2e-3:
                moved.append((name, round(delta, 3), round(1.0 - dot, 5)))
            if here[name]["parent"] != there[name]["parent"]:
                parent_moved.append((name, here[name]["parent"], there[name]["parent"]))
        result["rest_moved"] = moved
        result["parent_moved"] = parent_moved
        print(f"  rest moved: {len(moved)} {moved[:3]}", flush=True)
        print(f"  parent moved: {len(parent_moved)} {parent_moved[:3]}", flush=True)

    verdict = "PREFIX" if result["prefix_kept"] else "SHIFTED"
    print(
        f"IDENTITY {Path(args.candidate).name} {verdict}: "
        f"{result['candidate_joints']} joints, {result['shifted']} of {result['shared']} shared moved, "
        f"appended={len(result['appended'])} first_appended_slot={result['first_appended_slot']}",
        flush=True,
    )
    if result["first_shift"]:
        print(f"  first shift: {result['first_shift']}", flush=True)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["prefix_kept"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
