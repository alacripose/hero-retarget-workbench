"""IK target constraints and visual baking for animation clips.

Source 2 IK chains solve limbs from target bones that sit outside the pelvis
hierarchy.  A Blender action carries those bones' local transforms, not the
solved limbs, so the community workflow is: constrain each target to the real
limb with Copy Location and Copy Rotation, animate, bake with visual keying, and
clear the constraints before exporting the DMX.  This module is the Blender half
of that workflow; ``forge.ik`` recognises the targets and suggests limbs without
touching the rig.

Only constraints this addon created are removed.  A user's own constraints stay,
and no vmdl or compiled clip is read.
"""
from __future__ import annotations

from dataclasses import dataclass

import bpy
from bpy.types import Operator
from forge import ik as ikscan

from . import core

# Constraints do not support custom ID properties in Blender 5.4. The name is
# the tag; it is also what the user sees in the constraint stack.
_TAG_PREFIX = "DMF IK "


@dataclass
class BakeResult:
    frames: int
    cleared: int
    action: str


def _armature(settings):
    armature = settings.target_armature
    if armature is None:
        raise RuntimeError("ik-needs-hero: import the hero skeleton first")
    if armature.type != "ARMATURE":
        raise RuntimeError("ik-needs-hero: the hero skeleton is not an armature")
    return armature


def _tagged(pose_bone) -> list:
    return [
        constraint
        for constraint in pose_bone.constraints
        if constraint.name.startswith(_TAG_PREFIX)
    ]


def _remove_tagged(armature, bone_name: str) -> int:
    pose_bone = armature.pose.bones.get(bone_name)
    if pose_bone is None:
        return 0
    removed = 0
    for constraint in _tagged(pose_bone):
        pose_bone.constraints.remove(constraint)
        removed += 1
    return removed


def constraint_count(armature, bone_name: str) -> int:
    pose_bone = armature.pose.bones.get(bone_name)
    return len(_tagged(pose_bone)) if pose_bone is not None else 0


def has_constraints(armature) -> bool:
    """True while any constraint this addon made is still on the rig."""
    return any(_tagged(pose_bone) for pose_bone in armature.pose.bones)


def scan(settings) -> int:
    """List IK targets and a suggested limb for each; nothing is edited."""
    armature = _armature(settings)
    names = [bone.name for bone in armature.data.bones]
    found = ikscan.scan(names)
    settings.ik_bones.clear()
    for item in found:
        row = settings.ik_bones.add()
        row.bone = item.bone
        row.target = item.target
        row.state = "READY" if item.ready else "CHOOSE"
        row.constraints = constraint_count(armature, item.bone)
    settings.ik_index = 0
    settings.ik_scanned = len(found)
    return len(found)


def apply(settings) -> int:
    """Add Copy Location + Copy Rotation from each target to its chosen limb."""
    armature = _armature(settings)
    made = 0
    for row in settings.ik_bones:
        target = (row.target or "").strip()
        pose_bone = armature.pose.bones.get(row.bone)
        if pose_bone is None:
            row.state = "MISSING"
            continue
        if not target:
            row.state = "CHOOSE"
            row.constraints = 0
            continue
        if target not in armature.data.bones:
            row.state = "MISSING"
            row.constraints = 0
            continue
        _remove_tagged(armature, row.bone)
        for kind, name in (("COPY_LOCATION", "DMF IK Loc"), ("COPY_ROTATION", "DMF IK Rot")):
            constraint = pose_bone.constraints.new(kind)
            constraint.name = name
            constraint.target = armature
            constraint.subtarget = target
            constraint.target_space = "POSE"
            constraint.owner_space = "POSE"
            if hasattr(constraint, "mix_mode"):
                constraint.mix_mode = "REPLACE"
            made += 1
        row.constraints = 2
        row.state = "APPLIED"
    return made


