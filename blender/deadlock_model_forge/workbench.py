"""Manual workbench operators: map, rename, align, compare and inspect weights."""
from __future__ import annotations

import math
import re

import bpy
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import core, proofing, weights

_SUFFIXES = (
    ("_L", "_R"),
    ("_R", "_L"),
    (".L", ".R"),
    (".R", ".L"),
    ("Left", "Right"),
    ("Right", "Left"),
    ("left", "right"),
    ("right", "left"),
)


def _status(settings, message: str, kind: str = "INFO") -> None:
    core.set_status(settings, message, kind)


def _object_mode(context) -> None:
    active = bpy.context.object
    if active is not None and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _entry(settings):
    if not settings.bone_map:
        return None
    index = max(0, min(int(settings.bone_map_index), len(settings.bone_map) - 1))
    settings.bone_map_index = index
    return settings.bone_map[index]


def _sources(settings) -> list[str]:
    if settings.custom_armature is not None:
        return [bone.name for bone in settings.custom_armature.data.bones]
    if settings.custom_mesh is not None:
        return [group.name for group in settings.custom_mesh.vertex_groups]
    return []


def _targets(settings) -> list[str]:
    if settings.target_armature is None:
        return []
    return [bone.name for bone in settings.target_armature.data.bones]


def scan_bone_map(settings) -> int:
    from forge.names import match

    sources = _sources(settings)
    targets = _targets(settings)
    if not targets:
        raise RuntimeError("bone-map-no-target: import the hero skeleton first")
    if not sources:
        settings.bone_map.clear()
        settings.bone_map_index = 0
        return 0
    result = match(sources, targets)
    collision_sources = {
        source
        for _, group in result.collisions
        for source in group
    }
    settings.bone_map.clear()
    for source in sources:
        entry = settings.bone_map.add()
        entry.source = source
        if source in collision_sources:
            entry.state = "UNMATCHED"
            entry.target = ""
            entry.note = "ambiguous target; choose one explicitly"
        elif source in result.mapping:
            entry.state = "MAPPED"
            entry.target = result.mapping[source]
            entry.note = "exact or normalized"
        else:
            entry.state = "UNMATCHED"
            entry.target = ""
            entry.note = "no exact or normalized target"
    settings.bone_map_index = 0
    return len(sources)


class DMF_OT_scan_bones(Operator):
    bl_idname = "dmf.scan_bones"
    bl_label = "Scan Bone Map"
    bl_description = "Match every custom bone or group by exact name, alias, or normalized name; never guess a nearest bone"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            count = scan_bone_map(settings)
            proofing.bump_tick(settings)
            if not count:
                _status(settings, "No custom rig or groups; Surface + envelope will weight the mesh directly", "INFO")
            else:
                resolved = sum(1 for entry in settings.bone_map if entry.state == "MAPPED")
                _status(settings, f"Scanned {count} source bones; {resolved} mapped, {count - resolved} need a decision", "OK" if resolved == count else "WARN")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_add_bone_entry(Operator):
    bl_idname = "dmf.add_bone_entry"
    bl_label = "Add Map Row"
    bl_description = "Add a manual source-to-target row"

    def execute(self, context):
        settings = context.scene.dmf
        entry = settings.bone_map.add()
        entry.state = "UNMATCHED"
        settings.bone_map_index = len(settings.bone_map) - 1
        return {"FINISHED"}


class DMF_OT_remove_bone_entry(Operator):
    bl_idname = "dmf.remove_bone_entry"
    bl_label = "Remove Map Row"
    bl_description = "Remove the selected bone-map row"

    def execute(self, context):
        settings = context.scene.dmf
        if not settings.bone_map:
            return {"CANCELLED"}
        index = max(0, min(settings.bone_map_index, len(settings.bone_map) - 1))
        settings.bone_map.remove(index)
        settings.bone_map_index = max(0, min(index, len(settings.bone_map) - 1))
        proofing.bump_tick(settings)
        return {"FINISHED"}


