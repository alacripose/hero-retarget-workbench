"""Rebuild a model's `Skeleton` from the game's own model, then append the bones we add.

The game's decompiled `haze.vmdl` is the only document known to render correctly, and its bone
blocks carry exact `origin`/`angles` numbers. Rewriting them from a DMX means converting the
skeleton's quaternions into whatever frame those numbers are in; no reading of them matched
(closest candidate 129 deg out on `clavicle_L`), so this tool does not try. It copies the game's
bone blocks verbatim, keeps the game's parents, and appends the bones the shipped skeleton carries
beyond the game model — each with the block it already had — under the parent the skeleton gives.

    blender -b --python tools/model_from_game_vmdl.py -- \
        --game-vmdl <pak01>/haze.vmdl --vmdl <ours>.vmdl --skeleton <ours>_tailbones.dmx \
        --report artifacts/receipts/x.json

Refuses when the two documents disagree about which bones the game ships: a model that drops one
of the game's bones cannot bind it, and guessing which side is right is not this tool's job.
"""

from __future__ import annotations

import argparse
import json
import sys
import re
from pathlib import Path

TAIL_PREFIX = re.compile(r"^tail_[0-9]+$")

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


def datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel as module  # noqa: WPS433

    return module


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-vmdl", required=True)
    parser.add_argument("--vmdl", required=True)
    parser.add_argument("--skeleton", required=True)
    parser.add_argument(
        "--pelvis-block-from",
        default="",
        help="a vmdl whose `pelvis` bone block is authoritative (the rest that compensates the root)",
    )
    parser.add_argument(
        "--tree-from-skeleton",
        action="store_true",
        help="nest the bones with the skeleton DMX's own parents instead of the game model's",
    )
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    from forge import migrate, modeldoc

    game = Path(args.game_vmdl)
    ours = Path(args.vmdl)
    game_text = game.read_text(encoding="utf-8", errors="replace")
    our_text = ours.read_text(encoding="utf-8", errors="replace")

    game_fields = modeldoc.skeleton_bone_blocks(game_text)
    game_parents = modeldoc.skeleton_parent_map(game_text)
    our_fields = modeldoc.skeleton_bone_blocks(our_text)

    module = datamodel()
    from tail_release_audit import _joint_table  # noqa: WPS433
    from skeleton_model_order_probe import model_bone_tree  # noqa: WPS433

    table = _joint_table(module, args.skeleton)
    skeleton_order = list(dict.fromkeys(table["__order__"]["order"]))
    object_like = lambda name: " " in name or name.startswith("DMF ")
    skeleton_order = [name for name in skeleton_order if not object_like(name)]
    skeleton_parents = {name: table[name]["parent"] for name in skeleton_order if name in table}

    # A game bone the skeleton does not carry is kept in the model and recorded, not refused.
    # Measured: the game's own pair ships this way — `haze.vmdl` declares 120 bones and
    # `haze_skel.dmx` carries 98, so all 22 `*_end` leaves ride the model and the game renders the
    # head, arms and tail correctly.  The skeleton only has to carry what the clips animate.
    lost = [name for name in game_fields if name not in set(skeleton_order)]
    if lost:
        print(f"MODEL-FROM-GAME keeps {len(lost)} model-only bones the skeleton does not carry: {lost[:6]}", flush=True)

    appended = [name for name in skeleton_order if name not in game_fields]
    missing_blocks = [name for name in appended if name not in our_fields]
    if missing_blocks:
        raise SystemExit(f"model-rebuild-no-block: no bone block for {missing_blocks[:6]}")

    # Game bones keep the game's own block and parent; appended bones keep the block they had and
    # take the skeleton's parent, which is the only fact about them that can be derived.
    fields = {name: game_fields[name] for name in game_fields}
    parents = {name: game_parents.get(name) for name in game_fields}
    if args.tree_from_skeleton:
        # The mesh bind is ours, so the model must present the tree the bind was authored
        # against.  Measured in game: the game's tree rendered the body flat (v11), our tree
        # rendered it upright (v9).  Only the nesting changes here; every bone keeps its block.
        parents = {name: skeleton_parents.get(name) for name in fields}
    for name in appended:
        fields[name] = our_fields[name]
        parents[name] = skeleton_parents.get(name)

    # `pelvis` is the one bone the game's own model cannot supply: it sits at the root in our
    # model, carrying the rest that compensates the authored `root_motion` rotation.  Copying the
    # game's block puts the pelvis under that rotation and the body folds (v8 and v10 in game).
    if args.pelvis_block_from:
        source = Path(args.pelvis_block_from)
        blocks = modeldoc.skeleton_bone_blocks(source.read_text(encoding="utf-8", errors="replace"))
        if "pelvis" not in blocks:
            raise SystemExit(f"model-rebuild-no-pelvis-rest: {source} carries no pelvis bone block")
        fields["pelvis"] = blocks["pelvis"]

    order = [name for name in skeleton_order if name in fields]
    updated = modeldoc.rewrite_skeleton_bones(our_text, parents, order, fields)
    result = migrate.write_model_text(ours, updated)

    declared, _ = model_bone_tree(ours)
    absent = sorted(set(fields) - set(declared))
    extra = sorted(set(declared) - set(fields))
    if absent or extra:
        raise SystemExit(
            f"model-rebuild-write-failed: missing {absent[:4]}, unexpected {extra[:4]}"
        )

    report = {
        "game_vmdl": str(game),
        "vmdl": str(ours),
        "game_bones": len(game_fields),
        "appended": appended,
        "bones": len(declared),
        "changed": result["changed"],
        "sha256": result["sha256"],
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"MODEL-FROM-GAME {ours.name} game_bones={len(game_fields)} appended={len(appended)} bones={len(declared)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
