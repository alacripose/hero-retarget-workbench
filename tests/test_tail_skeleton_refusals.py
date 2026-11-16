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


def test_gate_refuses_a_skeleton_that_moves_a_game_joint() -> None:
    gate = read("tools/tail_release_gate.py")
    assert "skeleton-shifts-game-joint" in gate
    # The refusal must be computed from the joint list, never from the tree walk.
    assert "def _joint_list_order(" in gate
    block = gate[gate.index("skeleton-shifts-game-joint") - 2000 : gate.index("skeleton-shifts-game-joint")]
    assert "_joint_list_order(datamodel, game_skeleton)" in block, "the game's slots must come from its jointList"
    assert "_joint_list_order(datamodel, skeleton_dmx)" in block, "our slots must come from ours"


def test_gate_refuses_a_tree_walk_that_moves_a_game_joint() -> None:
    """v9 kept the game prefix in `jointList` and still rotated: its tree walked differently."""
    gate = read("tools/tail_release_gate.py")
    assert "skeleton-tree-shifts-game-joint" in gate
    block = gate[gate.index("skeleton-tree-shifts-game-joint") - 1500 : gate.index("skeleton-tree-shifts-game-joint")]
    assert "skeleton_joints" in block, "the walked order must come from the skeleton document"
    assert "_joint_list_order(datamodel, game_skeleton)" in block, "the wanted order is the game's list"


def test_gate_refuses_a_model_that_does_not_declare_a_skeleton_joint() -> None:
    gate = read("tools/tail_release_gate.py")
    assert "model-vmdl-missing-skeleton-joint" in gate


def test_packer_cannot_pack_without_the_game_skeleton() -> None:
    packer = read("tools/tail_release_pack.py")
    assert "gate-needs-game-skeleton" in packer
    # It has to reach the gate as well, or the refusal above is decoration.
    assert '["--game-skeleton", args.game_skeleton]' in packer


def test_gate_refuses_a_pelvis_that_lands_off_the_game_pose() -> None:
    """The v8 build collapsed in on itself because pelvis inherited root_motion's 90 deg twice.

    A parent and a rest are one fact: our compensated rest at a root and the game's rest under
    the game's parent describe the same pose, but mixing them doubles the offset.  So the check
    is on the world transform, not on which parent is used.
    """
    gate = read("tools/tail_release_gate.py")
    assert "pelvis-world-differs-from-game" in gate
    assert "_joint_world(" in gate


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


def test_tree_check_compares_walks_not_the_game_list() -> None:
    """The game's own skeleton walks 4 joints out of its list order (measured 2026-11-16).

    `clavicle_R`, `leg_upper_L`, `leg_upper_R` and `attachWorld` sit in a different order in
    `haze_skel.dmx`'s tree than in its own `jointList`, so a check that a walk is a subsequence of
    that list refuses the game's own file — it refused ours for exactly those 4 joints.  The walk
    must be compared against the game's walk; the list is a separate contract, checked separately.
    """
    gate = read("tools/tail_release_gate.py")
    assert "_joint_tree_order(datamodel, game_skeleton)" in gate
    assert "game_walk_vs_list_inversions" in gate


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
