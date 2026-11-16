"""Compare the compiled model's own bone order with the skeleton we ship.

The client binds a model's render meshes into `m_modelSkeleton`, and a `.vnmskel`
that ships beside the model replaces that structure.  Every build this port has
made that bundled a skeleton came back with a body defect -- head and arms rotated,
tail curling into itself -- and every one of them was checked against the mesh
documents and the clips, never against the order the *compiled model* declares.

That comparison is the one AGENTS.md names as unrun for this hero:

    "Until the model's own `m_modelSkeleton.m_boneName` order is compared with the
     shipped skeleton's (the `artifacts/probes/0647` method), 'ship a skeleton' is
     unproven for this hero."

`Source2Viewer-CLI -d` writes the compiled model as text with a `Skeleton` section
whose `Bone` children are in exactly that order, so no compiled-data reader is
needed and nothing is inferred: this reads the text the game's own tool emitted and
the skeleton with the same reader the release gate uses.

    blender -b --factory-startup --python tools/skeleton_model_order_probe.py -- \
      --vmdl artifacts/probes/haze-model-game/models/heroes_staging/haze/haze.vmdl \
      --skeleton artifacts/probes/haze-skel-ours/models/heroes_staging/haze/haze_tailbones.dmx \
      --report artifacts/receipts/skeleton-model-order.json

Refusals, because a divergence at a shared slot is the body defect:

* `model-skeleton-order-diverges` — a joint the model declares sits at a different
  slot in the skeleton.  Slot is what binds; a shared joint may not move.
* `model-joint-absent-from-skeleton` — the model declares a joint the skeleton
  cannot resolve, so the mesh has nothing to bind to.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
sys.path.insert(0, str(REPO / "tools"))

NAME = re.compile(r'^\s*name = "([^"]+)"\s*$')
BONE = re.compile(r'^\s*_class = "Bone"\s*$')
SKELETON = re.compile(r'^\s*_class = "Skeleton"\s*$')


def model_bone_tree(vmdl: Path) -> tuple[list[str], dict[str, str | None]]:
    """The `Skeleton` section's bones in declared order, plus each bone's parent.

    The order is the slot order the client binds meshes against; the parents decide
    whether a disagreement can be fixed by reordering at all.  Reordering siblings is
    a slot change; a different parent is a different frame, and no reorder repairs it.
    """
    lines = vmdl.read_text(encoding="utf-8", errors="replace").splitlines()
    start = next((index for index, line in enumerate(lines) if SKELETON.match(line)), None)
    if start is None:
        raise SystemExit(f"model-vmdl-has-no-skeleton: {vmdl} has no `_class = \"Skeleton\"` section")
    indent = len(lines[start]) - len(lines[start].lstrip())
    order: list[str] = []
    parents: dict[str, str | None] = {}
    # Braces delimit a bone, and a bone's `{` sits at its *parent's* indentation, so
    # indentation cannot track the nesting: keying the stack on indentation popped the
    # parent as soon as a child's brace appeared and reported every bone as a root.
    # Frames are pushed on `{` and popped on `}`; the parent is the nearest enclosing
    # frame that named a bone.
    frames: list[str | None] = [None]
    pending = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        depth = len(line) - len(line.lstrip())
        # The section's own `children = [` sits at the same indentation as its
        # `_class` line, so an equal-depth line is only the end of the section when
        # it closes it.  Breaking on any equal-depth line stopped at `children = [`
        # and reported "declares no Bone names" on a model that declares 98.
        if depth < indent or (depth == indent and stripped == "}"):
            break
        if BONE.match(line):
            pending = True
            continue
        match = NAME.match(line)
        if match and pending:
            name = match.group(1)
            parents[name] = next((frame for frame in reversed(frames) if frame), None)
            order.append(name)
            frames[-1] = name
            pending = False
        if "{" in stripped:
            frames.append(None)
        if "}" in stripped:
            if len(frames) > 1:
                frames.pop()
    if not order:
        raise SystemExit(f"model-vmdl-has-no-bones: {vmdl} Skeleton section declared no Bone names")
    return order, parents


def skeleton_order(dmx: Path) -> tuple[list[str], dict[str, str | None]]:
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433
    from tail_release_audit import _joint_table  # noqa: WPS433

    table = _joint_table(datamodel, str(dmx))
    order = list(dict.fromkeys(table["__order__"]["order"]))
    parents = {name: table[name]["parent"] for name in order if name in table}
    return order, parents


def compare(model: list[str], skeleton: list[str], model_parents=None, skeleton_parents=None) -> dict:
    slots = {name: index for index, name in enumerate(skeleton)}
    absent = [name for name in model if name not in slots]
    moved = [
        {"joint": name, "model_slot": index, "skeleton_slot": slots[name]}
        for index, name in enumerate(model)
        if name in slots and slots[name] != index
    ]
    first = moved[0] if moved else None
    reparented = []
    if model_parents and skeleton_parents:
        reparented = [
            {"joint": name, "model_parent": model_parents.get(name), "skeleton_parent": skeleton_parents.get(name)}
            for name in model
            if name in slots and model_parents.get(name) != skeleton_parents.get(name)
        ]
    return {
        "model_joints": len(model),
        "skeleton_joints": len(skeleton),
        "shared": sum(1 for name in model if name in slots),
        "absent_from_skeleton": absent,
        "moved": moved,
        "first_divergence": first,
        "order_identical_for_shared": not moved,
        "reparented": reparented,
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--vmdl", required=True, help="the text vmdl Source2Viewer -d wrote")
    parser.add_argument("--skeleton", required=True, help="the skeleton dmx we ship")
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    model, model_parents = model_bone_tree(Path(args.vmdl))
    skeleton, skeleton_parents = skeleton_order(Path(args.skeleton))
    result = compare(model, skeleton, model_parents, skeleton_parents)
    result.update({"vmdl": args.vmdl, "skeleton": args.skeleton})

    if result["absent_from_skeleton"]:
        result["refused"] = "model-joint-absent-from-skeleton"
        print(
            f"REFUSE model-joint-absent-from-skeleton: {len(result['absent_from_skeleton'])} model "
            f"joints have no slot in {Path(args.skeleton).name}: {result['absent_from_skeleton'][:6]}",
            flush=True,
        )
    elif result["moved"]:
        result["refused"] = "model-skeleton-order-diverges"
        first = result["first_divergence"]
        print(
            f"REFUSE model-skeleton-order-diverges: {len(result['moved'])} of {result['shared']} shared "
            f"joints sit at a different slot; first is {first['joint']} at model {first['model_slot']} "
            f"vs skeleton {first['skeleton_slot']}",
            flush=True,
        )
    else:
        print(
            f"ORDER model {result['model_joints']} / skeleton {result['skeleton_joints']}: "
            f"every shared joint keeps its slot ({result['shared']} shared)",
            flush=True,
        )
    print(
        f"PARENTS {len(result['reparented'])} of {result['shared']} shared joints have a different parent "
        + (f"(first {result['reparented'][0]})" if result["reparented"] else ""),
        flush=True,
    )
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if not result.get("refused") else 2


if __name__ == "__main__":
    raise SystemExit(main())
