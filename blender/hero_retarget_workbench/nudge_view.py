"""Viewport guides for the hand/bone nudge pass.

The selected bone's rest and current segments are drawn over a screen-space
radial field: hot at the rest head, cooling toward the edge.  The field radius is
independent of the model, while its heat is normalised by the selected bone's
own length, so a finger and an arm read on the same scale.  One active axis
handle sits on the current head (X, Y or Z); the other axes are not drawn as
separate gradient lines.

Nudge mode splits the 3D screen into a temporary rest copy on the left and the
animated custom rig on the right.  The left pane is identified by
``scene.dmf.nudge_rest_area`` and draws the rest copy's armature.  Drawing is a
POST_PIXEL handler; a failure is recorded in ``nudge_overlay_error`` and never
raised into Blender's draw loop.
"""
from __future__ import annotations

import math

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

_HANDLER = None
_FIELD_STEPS = 48
_FIELD_SEGMENTS = 48

TEXT = (0.88, 0.90, 0.94, 1.0)
DIM = (0.55, 0.60, 0.68, 1.0)
REST = (0.42, 0.47, 0.56, 0.80)
POSED = (1.00, 0.64, 0.20, 1.0)
ACTIVE = (1.00, 0.86, 0.30, 1.0)
PANEL = (0.045, 0.055, 0.070, 0.88)
BORDER = (0.24, 0.28, 0.34, 1.0)


def _shader():
    return gpu.shader.from_builtin("UNIFORM_COLOR")


def _line(coords, color, width: float = 1.0) -> None:
    if len(coords) < 2:
        return
    shader = _shader()
    batch = batch_for_shader(shader, "LINES", {"pos": coords})
    gpu.state.line_width_set(width)
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.line_width_set(1.0)


def _fill(coords, color) -> None:
    if len(coords) < 3:
        return
    shader = _shader()
    batch = batch_for_shader(shader, "TRI_FAN", {"pos": coords})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _ring(center, radius: float, color, width: float = 1.4) -> None:
    steps = 12
    points = [
        (
            center[0] + radius * math.cos(2.0 * math.pi * index / steps),
            center[1] + radius * math.sin(2.0 * math.pi * index / steps),
        )
        for index in range(steps + 1)
    ]
    coords = []
    for index in range(steps):
        coords.extend((points[index], points[index + 1]))
    _line(coords, color, width)


def _cross(center, size: float, color, width: float = 1.6) -> None:
    x, y = center
    _line([(x - size, y), (x + size, y), (x, y - size), (x, y + size)], color, width)


def _text(text: str, x: float, y: float, size: float = 11.0, color=TEXT) -> None:
    font = 0
    blf.size(font, size)
    blf.color(font, *color)
    blf.position(font, x, y, 0.0)
    blf.draw(font, text)


def _lerp(first, second, ratio: float):
    return tuple(first[index] + (second[index] - first[index]) * ratio for index in range(4))


def _heat(ratio: float):
    """Slate -> amber -> red, in the same order as the viewport field."""
    ratio = max(0.0, min(1.0, ratio))
    if ratio < 0.5:
        return _lerp((0.30, 0.62, 0.92, 0.95), (1.00, 0.76, 0.22, 1.0), ratio * 2.0)
    return _lerp((1.00, 0.76, 0.22, 1.0), (1.00, 0.26, 0.26, 1.0), (ratio - 0.5) * 2.0)


def _field_color(t: float, hot):
    """A radial field: hot at the head, green mid, blue-transparent outside."""
    core = (hot[0], hot[1], hot[2], 0.34)
    amber = (1.00, 0.78, 0.18, 0.24)
    green = (0.25, 0.82, 0.42, 0.15)
    edge = (0.08, 0.22, 0.50, 0.0)
    if t < 0.34:
        return _lerp(core, amber, t / 0.34)
    if t < 0.68:
        return _lerp(amber, green, (t - 0.34) / 0.34)
    return _lerp(green, edge, (t - 0.68) / 0.32)