class DMF_OT_mark_extra(Operator):
    bl_idname = "dmf.mark_extra"
    bl_label = "Mark Extra"
    bl_description = "Keep this source as an appendage; the extra-bone policy decides whether it is copied or folded"

    def execute(self, context):
        settings = context.scene.dmf
        entry = _entry(settings)
        if entry is None or not entry.source:
            self.report({"ERROR"}, "Choose a map row with a source first")
            return {"CANCELLED"}
        entry.state = "EXTRA"
        entry.target = entry.source
        entry.note = "extra appendage; follows the extra-bone policy"
        proofing.bump_tick(settings)
        _status(settings, f"{entry.source} is extra; set Extra bones to Keep or Fold before binding", "INFO")
        return {"FINISHED"}


class DMF_OT_ignore_entry(Operator):
    bl_idname = "dmf.ignore_entry"
    bl_label = "Ignore"
    bl_description = "Drop this source's weights instead of guessing a hero bone"

    def execute(self, context):
        settings = context.scene.dmf
        entry = _entry(settings)
        if entry is None or not entry.source:
            return {"CANCELLED"}
        entry.state = "IGNORED"
        entry.note = "explicitly dropped"
        proofing.bump_tick(settings)
        _status(settings, f"{entry.source} will be dropped by the solver", "INFO")
        return {"FINISHED"}


class DMF_OT_clear_target(Operator):
    bl_idname = "dmf.clear_target"
    bl_label = "Clear Target"
    bl_description = "Remove the selected row's target and return it to unmatched"

    def execute(self, context):
        settings = context.scene.dmf
        entry = _entry(settings)
        if entry is None:
            return {"CANCELLED"}
        entry.target = ""
        entry.state = "UNMATCHED"
        entry.note = "target cleared"
        proofing.bump_tick(settings)
        return {"FINISHED"}


