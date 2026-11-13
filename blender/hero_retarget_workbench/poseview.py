"""Show the source rig in the hero's reference pose, live, while the map is made.

A custom model usually arrives in a T-pose or an A-pose while the hero rig rests
in its own reference stance. The preview writes the hero's rest orientation onto
every mapped custom bone (keeping each bone's own head position), so the mesh
visibly moves into the hero's stance as rows get mapped and the split compare
shows both models in the same pose. It writes pose transforms only — no rest
edit, no keys — so clearing it restores the model exactly.
"""
from __future__ import annotations

import re

import bpy
from bpy.types import Operator
from forge import bonerules, posematch
from mathutils import Matrix, Vector

from . import core, proofing

def _key(name: str) -> str:
    """Side-free, separator-free, order-free spelling of a stem."""
    stem, _side = bonerules.split_side(name)
    return "".join(sorted(re.sub(r"[^a-z0-9]", "", stem.lower())))


# Compared through _key, because a rig may spell the same joint arm_upper or upperarm.
_UPPER_ARM_KEYS = {_key(word) for word in ("arm_upper", "upperarm", "shoulder", "deltoid", "clavicle")}


def mapping(settings) -> dict[str, str]:
    return {
        entry.source: entry.target
        for entry in settings.bone_map
        if entry.state == "MAPPED" and entry.source and entry.target
    }


def pairs(settings) -> list[posematch.Pair]:
    custom = settings.custom_armature
    hero = settings.target_armature
    if custom is None or hero is None:
        return []
    parents = {bone.name: (bone.parent.name if bone.parent else None) for bone in custom.data.bones}
    return posematch.pairs(
        mapping(settings),
        parents,
        [bone.name for bone in custom.data.bones],
        [bone.name for bone in hero.data.bones],
    )


def arm_bone_names(settings, armature) -> list[str]:
    """The bones whose direction says how the arms rest.

    A source rig rarely uses the hero's spelling, so the rows that already point
    at an upper-arm hero bone are read first; only then does the rig's own naming
    get a chance.
    """
    bones = armature.data.bones
    mapped = [
        entry.source
        for entry in settings.bone_map
        if entry.state == "MAPPED"
        and entry.source in bones
        and entry.target
        and _key(entry.target) in _UPPER_ARM_KEYS
    ]
    if mapped:
        return mapped
    return [bone.name for bone in bones if _key(bone.name) in _UPPER_ARM_KEYS]


def stance(settings) -> tuple[str, float]:
    """T-pose, A-pose or arms-down for the rig the user is working on."""
    armature = settings.custom_armature or settings.target_armature
    if armature is None:
        return ("unknown", 0.0)
    directions = []
    for name in arm_bone_names(settings, armature):
        bone = armature.data.bones.get(name)
        if bone is None:
            continue
        direction = Vector(bone.tail_local) - Vector(bone.head_local)
        directions.append((float(direction.x), float(direction.y), float(direction.z)))
    return posematch.stance(directions)


def apply(settings) -> int:
    """Rotate every mapped custom bone onto the hero's rest orientation."""
    custom = settings.custom_armature
    hero = settings.target_armature
    if custom is None or hero is None:
        raise RuntimeError("ref-pose-needs-both-rigs: import the hero skeleton and the custom rig")
    rows = pairs(settings)
    if not rows:
        raise RuntimeError("ref-pose-no-mapped-bones: map at least one bone that exists in both rigs")
    hero_to_custom = custom.matrix_world.inverted() @ hero.matrix_world
    view_layer = bpy.context.view_layer
    changed = 0
    for row in rows:
        pose_bone = custom.pose.bones.get(row.source)
        hero_bone = hero.data.bones.get(row.target)
        if pose_bone is None or hero_bone is None:
            continue
        rotation = (hero_to_custom @ hero_bone.matrix_local).to_3x3()
        # The head stays where the custom rig put it: this is a pose preview, not
        # a rest-align, so the mesh must not teleport between poses.
        pose_bone.matrix = Matrix.Translation(pose_bone.bone.head_local) @ rotation.to_4x4()
        view_layer.update()
        changed += 1
    return changed


def clear(settings) -> int:
    """Return every mapped custom bone to its own rest pose."""
    custom = settings.custom_armature
    if custom is None:
        return 0
    cleared = 0
    for source in mapping(settings):
        pose_bone = custom.pose.bones.get(source)
        if pose_bone is None:
            continue
        pose_bone.matrix_basis.identity()
        cleared += 1
    if cleared:
        bpy.context.view_layer.update()
    return cleared


def refresh(settings) -> None:
    """Re-apply after a mapping change; a failure is reported, never raised."""
    kind, angle = stance(settings)
    settings.pose_stance = kind if kind == "unknown" else f"{kind} {angle:.0f}°"
    if not settings.pose_preview:
        settings.pose_preview_error = ""
        return
    try:
        count = apply(settings)
        settings.pose_preview_error = "" if count else "nothing mapped yet"
    except Exception as error:
        settings.pose_preview_error = str(error)


class DMF_OT_pose_preview(Operator):
    bl_idname = "dmf.pose_preview"
    bl_label = "Show Ref Pose"
    bl_description = "Pose every mapped custom bone in the hero's reference stance; no rest edit and no keys"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            count = apply(settings)
            settings.pose_preview = True
            settings.pose_preview_error = ""
            kind, angle = stance(settings)
            where = "" if kind == "unknown" else f"; source rig is {kind}-pose at {angle:.0f}°"
            core.set_status(settings, f"Ref pose on {count} bones{where}", "OK")
        except Exception as error:
            settings.pose_preview = False
            settings.pose_preview_error = str(error)
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_pose_clear(Operator):
    bl_idname = "dmf.pose_clear"
    bl_label = "Clear Ref Pose"
    bl_description = "Put every mapped custom bone back in its own rest pose"

    def execute(self, context):
        settings = context.scene.dmf
        count = clear(settings)
        settings.pose_preview = False
        settings.pose_preview_error = ""
        core.set_status(settings, f"Cleared the ref pose on {count} bones" if count else "No mapped bone to clear", "INFO")
        return {"FINISHED"}


CLASSES = (DMF_OT_pose_preview, DMF_OT_pose_clear)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