def _radial_field(center, radius: float, hot) -> None:
    if radius < 2.0:
        return
    shader = _shader()
    for ring in range(_FIELD_STEPS - 1, -1, -1):
        inner = radius * ring / _FIELD_STEPS
        outer = radius * (ring + 1) / _FIELD_STEPS
        color = _field_color((ring + 0.5) / _FIELD_STEPS, hot)
        coords = []
        for index in range(_FIELD_SEGMENTS + 1):
            angle = 2.0 * math.pi * index / _FIELD_SEGMENTS
            cosine = math.cos(angle)
            sine = math.sin(angle)
            coords.append((center[0] + inner * cosine, center[1] + inner * sine))
            coords.append((center[0] + outer * cosine, center[1] + outer * sine))
        batch = batch_for_shader(shader, "TRI_STRIP", {"pos": coords})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)


def _project(region, region_3d, point: Vector):
    clip = region_3d.perspective_matrix @ Vector((point.x, point.y, point.z, 1.0))
    if clip.w <= 1e-8:
        return None
    x = (clip.x / clip.w * 0.5 + 0.5) * region.width
    y = (clip.y / clip.w * 0.5 + 0.5) * region.height
    if x < -100.0 or y < -100.0 or x > region.width + 100.0 or y > region.height + 100.0:
        return None
    return (x, y)


def _selected_name(settings, armature) -> str:
    if settings.bone_map:
        index = max(0, min(int(settings.bone_map_index), len(settings.bone_map) - 1))
        row = settings.bone_map[index]
        if row.source in armature.pose.bones:
            return row.source
        if row.target in armature.pose.bones:
            return row.target
    active = getattr(bpy.context, "active_pose_bone", None)
    return active.name if active is not None else ""


def _selected_rows(settings, armature):
    seen = set()
    names = []
    for row in settings.bone_map:
        name = row.source if row.source in armature.pose.bones else row.target
        if name and name not in seen and name in armature.pose.bones:
            seen.add(name)
            names.append(name)
    selected = _selected_name(settings, armature)
    if selected and selected not in names:
        names.insert(0, selected)
    return selected, names


def _bone_points(armature, name: str):
    bone = armature.data.bones.get(name)
    pose = armature.pose.bones.get(name)
    if bone is None or pose is None:
        return None
    rest_head = armature.matrix_world @ bone.head_local
    rest_tail = armature.matrix_world @ bone.tail_local
    pose_head = armature.matrix_world @ pose.head
    pose_tail = armature.matrix_world @ pose.tail
    return bone, pose, rest_head, rest_tail, pose_head, pose_tail


def _rest_area_here(settings) -> bool:
    area = getattr(bpy.context, "area", None)
    return bool(area is not None and settings.nudge_rest_area == f"{area.x}:{area.y}")


def _draw_legend(region, settings, hot) -> None:
    x = 14.0
    y = 14.0
    width = 330.0
    height = 68.0
    _fill([(x, y), (x + width, y), (x + width, y + height), (x, y + height)], PANEL)
    _line(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y)],
        BORDER,
        1.0,
    )
    _text("Nudge map  rest → posed", x + 9.0, y + height - 16.0, 11.0, TEXT)
    _radial_field((x + 25.0, y + 31.0), 18.0, hot)
    _text("field", x + 48.0, y + 35.0, 9.0, DIM)
    _text("length-normalized", x + 48.0, y + 23.0, 9.0, DIM)
    _text(
        f"axis {settings.nudge_axis}  |  {'rotate' if settings.nudge_rotate else 'translate'}  |  "
        f"{'relative' if settings.nudge_relative else 'absolute'}",
        x + 150.0,
        y + 29.0,
        9.5,
        DIM,
    )
    _text("hot = rest head / cool = outside", x + 9.0, y + 7.0, 9.0, DIM)


