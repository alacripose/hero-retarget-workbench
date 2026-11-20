"""Reorder a skeleton DMX so the game's own joint slots come first, unchanged.

A `.vnmskel` carries bone masks as *numeric* ids (`m_boneIDs`) into the skeleton's
`jointList`; it carries no bone names.  So the list is the binding contract: id 6 is whatever
sits at index 6.  Our Haze skeleton put `weaponHand_L` at 50 where the game has it at 6 and
`weaponHand_R` at 91 where the game has 8, which renames 81 of the game's joints and is what
the owner saw as a rotated head, arms and tail — with the model and its skeleton agreeing
131/131, because those two documents can only vouch for each other.

This tool refuses rather than guesses:

* every joint the game's skeleton carries must exist here (`skeleton-missing-game-joint`);
* the game's order is written first, as a prefix, and nothing the game carries may be
  moved into the appended tail (`skeleton-game-joint-in-tail`);
* after writing, the file is re-read and its `jointList` must equal the intended order
  (`skeleton-write-failed`), because a write that silently regroups is worse than none.

    blender -b --python tools/skeleton_game_prefix.py -- \
        --game <haze_skel.dmx> --skeleton <ours>.dmx --out <ours>.gameorder.dmx \
        --report artifacts/receipts/x.json
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
        raise SystemExit(f"skeleton-order-needs-blender: {error}") from error
    return module


def _model(element):
    if "model" in element.keys():
        return element["model"]
    for key in element.keys():
        child = element[key]
        if getattr(child, "type", "") == "DmeModel":
            return child
    return None


def _children(node) -> list:
    return list(node["children"]) if "children" in node.keys() else []


def _joints(model) -> list:
    out: list = []

    def walk(node):
        for child in _children(node):
            out.append(child)
            walk(child)

    walk(model)
    return out


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True, help="the game's own skeleton DMX")
    parser.add_argument("--skeleton", required=True, help="our skeleton DMX")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--bind",
        default="",
        help="the mesh bind DMX whose hierarchy the vertices were authored in (ours is flat)",
    )
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--keep-our-parents",
        action="store_true",
        help="keep our own nesting (the tree the mesh bind was authored against) and order siblings by the game's list",
    )
    args = parser.parse_args(argv)

    module = datamodel()
    game_root = module.load(args.game).root
    # Keep this handle: the tree and `jointList` are edited on it and *this* is what gets
    # written.  Reloading the source before writing discards every edit and the file comes
    # back in its old order, which the read-back check then reports honestly.
    our_loaded = module.load(args.skeleton)
    our_root = our_loaded.root
    game_model = _model(game_root)
    our_model = _model(our_root)
    if game_model is None or our_model is None:
        raise SystemExit("skeleton-order-needs-dme-model")

    all_joints = _joints(our_model)
    # `jointList` can carry one non-joint entry: the armature object the extraction writes
    # (`haze_body`).  The vmdl does not declare it and the game's list does not contain it, so
    # it must not be numbered.  Keep the entries whose type says joint, and only fall back to
    # all of them if the type is not reported at all.
    typed = [joint for joint in all_joints if getattr(joint, "type", "") == "DmeJoint"]
    bones = typed if typed else all_joints
    by_name = {joint.name: joint for joint in bones}

    game_names = [joint.name for joint in game_model["jointList"]]
    listed_names = [joint.name for joint in our_model["jointList"]]
    our_names = [name for name in listed_names if name in by_name]
    dropped = [name for name in listed_names if name not in by_name]
    if dropped and not typed:
        raise SystemExit(f"skeleton-jointlist-unwalked: {len(dropped)} listed joints are not in the tree ({dropped[:4]})")
    if dropped:
        print(f"GAME-ORDER drop-non-joint {dropped}", flush=True)
    our_set = set(our_names)
    missing = [name for name in game_names if name not in our_set]
    if missing:
        raise SystemExit(f"skeleton-missing-game-joint: {len(missing)} of the game's joints are absent ({missing[:6]})")

    extras = [name for name in our_names if name not in set(game_names)]
    # The `jointList` is written at the end, as the walk's own order, when our nesting is kept:
    # the game's list is 4 joints out of its own walk's order (`WALK-ORDER haze_skel.dmx ...
    # inversions=4`), so copying it as a prefix guarantees the list and the walk disagree — the
    # state in which a clip bone index lands on another bone.  Here the list only has to name
    # every joint once, so the parents below can be resolved.
    order = game_names + extras

    # Parents: the game's own for its joints, ours for the appended ones.
    # One traversal, not a membership search per joint: `joint in _children(candidate)` builds
    # a fresh list each call and an unresolved parent silently turns a bone into a root, which
    # moves it to the end of the written order while the jointList prefix still looks right.
    game_parents = {}
    for node in _joints(game_model):
        for child in _children(node):
            game_parents[child.name] = node.name
    our_parents = {}
    for joint in _joints(our_model):
        for child in _children(joint):
            our_parents[child.name] = joint.name
    print(
        f"GAME-ORDER source-hierarchy joints={len(_joints(our_model))} parents={len(our_parents)}",
        flush=True,
    )
    if args.bind:
        # Our skeleton document is FLAT: every joint hangs off the model, so it states no
        # hierarchy at all (`skeleton-invented-root` reports 130 of them).  The hierarchy the
        # vertices were actually bound in is the mesh bind's, so that is the tree to present.
        bind_model = _model(module.load(args.bind).root)
        if bind_model is None:
            raise SystemExit(f"skeleton-bind-has-no-model: {args.bind}")
        bind_parents = {}
        for joint in _joints(bind_model):
            for child in _children(joint):
                bind_parents[child.name] = joint.name
        our_parents.update(bind_parents)
        print(f"GAME-ORDER bind-hierarchy {args.bind} joints={len(bind_parents)}", flush=True)
    # Our own hierarchy is kept.  Only the list order comes from the game; adopting its parents
    # as well re-parented `pelvis` under `root_motion`, whose rest carries the authored 90 deg,
    # so the body applied it twice and collapsed in on itself (2026-11-16, the v8 build).  Order
    # and hierarchy are separate facts and only the order indexes a mask.
    # The game's parents are adopted, because the client numbers bones by walking the tree: in
    # v9 our own parents put `weaponHand_L` at 21 where the game walks it at 6 and the head, arms
    # and tail rotated again.  The one parent that is NOT copied is `pelvis`: the model's
    # `root_motion` carries the authored 90 deg, so a pelvis under it applies that rotation twice
    # and the body collapses in on itself (v8).  Those two failures are why order and hierarchy
    # are both taken from the game except for that single edge.
    parents = {}
    if args.keep_our_parents:
        # The mesh bind is ours, and the model and the skeleton must present the tree it was
        # authored against: measured in game, a model built on the game's own tree rendered the
        # body flat (v11) and one folded into itself with the game's tree and rests (v10), while
        # our tree rendered upright (v9).  Nesting is therefore not negotiable; the ordering of
        # siblings is, and it is what the client numbers bones by.
        for name in our_names:
            parents[name] = our_parents.get(name)
    else:
        for name in order:
            parents[name] = game_parents.get(name) if name in game_parents else our_parents.get(name)
    # `pelvis` stays a root, and its rest stays ours.  This cost two in-game failures to learn
    # and is not a preference: the model's `root_motion` carries the authored 90 deg and the
    # engine applies it to the body, so a pelvis under it takes that rotation twice and the body
    # folds (v8, and again v10 which copied the game's own pair).  The swap below is also why
    # the game's rest must not be copied for this one joint: ours is the value that compensates
    # the missing parent, and the pair is what holds the pose.
    if "pelvis" in parents and not args.keep_our_parents:
        parents["pelvis"] = None
    for name in order:
        parent = parents.get(name)
        if parent and parent not in by_name:
            raise SystemExit(f"skeleton-parent-missing: {name} names {parent}")

    # The tree is written in the order the client *walks* it, which is not the order the game's
    # `jointList` lists.  Both are contracts on different things: masks index the list, and the
    # bones are numbered by walking the tree.  Writing the tree from the list order put
    # `clavicle_R`, `leg_upper_L` and `leg_upper_R` out of step with the game's walk and the gate
    # refused it.
    game_walk = [joint.name for joint in _joints(game_model)]
    if args.keep_our_parents:
        order = [name for name in our_names]
        # Order every sibling group by where the game's list puts it, so a depth-first walk lands
        # as close to the game's own numbering as our nesting allows.
        rank = {name: index for index, name in enumerate(game_names)}
        walk_order = sorted(
            order,
            key=lambda name: rank.get(name, len(game_names)),
        )
    else:
        walk_order = [name for name in game_walk if name in set(order)] + extras
    children: dict[str, list[str]] = {name: [] for name in order}
    roots: list[str] = []
    for name in walk_order:
        parent = parents.get(name)
        if parent and parent in children:
            children[parent].append(name)
        else:
            roots.append(name)

    # Shared joints take the game's own rest.  The pair (parent, rest) is one fact: our pelvis
    # sat at the root with a rest 54.4 units and 60 deg away from the game's, which is the same
    # pose only while that rest compensates the parent.  Adopting the game's parents without its
    # rests composes the two compensations and the body collapses; adopting both makes the
    # shipped skeleton the game's skeleton plus appended tail joints, which is what the clips
    # and the mesh bind were authored against.
    game_joints_by_name = {joint.name: joint for joint in _joints(game_model)}
    rest_copied = 0
    for name in game_names:
        # With our own nesting the game's rests do not belong here at all: a rest is relative to
        # its parent, so copying the game's values under our parents moved 112 of 128 joints
        # against the mesh bind the vertices were authored in.
        if args.keep_our_parents:
            break
        if name == "pelvis":
            continue
        source = game_joints_by_name.get(name)
        target = by_name.get(name)
        if source is None or target is None:
            continue
        # A joint's rest is one `transform` matrix, not separate position/orientation fields.
        if "transform" in source.keys() and "transform" in target.keys():
            target["transform"] = source["transform"]
            rest_copied += 1

    if args.keep_our_parents:
        # The `jointList` is the walk's own order, computed from the tree that is about to be
        # written.  Anything else leaves the list and the walk disagreeing, and that is the state
        # in which a clip bone index lands on another bone and the head, arms and tail rotate.
        walked: list[str] = []

        def emit(name: str) -> None:
            walked.append(name)
            for child in children[name]:
                emit(child)

        for name in roots:
            emit(name)
        if sorted(walked) != sorted(order):
            raise SystemExit(
                f"skeleton-walk-incomplete: walked {len(walked)} of {len(order)} joints. "
                "A name would be dropped from `jointList`"
            )
        order = walked

    element_type = type(_joints(our_model)[0])
    for name in order:
        joint = by_name[name]
        if "children" in joint.keys():
            joint["children"] = module.make_array([by_name[child] for child in children[name]], element_type)
    our_model["children"] = module.make_array([by_name[name] for name in roots], element_type)
    our_model["jointList"] = module.make_array([by_name[name] for name in order], element_type)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    our_loaded.write(str(out), "binary", 9)

    check_root = module.load(str(out)).root
    written = [joint.name for joint in _model(check_root)["jointList"]]
    if written != order:
        first = next((i for i, (a, b) in enumerate(zip(written, order)) if a != b), min(len(written), len(order)))
        raise SystemExit(f"skeleton-write-failed: slot {first} is {written[first:first + 1]} not {order[first:first + 1]}")

    report = {
        "game": str(args.game),
        "skeleton": str(args.skeleton),
        "out": str(out),
        "bytes": out.stat().st_size,
        "game_joints": len(game_names),
        "appended": extras,
        "rest_fields_copied": rest_copied,
        "walk_order_kept": [name for name in walk_order if name in game_parents or name in parents],
        "joints": len(written),
        "prefix_kept": written[: len(game_names)] == game_names,
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"GAME-ORDER {out.name} joints={len(written)} game_prefix={len(game_names)} appended={len(extras)} "
        f"prefix_kept={report['prefix_kept']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
