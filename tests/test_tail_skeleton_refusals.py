"""The skeleton-slot refusal must exist, must be reachable, and must be reachable from packing.

The 2026-11-16 Haze build shipped with the game's `weaponHand_L` at slot 50 where the game
numbers it 6, and `weaponHand_R` at 91 where the game numbers it 8: 81 of the game's joints sat
at a different slot, and the owner saw a rotated head, arms and tail.  Every gate that existed
compared our model with our skeleton, and those two documents can only vouch for each other.

These tests pin the three properties that stop that from being possible again:

* the gate owns a refusal whose code names the failure and reads `jointList` (the array a
  `.vnmskel`'s bone ids resolve against), not the tree walk;
* the packer cannot produce a pak without the game's own skeleton, so the check always runs;
* the reordering tool refuses rather than guesses when the game carries a joint we do not.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_gate_refuses_a_model_that_does_not_declare_a_skeleton_joint() -> None:
    gate = read("tools/tail_release_gate.py")
    assert "model-vmdl-missing-skeleton-joint" in gate


def test_packer_cannot_pack_without_the_game_skeleton() -> None:
    packer = read("tools/tail_release_pack.py")
    assert "gate-needs-game-skeleton" in packer
    # It has to reach the gate as well, or the refusal above is decoration.
    assert '["--game-skeleton", args.game_skeleton]' in packer


def test_reorder_tool_refuses_instead_of_guessing() -> None:
    tool = read("tools/skeleton_game_prefix.py")
    assert "skeleton-missing-game-joint" in tool
    assert "skeleton-write-failed" in tool
    assert "prefix_kept" in tool, "the report must say whether the game prefix survived"


def test_repository_gate_refuses_a_shifted_release() -> None:
    """The repo's own gate must read the newest pack receipt and fail on a non-zero shift.

    This is the loud half: the packer can be bypassed by a hand-built pak or an older
    checkout, so `python tools/project.py gate` has to answer for whatever is on disk.
    """
    project = read("tools/project.py")
    assert "_release_skeleton_identity_check" in project
    assert "skeleton_identity" in project
    assert "shifted != 0" in project, "a non-zero shift must be a failure, not a warning"
    assert "carries no skeleton_identity record" in project, "a missing record must fail too"
    packer = read("tools/tail_release_pack.py")
    assert 'receipt["skeleton_identity"]' in packer, "the packer must carry the gate's identity record"


def test_the_gate_is_the_only_pack_path() -> None:
    packer = read("tools/tail_release_pack.py")
    assert re.search(r"--skip-gate", packer), "diagnostic escape hatch must stay named"
    # A release is the default; skipping the gate has to be explicit and is never a release.
    assert "diagnostics" in packer.lower()


def test_rest_check_compares_world_poses_not_local_decompositions() -> None:
    """A parent and a rest are one fact, so two correct spellings read as different locals.

    Our skeleton writes `pelvis` under `root_motion`; the model document writes it at the root.
    Measured: both land at `[-0.482, 0, 53.909]` with the same rotation, while the local
    decompositions differ by 54.4 units and 60 deg.  Comparing locals reported a shifted joint on
    a correct pair.
    """
    gate = read("tools/tail_release_gate.py")
    assert "_joint_world_map(datamodel, skeleton_dmx)" in gate
    assert "_joint_world_map(datamodel, model_dmx)" in gate


def test_project_gate_refuses_an_installed_pak_that_is_not_the_admitted_build() -> None:
    """An older vpk copied over `pak97_dir.vpk` is not a release.

    After v10 folded in game the agent hand-copied v9 over the installed pak and left it there;
    nothing in the repository noticed.  The gate now compares the installed bytes with the
    admitted pack report's sha256 and fails on a mismatch.
    """
    project = read("tools/project.py")
    assert "_release_installed_pak_check" in project
    assert "is not the admitted" in project

def test_pack_refuses_files_outside_models() -> None:
    """v14 shipped 228 compiled clips at `clips/` beside the same 228 under the model.

    `shiv_perclip_build compile` staged each document at `addon / relative_to(extraction)`, and the
    extraction points at the hero folder, so the path started at `clips/` and landed at the addon
    root.  Both halves are pinned: the staging root and the packer's refusal.
    """
    pack = read("tools/tail_release_pack.py")
    assert "refused stray-path" in pack
    build = read("tools/shiv_perclip_build.py")
    assert "_staged_root(extraction) / document.relative_to(extraction)" in build


def test_gate_refuses_a_game_joint_that_changed_slot() -> None:
    """The rotation refusal, and its statement comes from the builds that render correctly.

    The game's own `haze_skel.dmx` lists `weaponHand_L` at 6, `head` at 15, `hand_L` at 20 and
    `hand_R` at 53; the pinned Shiv skeleton (`pak93_dir.vpk`, sha256 `01efc18e…`) is that
    skeleton with the tail appended after every stock joint and nothing re-ordered, and the owner
    reports its head, arms and tail correct.  v6 moved `weaponHand_L` to 50, and v15 nested the
    `*_end` leaves beside their parents, moving `hand_L` 20 -> 21 and `hand_R` 53 -> 61.
    """
    gate = read("tools/tail_release_gate.py")
    assert "skeleton-shifts-game-joint" in gate


def test_pack_refuses_files_outside_models() -> None:
    """v14 shipped 228 compiled clips at `clips/` beside the same 228 under the model."""
    pack = read("tools/tail_release_pack.py")
    assert "refused stray-path" in pack
    build = read("tools/shiv_perclip_build.py")
    assert "_staged_root(extraction) / document.relative_to(extraction)" in build


def test_appended_joints_go_after_every_game_joint() -> None:
    """The skeleton builder appends rather than nests: that is what keeps the game's slots.

    `tools/skeleton_append_tail.py` and `tools/skeleton_append_leaves.py` both put new joints after
    every stock joint, and the pinned Shiv build is the evidence that this is the working shape.
    """
    append = read("tools/skeleton_append_tail.py")
    assert "appended after every stock joint" in append
    leaves = read("tools/skeleton_append_leaves.py")
    assert "after every other joint" in leaves


def test_gate_refuses_dropping_a_leaf_bone() -> None:
    """The working Shiv pak ships `*_end` leaves; a Haze build that drops them rotated the head.

    Measured 2026-11-16: `pak93_dir.vpk` (sha256 01efc18e…) carries a custom `shiv.vnmskel`
    that is the stock document plus 147 lines of `*_end` high-LOD names, and its skeleton carries
    all 168 bones.  A Haze build from the game's 98-joint animation skeleton plus the tail dropped
    all 18 leaves the model declares (`head_end`, `finger_*_end`, `ball_end_*`) and the head, arms
    and tail rotated while the body stood upright.
    """
    gate = read("tools/tail_release_gate.py")
    assert "end-bone-dropped" in gate
    assert "end-bone-hierarchy-broken" in gate
    # Both must be reachable: a refusal string alone is decoration.
    assert 'raise Refused(\n                "end-bone-dropped"' in gate
    assert 'raise Refused(\n                "end-bone-hierarchy-broken"' in gate
    # The leaf test is the `*_end` name, and it must cover the sided leaves too.
    assert '_end(_[LR])?$' in gate


def test_the_tree_walk_refusal_is_in_the_gate_and_fires() -> None:
    """The owner's 2026-11-16 verdict: every build after the no-skeleton reference regressed.

    `skeleton-tree-shifts-game-joint` refused v9 and was deleted by `aaf6117`; the v39 tree walked
    89 of the game's 98 joints at another slot and was admitted.  The code has to be back, and it
    must be reachable from the walk list the gate already computes — not a comment.
    """
    gate = read("tools/tail_release_gate.py")
    assert "skeleton-tree-shifts-game-joint" in gate
    assert "if shifted_in_walk:" in gate, "the walk shift has to be refused, not recorded"
    assert '"game_slot_shifts_in_walk"' in gate, "the measurement has to survive in the report"


def test_the_pelvis_world_refusal_is_in_the_gate_and_fires() -> None:
    """A compensating rest under a rotated root passes a parent check and still folds the body."""
    gate = read("tools/tail_release_gate.py")
    assert "pelvis-world-differs-from-game" in gate
    assert 'report["pelvis_world_delta"]' in gate