def _draw(context) -> None:
    settings = getattr(bpy.context.scene, "dmf", None)
    if settings is None or not settings.show_nudge_overlay:
        return
    region = bpy.context.region
    region_3d = getattr(bpy.context.space_data, "region_3d", None)
    if region is None or region_3d is None or region.width < 120 or region.height < 120:
        return
    custom = settings.custom_armature
    if custom is None or custom.type != "ARMATURE":
        return
    rest_here = _rest_area_here(settings)
    armature = settings.nudge_rest_armature if rest_here else custom
    if armature is None or armature.name not in bpy.data.objects:
        armature = custom
        rest_here = False
    selected, names = _selected_rows(settings, armature)
    if not names:
        return
    active_axis = {"X": 0, "Y": 1, "Z": 2}.get(settings.nudge_axis, 0)
    selected_points = _bone_points(armature, selected) if selected else None
    field_center = None
    hot = _heat(0.0)
    if selected_points is not None:
        bone, pose, rest_head, rest_tail, pose_head, pose_tail = selected_points
        delta = (pose_head - rest_head).length
        hot = _heat(delta / max(bone.length, 1e-4))
        field_center = _project(region, region_3d, rest_head)
        if field_center is None:
            field_center = _project(region, region_3d, pose_head)

    gpu.state.blend_set("ALPHA")
    if field_center is not None:
        radius = max(70.0, min(region.width, region.height) * 0.52)
        _radial_field(field_center, radius, hot)

    # The whole map stays readable: every mapped bone gets a rest segment and a
    # heat dot at its current head.  The selected bone gets the labelled detail.
    for name in names:
        points = _bone_points(armature, name)
        if points is None:
            continue
        bone, pose, rest_head, rest_tail, pose_head, pose_tail = points
        rest_a = _project(region, region_3d, rest_head)
        rest_b = _project(region, region_3d, rest_tail)
        pose_a = _project(region, region_3d, pose_head)
        pose_b = _project(region, region_3d, pose_tail)
        if rest_a is not None and rest_b is not None:
            _line([rest_a, rest_b], REST if name == selected else (*REST[:3], 0.35), 1.3)
        if name != selected and pose_a is not None:
            _ring(pose_a, 2.2, _heat((pose_head - rest_head).length / max(bone.length, 1e-4)), 1.0)
        if name != selected or pose_a is None or rest_a is None:
            continue
        delta = (pose_head - rest_head).length
        ratio = delta / max(bone.length, 1e-4)
        if pose_a is not None and pose_b is not None:
            _line([pose_a, pose_b], _heat(ratio), 3.0)
        if (pose_head - rest_head).length > 1e-6:
            _line([rest_a, pose_a], (0.92, 0.94, 1.0, 0.34), 1.2)
        _ring(rest_a, 3.2, REST, 1.2)
        _ring(pose_a, 4.4, POSED, 2.0)
        _cross(pose_a, 5.0, POSED, 1.8)
        axis = (pose.x_axis, pose.y_axis, pose.z_axis)[active_axis]
        axis_length = max(bone.length * 1.1, 0.02)
        tip = pose_head + Vector(axis) * axis_length
        tip_2d = _project(region, region_3d, tip)
        if tip_2d is not None:
            _line([pose_a, tip_2d], ACTIVE, 2.4)
            _cross(tip_2d, 3.0, ACTIVE, 1.4)
            _text(settings.nudge_axis, tip_2d[0] + 5.0, tip_2d[1] + 4.0, 10.0, ACTIVE)
        angle = pose.matrix_basis.to_quaternion().angle
        suffix = "  rest" if rest_here else ""
        _text(
            f"{name}{suffix}  Δ{delta:.3f}m  {math.degrees(angle):.1f}°",
            pose_a[0] + 8.0,
            pose_a[1] + 8.0,
            11.5,
            ACTIVE,
        )

    _draw_legend(region, settings, hot)


def draw(_self=None, context=None) -> None:
    try:
        _draw(context or bpy.context)
    except Exception as error:
        settings = getattr(bpy.context.scene, "dmf", None)
        if settings is not None and settings.nudge_overlay_error != str(error):
            settings.nudge_overlay_error = str(error)


def register() -> None:
    global _HANDLER
    if _HANDLER is not None:
        return
    _HANDLER = bpy.types.SpaceView3D.draw_handler_add(
        draw, (None, None), "WINDOW", "POST_PIXEL"
    )


def unregister() -> None:
    global _HANDLER
    if _HANDLER is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_HANDLER, "WINDOW")
        _HANDLER = None