class DMF_OT_rename_bones(Operator):
    bl_idname = "dmf.rename_bones"
    bl_label = "Rename Source to Target"
    bl_description = "Rename the custom bone and its matching vertex group; refuses a name that is already occupied"

    def execute(self, context):
        settings = context.scene.dmf
        entry = _entry(settings)
        if entry is None or not entry.source or not entry.target:
            self.report({"ERROR"}, "Choose a row with both a source and a target")
            return {"CANCELLED"}
        source, target = entry.source.strip(), entry.target.strip()
        if source == target:
            _status(settings, f"{source} already has the target name", "INFO")
            return {"CANCELLED"}
        try:
            duplicate = [
                row.source
                for row in settings.bone_map
                if row.source != source and row.target.strip() == target and row.state in ("MAPPED", "EXTRA")
            ]
            if duplicate:
                raise RuntimeError(f"bone-rename-collision: {target} is already the target of {', '.join(duplicate)}")
            armature = settings.custom_armature
            mesh = settings.custom_mesh
            if mesh is not None and target in mesh.vertex_groups and target != source:
                raise RuntimeError(f"bone-rename-group-occupied: {target} already exists on the custom mesh")
            if armature is not None:
                if target in armature.data.bones and target != source:
                    raise RuntimeError(f"bone-rename-occupied: {target} already exists on the custom rig")
                _object_mode(context)
                core.select_only(context, [armature])
                bpy.context.view_layer.objects.active = armature
                if bpy.context.object and bpy.context.object.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="EDIT")
                edit_bone = armature.data.edit_bones.get(source)
                if edit_bone is None:
                    raise RuntimeError(f"bone-rename-source-missing: {source}")
                edit_bone.name = target
                bpy.ops.object.mode_set(mode="OBJECT")
            if mesh is not None:
                group = mesh.vertex_groups.get(source)
                if group is not None:
                    group.name = target
            entry.source = target
            entry.target = target
            entry.state = "MAPPED"
            entry.note = "renamed in place"
            proofing.bump_tick(settings)
            _status(settings, f"Renamed {source} to {target} on the rig and matching group", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def _depth(armature, name: str) -> int:
    depth = 0
    bone = armature.data.bones.get(name)
    seen = set()
    while bone is not None and bone.parent is not None and bone.name not in seen:
        seen.add(bone.name)
        depth += 1
        bone = bone.parent
    return depth


def _align_edit_bone(settings, entry) -> None:
    armature = settings.custom_armature
    target = settings.target_armature
    if armature is None or target is None:
        raise RuntimeError("align-needs-two-rigs: choose the custom rig and the hero skeleton")
    source_bone = armature.data.edit_bones.get(entry.source)
    target_bone = target.data.bones.get(entry.target)
    if source_bone is None:
        raise RuntimeError(f"align-source-missing: {entry.source}")
    if target_bone is None:
        raise RuntimeError(f"align-target-missing: {entry.target}")
    world = target.matrix_world @ target_bone.matrix_local
    source_bone.matrix = armature.matrix_world.inverted() @ world


class DMF_OT_align_bone(Operator):
    bl_idname = "dmf.align_bone"
    bl_label = "Align Rest Bone"
    bl_description = "Move the custom rest bone to the hero bone's head, tail and roll"

    def execute(self, context):
        settings = context.scene.dmf
        entry = _entry(settings)
        if entry is None or not entry.source or not entry.target:
            self.report({"ERROR"}, "Choose a mapped row first")
            return {"CANCELLED"}
        try:
            armature = settings.custom_armature
            if armature is None:
                raise RuntimeError("align-needs-custom-rig: choose the custom rig")
            core.select_only(context, [armature])
            bpy.context.view_layer.objects.active = armature
            if bpy.context.object and bpy.context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="EDIT")
            try:
                _align_edit_bone(settings, entry)
            finally:
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.context.view_layer.update()
            proofing.bump_tick(settings)
            _status(settings, f"Aligned {entry.source} to {entry.target}; rebind if the mesh already had weights", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_align_all_bones(Operator):
    bl_idname = "dmf.align_all_bones"
    bl_label = "Align All Mapped"
    bl_description = "Align every mapped rest bone in parent order"

    def execute(self, context):
        settings = context.scene.dmf
        armature = settings.custom_armature
        if armature is None:
            self.report({"ERROR"}, "Choose the custom rig first")
            return {"CANCELLED"}
        mapped = [entry for entry in settings.bone_map if entry.state == "MAPPED" and entry.source and entry.target]
        if not mapped:
            self.report({"ERROR"}, "No mapped rows to align")
            return {"CANCELLED"}
        try:
            core.select_only(context, [armature])
            bpy.context.view_layer.objects.active = armature
            if bpy.context.object and bpy.context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="EDIT")
            try:
                for entry in sorted(mapped, key=lambda row: _depth(armature, row.source)):
                    _align_edit_bone(settings, entry)
            finally:
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.context.view_layer.update()
            proofing.bump_tick(settings)
            _status(settings, f"Aligned {len(mapped)} mapped rest bones", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_copy_pose(Operator):
    bl_idname = "dmf.copy_pose"
    bl_label = "Copy Hero Pose"
    bl_description = "Copy the hero's current pose matrix to the selected custom bone"

    def execute(self, context):
        settings = context.scene.dmf
        entry = _entry(settings)
        if entry is None or not entry.source or not entry.target:
            self.report({"ERROR"}, "Choose a mapped row first")
            return {"CANCELLED"}
        armature = settings.custom_armature
        target = settings.target_armature
        if armature is None or target is None:
            self.report({"ERROR"}, "Both rigs must be present")
            return {"CANCELLED"}
        source_pose = armature.pose.bones.get(entry.source)
        target_pose = target.pose.bones.get(entry.target)
        if source_pose is None or target_pose is None:
            self.report({"ERROR"}, "Pose bone is missing; check the mapped names")
            return {"CANCELLED"}
        source_pose.matrix = armature.matrix_world.inverted() @ target.matrix_world @ target_pose.matrix
        bpy.context.view_layer.update()
        proofing.bump_tick(settings)
        _status(settings, f"Copied {entry.target} pose to {entry.source}", "OK")
        return {"FINISHED"}


class DMF_OT_nudge_bone(Operator):
    bl_idname = "dmf.nudge_bone"
    bl_label = "Nudge Bone"
    bl_description = "Translate or rotate the selected custom bone in pose space"

    direction: bpy.props.IntProperty(default=1, min=-1, max=1)

    def execute(self, context):
        settings = context.scene.dmf
        entry = _entry(settings)
        armature = settings.custom_armature
        if entry is None or not entry.source or armature is None:
            self.report({"ERROR"}, "Choose a mapped row and a custom rig")
            return {"CANCELLED"}
        pose_bone = armature.pose.bones.get(entry.source)
        if pose_bone is None:
            self.report({"ERROR"}, f"Pose bone missing: {entry.source}")
            return {"CANCELLED"}
        axis = {"X": 0, "Y": 1, "Z": 2}[settings.nudge_axis]
        amount = float(settings.nudge_amount) * int(self.direction)
        if settings.nudge_rotate:
            pose_bone.rotation_mode = "XYZ"
            pose_bone.rotation_euler[axis] += amount
        else:
            pose_bone.location[axis] += amount
        bpy.context.view_layer.update()
        proofing.bump_tick(settings)
        _status(settings, f"Nudged {entry.source} {settings.nudge_axis} by {amount:+.4f}", "INFO")
        return {"FINISHED"}


def _view3d_areas(context):
    if context.screen is None:
        return []
    return [area for area in context.screen.areas if area.type == "VIEW_3D"]


def _split(context):
    areas = _view3d_areas(context)
    area = context.area if context.area and context.area.type == "VIEW_3D" else (areas[0] if areas else None)
    if area is None:
        raise RuntimeError("compare-needs-viewport: open a 3D viewport first")
    region = next((item for item in area.regions if item.type == "WINDOW"), None)
    if region is None:
        raise RuntimeError("compare-needs-window: the 3D viewport has no window region")
    with context.temp_override(area=area, region=region):
        bpy.ops.screen.area_split(direction="VERTICAL", factor=0.5)


def _local_view(context, area, objects, enable: bool) -> None:
    region = next((item for item in area.regions if item.type == "WINDOW"), None)
    if region is None or area.spaces.active is None:
        return
    _object_mode(context)
    with context.temp_override(area=area, region=region, space_data=area.spaces.active):
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            if obj is not None:
                obj.select_set(True)
        if objects:
            bpy.context.view_layer.objects.active = objects[0]
        active = area.spaces.active
        if enable and active.local_view is None:
            bpy.ops.view3d.localview()
        elif not enable and active.local_view is not None:
            bpy.ops.view3d.localview()
        try:
            bpy.ops.view3d.view_selected()
        except Exception:
            pass


def _compare_objects(settings):
    right_armature = settings.custom_armature
    mesh = settings.custom_mesh
    if mesh is not None and settings.target_armature is not None:
        if any(mod.type == "ARMATURE" and mod.object is settings.target_armature for mod in mesh.modifiers):
            right_armature = settings.target_armature
    left = [obj for obj in (settings.target_body, settings.target_armature) if obj is not None]
    right = [obj for obj in (mesh, right_armature) if obj is not None]
    return left, right


class DMF_OT_compare_split(Operator):
    bl_idname = "dmf.compare_split"
    bl_label = "Split Compare"
    bl_description = "Split the viewport and isolate hero body left, custom mesh right, both on the same rig"

    def execute(self, context):
        settings = context.scene.dmf
        if settings.custom_mesh is None or settings.target_armature is None:
            self.report({"ERROR"}, "Import the hero skeleton and custom mesh first")
            return {"CANCELLED"}
        try:
            if len(_view3d_areas(context)) < 2:
                _split(context)
            areas = sorted(_view3d_areas(context), key=lambda area: (area.x, area.y))
            if len(areas) < 2:
                raise RuntimeError("compare-split-failed: Blender did not create a second 3D area")
            left, right = _compare_objects(settings)
            _local_view(context, areas[0], left, True)
            _local_view(context, areas[-1], right, True)
            settings.compare_active = True
            _status(settings, "Split compare: hero body left, custom mesh right; both use the same target rig", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_compare_clear(Operator):
    bl_idname = "dmf.compare_clear"
    bl_label = "Clear Compare Views"
    bl_description = "Leave local view in every 3D viewport; the split itself stays"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            for area in _view3d_areas(context):
                if area.spaces.active is not None and area.spaces.active.local_view is not None:
                    _local_view(context, area, [], False)
            settings.compare_active = False
            _status(settings, "Cleared comparison local views", "INFO")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_apply_compare_action(Operator):
    bl_idname = "dmf.apply_compare_action"
    bl_label = "Apply Preview Action"
    bl_description = "Put the same action on the hero rig and the custom rig, if both exist"

    def execute(self, context):
        settings = context.scene.dmf
        action = settings.compare_action
        if action is None:
            self.report({"ERROR"}, "Choose a preview action first")
            return {"CANCELLED"}
        try:
            for armature in (settings.target_armature, settings.custom_armature):
                if armature is None:
                    continue
                animation = armature.animation_data_create()
                animation.action = action
                if hasattr(animation, "action_slot") and getattr(action, "slots", None):
                    animation.action_slot = action.slots[0]
            bpy.context.scene.frame_set(bpy.context.scene.frame_current)
            bpy.context.view_layer.update()
            _status(settings, f"Preview action {action.name} applied to both rigs", "OK")
        except Exception as error:
            _status(settings, f"Could not apply preview action: {error}", "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def _selected_indices(mesh) -> list[int]:
    if bpy.context.object and bpy.context.object.mode == "EDIT":
        bpy.ops.object.mode_set(mode="OBJECT")
    return [vertex.index for vertex in mesh.data.vertices if vertex.select]


def _mesh_group_weights(mesh, group):
    result = {}
    for vertex in mesh.data.vertices:
        try:
            weight = group.weight(vertex.index)
        except RuntimeError:
            continue
        if weight > 0:
            result[vertex.index] = weight
    return result


class DMF_OT_select_unweighted(Operator):
    bl_idname = "dmf.select_unweighted"
    bl_label = "Select Unweighted"
    bl_description = "Select vertices with no positive weight in any group"

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        if mesh is None:
            self.report({"ERROR"}, "Choose the custom mesh first")
            return {"CANCELLED"}
        _object_mode(context)
        core.select_only(context, [mesh])
        bpy.context.view_layer.objects.active = mesh
        selected = []
        for vertex in mesh.data.vertices:
            if not any(item.weight > 1e-8 for item in vertex.groups):
                vertex.select = True
                selected.append(vertex.index)
            else:
                vertex.select = False
        bpy.ops.object.mode_set(mode="EDIT")
        _status(settings, f"Selected {len(selected):,} unweighted vertices", "OK" if selected else "INFO")
        return {"FINISHED"}


class DMF_OT_assign_active_bone(Operator):
    bl_idname = "dmf.assign_active_bone"
    bl_label = "Assign Selected"
    bl_description = "Assign the selected vertices to the active vertex group at the declared weight"

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        if mesh is None or not mesh.vertex_groups.active:
            self.report({"ERROR"}, "Choose the custom mesh and an active vertex group")
            return {"CANCELLED"}
        indices = _selected_indices(mesh)
        if not indices:
            self.report({"ERROR"}, "Select vertices in Edit Mode first")
            return {"CANCELLED"}
        group = mesh.vertex_groups.active
        group.add(indices, float(settings.manual_weight), "REPLACE")
        proofing.bump_tick(settings)
        _status(settings, f"Assigned {len(indices):,} vertices to {group.name} at {settings.manual_weight:.3f}", "OK")
        return {"FINISHED"}


class DMF_OT_smooth_active_group(Operator):
    bl_idname = "dmf.smooth_active_group"
    bl_label = "Smooth Active Group"
    bl_description = "Smooth the active group across mesh edges; selected vertices only when a selection exists"

    iterations: bpy.props.IntProperty(default=2, min=1, max=8)

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        if mesh is None or not mesh.vertex_groups.active:
            self.report({"ERROR"}, "Choose the custom mesh and an active vertex group")
            return {"CANCELLED"}
        selected = set(_selected_indices(mesh))
        group = mesh.vertex_groups.active
        weights = _mesh_group_weights(mesh, group)
        neighbors = [[] for _ in mesh.data.vertices]
        for edge in mesh.data.edges:
            a, b = edge.vertices
            neighbors[a].append(b)
            neighbors[b].append(a)
        targets = selected or set(range(len(mesh.data.vertices)))
        for _ in range(max(1, int(self.iterations))):
            updated = {}
            for index in targets:
                linked = neighbors[index]
                if not linked:
                    continue
                average = sum(weights.get(other, 0.0) for other in linked) / len(linked)
                updated[index] = (weights.get(index, 0.0) * 0.5) + (average * 0.5)
            weights.update(updated)
        for index, weight in weights.items():
            if weight > 1e-8:
                group.add([index], weight, "REPLACE")
            else:
                group.remove([index])
        proofing.bump_tick(settings)
        _status(settings, f"Smoothed {group.name} over {len(targets):,} vertices", "OK")
        return {"FINISHED"}


def _rewrite_vertex_weights(mesh, max_influences: int, normalize_only: bool = False):
    names = {group.index: group.name for group in mesh.vertex_groups}
    groups = {group.name: group for group in mesh.vertex_groups}
    for vertex in mesh.data.vertices:
        current = {}
        for item in vertex.groups:
            name = names.get(item.group, "")
            if name and item.weight > 1e-8:
                current[name] = float(item.weight)
        from forge.weights import normalize_weights

        updated = normalize_weights(current, max_influences=max_influences)
        for name, weight in updated.items():
            group = groups.get(name) or mesh.vertex_groups.new(name=name)
            groups[name] = group
            group.add([vertex.index], weight, "REPLACE")
        for name in set(current) - set(updated):
            group = groups.get(name)
            if group is not None:
                group.remove([vertex.index])


class DMF_OT_normalize_weights(Operator):
    bl_idname = "dmf.normalize_weights"
    bl_label = "Normalize Weights"
    bl_description = "Normalize every vertex to the influence limit"

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        if mesh is None:
            self.report({"ERROR"}, "Choose the custom mesh first")
            return {"CANCELLED"}
        _rewrite_vertex_weights(mesh, int(settings.max_influences), normalize_only=True)
        proofing.bump_tick(settings)
        _status(settings, f"Normalized weights to {settings.max_influences} influences", "OK")
        return {"FINISHED"}


class DMF_OT_limit_influences(Operator):
    bl_idname = "dmf.limit_influences"
    bl_label = "Limit Influences"
    bl_description = "Drop the weakest weights above the influence limit, then normalize"

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        if mesh is None:
            self.report({"ERROR"}, "Choose the custom mesh first")
            return {"CANCELLED"}
        _rewrite_vertex_weights(mesh, int(settings.max_influences))
        proofing.bump_tick(settings)
        _status(settings, f"Limited weights to {settings.max_influences} influences", "OK")
        return {"FINISHED"}


class DMF_OT_remove_zero_weights(Operator):
    bl_idname = "dmf.remove_zero_weights"
    bl_label = "Remove Zero Weights"
    bl_description = "Remove zero and sub-epsilon memberships from every group"

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        if mesh is None:
            self.report({"ERROR"}, "Choose the custom mesh first")
            return {"CANCELLED"}
        for group in mesh.vertex_groups:
            drop = [
                vertex.index
                for vertex in mesh.data.vertices
                for item in vertex.groups
                if item.group == group.index and item.weight <= 1e-8
            ]
            if drop:
                group.remove(drop)
        proofing.bump_tick(settings)
        _status(settings, "Removed zero weights", "OK")
        return {"FINISHED"}


class DMF_OT_mirror_weights(Operator):
    bl_idname = "dmf.mirror_weights"
    bl_label = "Mirror L/R"
    bl_description = "Copy each left/right group's weights to its opposite suffix"

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        if mesh is None:
            self.report({"ERROR"}, "Choose the custom mesh first")
            return {"CANCELLED"}
        copied = 0
        for group in list(mesh.vertex_groups):
            for source_suffix, target_suffix in _SUFFIXES:
                if not group.name.endswith(source_suffix):
                    continue
                target_name = group.name[: -len(source_suffix)] + target_suffix
                target = mesh.vertex_groups.get(target_name) or mesh.vertex_groups.new(name=target_name)
                for vertex in mesh.data.vertices:
                    try:
                        weight = group.weight(vertex.index)
                    except RuntimeError:
                        continue
                    if weight > 1e-8:
                        target.add([vertex.index], weight, "REPLACE")
                        copied += 1
                break
        proofing.bump_tick(settings)
        _status(settings, f"Mirrored {copied:,} L/R weights", "OK")
        return {"FINISHED"}


class DMF_OT_mint_proof(Operator):
    bl_idname = "dmf.mint_proof"
    bl_label = "Mint Axis Proof"
    bl_description = "Measure the current weights and write the BLAKE3 proof artifact"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            options = weights.WeightOptions.from_settings(settings)
            proof, admission = proofing.mint(settings, options)
            if admission.ok:
                _status(settings, f"Proof {proof.artifact_digest[:18]} is current at tick {settings.axis_tick}", "OK")
            else:
                _status(settings, "Proof refused: " + "; ".join(admission.reasons()), "ERROR")
                self.report({"WARNING"}, "The proof was written but refused; export stays blocked")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_verify_proof(Operator):
    bl_idname = "dmf.verify_proof"
    bl_label = "Verify Proof"
    bl_description = "Check the proof bytes, tick, world digest and every live weight check"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            admission = proofing.verify(settings)
            if admission.ok:
                _status(settings, f"Proof current at tick {settings.axis_tick}", "OK")
            else:
                _status(settings, "Proof refused: " + "; ".join(admission.reasons()), "ERROR")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_cancel_weight_job(Operator):
    bl_idname = "dmf.cancel_weight_job"
    bl_label = "Cancel Weight Solve"
    bl_description = "Stop after the current vertex chunk"

    def execute(self, context):
        settings = context.scene.dmf
        weights.cancel()
        _status(settings, "Weight solve cancellation requested", "WARN")
        return {"FINISHED"}


CLASSES = (
    DMF_OT_scan_bones,
    DMF_OT_add_bone_entry,
    DMF_OT_remove_bone_entry,
    DMF_OT_mark_extra,
    DMF_OT_ignore_entry,
    DMF_OT_clear_target,
    DMF_OT_rename_bones,
    DMF_OT_align_bone,
    DMF_OT_align_all_bones,
    DMF_OT_copy_pose,
    DMF_OT_nudge_bone,
    DMF_OT_compare_split,
    DMF_OT_compare_clear,
    DMF_OT_apply_compare_action,
    DMF_OT_select_unweighted,
    DMF_OT_assign_active_bone,
    DMF_OT_smooth_active_group,
    DMF_OT_normalize_weights,
    DMF_OT_limit_influences,
    DMF_OT_remove_zero_weights,
    DMF_OT_mirror_weights,
    DMF_OT_mint_proof,
    DMF_OT_verify_proof,
    DMF_OT_cancel_weight_job,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
