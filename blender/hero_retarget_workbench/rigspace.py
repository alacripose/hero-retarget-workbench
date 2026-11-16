"""Re-parenting `pelvis` under `root_motion`: measured, and NOT a fix.

The stock clips declare `pelvis` as a child of `root_motion`, while the animation
DMX these tools export declare it as a root bone. Restoring that parent makes a
compiled clip round-trip exactly through PulseSrcOps' reader, which is why this
looked right (`tools/shiv_pelvis_parent_probe.py`,
`artifacts/receipts/shiv-pelvis-parent.json`, and the 181-clip Axis proof in
`artifacts/receipts/shiv-merge-proof.json`).

It is wrong in the game. The body curves in these clips are authored against a
constant `root_motion` rotation of 1.5708 on X and Z (AGENTS.md, 2026-11-14,
"the 90 degree root is authored and must stay"). A pelvis left at the root never
inherits it; a pelvis parented under it does, and the owner's report on the build
carrying this change was *"now he's lying horizontally in the ground"*. The
06:47 base is upright with `pelvis` at the root, and that is the accepted
standing.

So the reader round-trip is not the acceptance surface. The loaded game is. This
module stays as the record of the experiment and of the reader-level measurement
it produced; no publish or merge path calls it.
"""
from __future__ import annotations


def parent_pelvis(rig) -> list[str]:
    """Return the bones whose rest would move; this function changes nothing.

    Kept for the probe that measured the reader round-trip. Any caller that
    re-parents `pelvis` under `root_motion` before export regresses the standing
    pose in game -- see the module docstring.
    """
    moved: list[str] = []
    pelvis = rig.data.bones.get("pelvis") if getattr(rig, "data", None) else None
    root = rig.data.bones.get("root_motion") if getattr(rig, "data", None) else None
    if pelvis is None or root is None:
        return moved
    if pelvis.parent is not None and pelvis.parent.name == "root_motion":
        return moved
    return ["pelvis"]
