"""Which bones an animation clip may rotate freely and which are solver inputs.

Source 2 clips carry the bones the animgraph's IK and aim nodes read as ordinary
tracks: ``arm_L_IKTARGET``, ``leg_R_OFFSET``, ``chestHier_OFFSET``, ``muzzle_*``,
``weaponHand_*``.  They are proxies, not limbs.  A bake that divides the animated
root's rotation out of every bone therefore hands the solver a target turned by
the root -- measured at 120 deg on the arm targets and 240 deg on the leg and
chest offsets in Shiv's ``item_run_center`` -- and the engine then solves the arms
and head against it (rotated wrong) and the feet off the ground (the hero lifts
for the first frames of movement).

This module holds that rule so it can be tested without Blender.
"""
from __future__ import annotations

SOLVER_SUFFIXES = ("_IKTARGET", "_OFFSET")
SOLVER_PREFIXES = ("muzzle", "weaponHand")


def is_solver_input(name: str) -> bool:
    """True when ``name`` is a target/offset the animgraph solves from."""
    return name.endswith(SOLVER_SUFFIXES) or name.startswith(SOLVER_PREFIXES)