def clear(settings) -> int:
    """Remove only the IK constraints this addon made."""
    armature = _armature(settings)
    removed = 0
    for row in settings.ik_bones:
        removed += _remove_tagged(armature, row.bone)
        row.constraints = constraint_count(armature, row.bone)
        row.state = "READY" if (row.target or "").strip() else "CHOOSE"
    return removed


def _frame_range(armature) -> tuple[int, int]:
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        raise RuntimeError("ik-bake-needs-action: import a clip before baking")
    start, end = (int(round(value)) for value in action.frame_range)
    if end <= start:
        scene = bpy.context.scene
        start, end = int(scene.frame_start), int(scene.frame_end)
    if end <= start:
        raise RuntimeError("ik-bake-empty-range: the action has no frame range")
    return start, end


def bake(settings) -> BakeResult:
    """Bake the active action with visual keying, then remove addon constraints.

    Every pose bone is baked, so extra bones kept from a custom rig (a tail, for
    example) are carried by the same action; none of them needs a separate bake.
    """
    armature = _armature(settings)
    if not any(constraint_count(armature, row.bone) for row in settings.ik_bones):
        raise RuntimeError("ik-bake-needs-constraints: apply IK constraints first")
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        raise RuntimeError("ik-bake-needs-action: import a clip before baking")
    start, end = _frame_range(armature)
    scene = bpy.context.scene
    active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    old_mode = armature.mode
    try:
        core.select_only(bpy.context, [armature])
        bpy.context.view_layer.objects.active = armature
        if armature.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="POSE")
        result = bpy.ops.nla.bake(
            frame_start=start,
            frame_end=end,
            step=1,
            only_selected=False,
            visual_keying=True,
            clear_constraints=False,
            clear_parents=False,
            use_current_action=True,
            bake_types={"POSE"},
        )
    finally:
        current = bpy.data.objects.get(armature.name) or armature
        if current.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        core.select_only(bpy.context, selected)
        if active is not None:
            bpy.context.view_layer.objects.active = active
    if "FINISHED" not in result:
        raise RuntimeError("ik-bake-refused: Blender did not finish the pose bake")
    cleared = clear(settings)
    settings.ik_note = (
        f"Baked {action.name} frames {start}-{end}; removed {cleared} IK constraints. "
        "The action now carries every pose bone, including extra tail bones."
    )
    return BakeResult(frames=end - start + 1, cleared=cleared, action=action.name)


class DMF_OT_scan_ik(Operator):
    bl_idname = "dmf.scan_ik"
    bl_label = "Find IK Bones"
    bl_description = "List Source 2 IK target bones on the hero rig and suggest the limb each follows"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            count = scan(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        ready = sum(1 for row in settings.ik_bones if row.target)
        core.set_status(
            settings,
            f"{count} IK targets; {ready} have a suggested limb" if count else "No IK target bones on this rig",
            "OK" if count else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_apply_ik(Operator):
    bl_idname = "dmf.apply_ik"
    bl_label = "Apply IK Constraints"
    bl_description = "Add Copy Location and Copy Rotation from each IK target to its chosen limb"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            made = apply(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(
            settings,
            f"Added {made} IK constraints on {made // 2} targets" if made else "No target with a limb chosen",
            "OK" if made else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_bake_ik(Operator):
    bl_idname = "dmf.bake_ik"
    bl_label = "Bake Action"
    bl_description = "Bake the active action with visual keying, then remove this addon's IK constraints"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            result = bake(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, settings.ik_note, "OK")
        self.report({"INFO"}, f"Baked {result.frames} frames into {result.action}")
        return {"FINISHED"}


class DMF_OT_clear_ik(Operator):
    bl_idname = "dmf.clear_ik"
    bl_label = "Clear IK Constraints"
    bl_description = "Remove only the IK constraints this addon added; bones and keys stay"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            removed = clear(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, f"Removed {removed} IK constraints" if removed else "No addon IK constraints to remove", "OK" if removed else "INFO")
        return {"FINISHED"}


CLASSES = (
    DMF_OT_scan_ik,
    DMF_OT_apply_ik,
    DMF_OT_bake_ik,
    DMF_OT_clear_ik,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
