"""Viewport guides for the hand/bone nudge pass.

The selected custom chain is drawn against its mapped hero chain.  Warm halos
belong to the custom rig; cool halos belong to the hero target.  Each bone's
warm colour is its position/rotation error: blue when aligned, green/amber as it
moves away, red when it is far.  A selected bone keeps a warm outline even when
it is close, so the bone being nudged is always identifiable.

The old viewport-sized radial field is gone.  Each bone gets a small local halo,
so a long arm does not wash out the hand.  Drawing is a POST_PIXEL handler; a
failure is recorded in ``nudge_overlay_error`` and never raised into Blender's
draw loop.  The overlay never changes a mode, a pose, a rest bone or an action.
"""
from __future__ import annotations

import math

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from forge.solver import is_solver_input

_HANDLER = None
_FIELD_STEPS = 24
_FIELD_SEGMENTS = 36

TEXT = (0.88, 0.90, 0.94, 1.0)
DIM = (0.55, 0.60, 0.68, 1.0)
REST = (0.42, 0.47, 0.56, 0.80)
WARM = (1.00, 0.52, 0.14, 1.0)
COOL = (0.20, 0.72, 1.00, 0.95)
COOL_BRIGHT = (0.48, 0.92, 1.00, 1.0)
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
    """Blue when aligned, through green/amber, to red when far."""
    ratio = max(0.0, min(1.0, ratio))
    if ratio < 0.35:
        return _lerp((0.20, 0.62, 1.00, 1.0), (0.30, 0.88, 0.42, 1.0), ratio / 0.35)
    if ratio < 0.70:
        return _lerp((0.30, 0.88, 0.42, 1.0), (1.00, 0.76, 0.18, 1.0), (ratio - 0.35) / 0.35)
    return _lerp((1.00, 0.76, 0.18, 1.0), (1.00, 0.24, 0.22, 1.0), (ratio - 0.70) / 0.30)


def _warm_color(error: float, selected: bool):
    """A selected bone stays warm at rest, then goes red as its error grows."""
    if not selected:
        return _heat(error)
    return _lerp(WARM, _heat(error), min(1.0, error * 2.2))


def _field_color(t: float, hot, target: bool = False):
    if target:
        core = (0.20, 0.72, 1.00, 0.34)
        mid = (0.16, 0.88, 1.00, 0.16)
        edge = (0.04, 0.16, 0.42, 0.0)
    else:
        core = (hot[0], hot[1], hot[2], 0.34)
        mid = (1.00, 0.74, 0.16, 0.16)
        edge = (0.05, 0.16, 0.40, 0.0)
    if t < 0.38:
        return _lerp(core, mid, t / 0.38)
    return _lerp(mid, edge, (t - 0.38) / 0.62)


def _radial_field(center, radius: float, hot, *, target: bool = False, strength: float = 1.0) -> None:
    if radius < 2.0 or strength <= 0.01:
        return
    shader = _shader()
    for ring in range(_FIELD_STEPS - 1, -1, -1):
        inner = radius * ring / _FIELD_STEPS
        outer = radius * (ring + 1) / _FIELD_STEPS
        color = _field_color((ring + 0.5) / _FIELD_STEPS, hot, target)
        color = (*color[:3], color[3] * strength)
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


def _resolve(settings, armature, name: str) -> str:
    """A panel pick on the custom rig, following the bone map when needed."""
    if not name:
        return ""
    if armature.pose.bones.get(name) is not None:
        return name
    for row in settings.bone_map:
        if row.target == name and row.source and armature.pose.bones.get(row.source) is not None:
            return row.source
    return ""


def _selected_name(settings, armature) -> str:
    """The chain chosen in the panel; the pose selection never takes it over.

    The bone map's Pick and the bone list set ``hierarchy_index``; the mapped
    row is the fallback when no hero hierarchy has been read.  The overlay is a
    drawing, so posing or rest-editing a different bone leaves the highlighted
    chain where the owner put it.
    """
    if settings.hierarchy and 0 <= settings.hierarchy_index < len(settings.hierarchy):
        chosen = _resolve(settings, armature, settings.hierarchy[settings.hierarchy_index].name)
        if chosen:
            return chosen
    if settings.bone_map:
        index = max(0, min(int(settings.bone_map_index), len(settings.bone_map) - 1))
        row = settings.bone_map[index]
        for name in (row.source, row.target):
            chosen = _resolve(settings, armature, name)
            if chosen:
                return chosen
    return ""


def _mapping(settings) -> dict[str, str]:
    result = {}
    for row in settings.bone_map:
        if row.source and row.target:
            result[row.source] = row.target
            result.setdefault(row.target, row.target)
    return result


def _chain(armature, selected: str) -> list[str]:
    """The selected bone and its ancestors, root first."""
    names = []
    pose = armature.pose.bones.get(selected) if selected else None
    while pose is not None:
        names.append(pose.name)
        pose = pose.parent
    return list(reversed(names))


def _retarget_axes(hero):
    """The root-motion rotation the retarget divides out, or identity."""
    if hero is None:
        return Matrix.Identity(4)
    root = hero.pose.bones.get("root_motion")
    if root is None:
        return Matrix.Identity(4)
    try:
        matrix = root.matrix.to_quaternion().to_matrix().to_4x4()
        if abs(matrix.determinant()) < 1e-12:
            return Matrix.Identity(4)
        return matrix.inverted()
    except (AttributeError, ValueError, RuntimeError):
        return Matrix.Identity(4)


def _metrics(settings, custom, hero, name: str, mapping: dict[str, str], axes):
    pose = custom.pose.bones.get(name)
    if pose is None:
        return None
    target_name = mapping.get(name, name)
    target = hero.pose.bones.get(target_name) if hero is not None and hero.type == "ARMATURE" else None
    bone = pose.bone
    custom_head = custom.matrix_world @ pose.head
    custom_tail = custom.matrix_world @ pose.tail
    rest_head = custom.matrix_world @ bone.head_local
    rest_tail = custom.matrix_world @ bone.tail_local
    if target is None:
        return {
            "name": name,
            "target": target_name,
            "pose": pose,
            "target_pose": None,
            "bone": bone,
            "custom_head": custom_head,
            "custom_tail": custom_tail,
            "rest_head": rest_head,
            "rest_tail": rest_tail,
            "target_head": None,
            "target_tail": None,
            "custom_world": custom.matrix_world @ pose.matrix,
            "target_world": None,
            "pos_error": 0.0,
            "rot_error": 0.0,
            "error": 0.0,
        }
    # Compare against the same target the retarget solver applies.  The root and
    # solver proxies keep their authored transforms; other bones divide out root
    # rotation.  Otherwise root motion makes a correct chain look far away.
    if target.name == "root_motion" or is_solver_input(target.name):
        target_matrix = target.matrix.copy()
    else:
        target_matrix = axes @ target.matrix
    target_head = custom.matrix_world @ target_matrix.translation
    target_tail = custom.matrix_world @ (target_matrix @ Vector((0.0, target.length, 0.0)))
    custom_world = custom.matrix_world @ pose.matrix
    target_world = custom.matrix_world @ target_matrix
    rotation = custom_world.to_quaternion().rotation_difference(target_world.to_quaternion()).angle
    pos_error = (custom_head - target_head).length
    # Positions are drawn in the custom object's world frame.  The hierarchy copy
    # inherits that object's scale, so an unscaled rest length compared metres
    # with centimetres and collapsed a small error to 0% accuracy.
    frame = custom.matrix_world.to_3x3()
    custom_length = (frame @ (bone.tail_local - bone.head_local)).length
    target_length = (frame @ (target.bone.tail_local - target.bone.head_local)).length
    scale = max(custom_length, target_length, 1e-3)
    error = min(1.0, max(abs(rotation) / math.radians(75.0), pos_error / (2.0 * scale)))
    return {
        "name": name,
        "target": target_name,
        "pose": pose,
        "target_pose": target,
        "bone": bone,
        "custom_head": custom_head,
        "custom_tail": custom_tail,
        "rest_head": rest_head,
        "rest_tail": rest_tail,
        "target_head": target_head,
        "target_tail": target_tail,
        "custom_world": custom_world,
        "target_world": target_world,
        "pos_error": pos_error,
        "rot_error": rotation,
        "error": error,
    }


def _accuracy(error: float) -> float:
    return max(0.0, min(100.0, (1.0 - error) * 100.0))


def _point_text(point) -> str:
    return f"x {point.x:+.3f}  y {point.y:+.3f}  z {point.z:+.3f} m"


def _rotation_text(matrix) -> str:
    euler = matrix.to_euler("XYZ")
    return (
        f"rx {math.degrees(euler.x):+.1f}°  "
        f"ry {math.degrees(euler.y):+.1f}°  "
        f"rz {math.degrees(euler.z):+.1f}°"
    )


def _draw_info(selected_item) -> None:
    """The selected bone's numbers, kept off the bone itself."""
    x = 14.0
    y = 92.0
    width = 350.0
    height = 86.0
    _fill([(x, y), (x + width, y), (x + width, y + height), (x, y + height)], PANEL)
    _line(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y)],
        BORDER,
        1.0,
    )
    target = selected_item["target_pose"]
    accuracy = _accuracy(selected_item["error"])
    title = (
        f"{selected_item['name']} → {selected_item['target']}   accuracy {accuracy:.0f}%"
        if target is not None
        else f"{selected_item['name']} · no mapped target"
    )
    _text(title, x + 9.0, y + height - 16.0, 10.0, TEXT)
    _text(
        f"custom  {_point_text(selected_item['custom_head'])}",
        x + 9.0,
        y + height - 34.0,
        9.0,
        WARM,
    )
    _text(
        f"        {_rotation_text(selected_item['custom_world'])}",
        x + 9.0,
        y + height - 48.0,
        9.0,
        WARM,
    )
    if target is None:
        _text("hero    not mapped", x + 9.0, y + height - 64.0, 9.0, DIM)
        return
    _text(
        f"hero    {_point_text(selected_item['target_head'])}",
        x + 9.0,
        y + height - 64.0,
        9.0,
        COOL_BRIGHT,
    )
    _text(
        f"        {_rotation_text(selected_item['target_world'])}",
        x + 9.0,
        y + height - 78.0,
        9.0,
        COOL_BRIGHT,
    )


def _draw_legend(selected_error: float) -> None:
    x = 14.0
    y = 14.0
    width = 350.0
    height = 70.0
    _fill([(x, y), (x + width, y), (x + width, y + height), (x, y + height)], PANEL)
    _line(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y)],
        BORDER,
        1.0,
    )
    _text("Chain overlay  warm custom / cool hero", x + 9.0, y + height - 17.0, 11.0, TEXT)
    _radial_field((x + 22.0, y + 36.0), 15.0, _warm_color(selected_error, True), strength=0.9)
    _text("custom", x + 42.0, y + 41.0, 9.0, WARM)
    _radial_field((x + 124.0, y + 36.0), 15.0, COOL, target=True, strength=0.9)
    _text("hero target", x + 144.0, y + 41.0, 9.0, COOL_BRIGHT)
    _text("red = far  ·  blue = aligned", x + 9.0, y + 22.0, 9.0, DIM)
    _text("chain: picked bone and its mapped ancestors", x + 9.0, y + 7.0, 9.0, DIM)


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
    armature = custom
    hero = settings.target_armature
    if hero is not None and (hero == armature or hero.type != "ARMATURE"):
        hero = None
    selected = _selected_name(settings, armature)
    names = _chain(armature, selected)
    if not names:
        return
    mapping = _mapping(settings)
    axes = _retarget_axes(hero)
    chain = [item for item in (_metrics(settings, armature, hero, name, mapping, axes) for name in names) if item]
    if not chain:
        return
    selected_item = next((item for item in chain if item["name"] == selected), None)

    gpu.state.blend_set("ALPHA")
    # Cool target halos first, then warm custom halos.  Each halo is local to its
    # bone; the old viewport-sized field hid the hand under the arm's colour.
    for item in chain:
        target = item["target_head"]
        if target is None:
            continue
        center = _project(region, region_3d, target)
        if center is None:
            continue
        radius = 22.0 if item is selected_item else 14.0
        _radial_field(center, radius, COOL, target=True, strength=0.75)

    for item in chain:
        center = _project(region, region_3d, item["custom_head"])
        if center is None:
            continue
        error = item["error"]
        radius = (20.0 + 28.0 * error) if item is selected_item else (12.0 + 18.0 * error)
        _radial_field(
            center,
            radius,
            _warm_color(error, item is selected_item),
            strength=0.35 + 0.65 * error,
        )

    # The cool chain is the destination.  Draw it behind the warm chain so the
    # bone being nudged always stays on top.
    for item in chain:
        if item["target_head"] is None:
            continue
        first = _project(region, region_3d, item["target_head"])
        second = _project(region, region_3d, item["target_tail"])
        if first is not None and second is not None:
            _line(
                [first, second],
                COOL_BRIGHT if item is selected_item else (*COOL[:3], 0.68),
                2.4 if item is selected_item else 1.3,
            )
            _ring(first, 2.6 if item is not selected_item else 3.8, COOL, 1.0)

    for item in chain:
        rest_first = _project(region, region_3d, item["rest_head"])
        rest_second = _project(region, region_3d, item["rest_tail"])
        first = _project(region, region_3d, item["custom_head"])
        second = _project(region, region_3d, item["custom_tail"])
        color = _warm_color(item["error"], item is selected_item)
        if rest_first is not None and rest_second is not None:
            _line([rest_first, rest_second], (*REST[:3], 0.35), 1.0)
        if first is not None and second is not None:
            _line([first, second], color, 3.1 if item is selected_item else 1.8)
        if first is not None:
            _ring(first, 3.7 if item is selected_item else 2.0, color, 1.4)

    # Keep the destination visible even when the custom and target heads
    # coincide (hands preserve their head, so translation does not move them
    # apart).  These cool markers are deliberately drawn after the warm chain.
    for item in chain:
        target = item["target_head"]
        if target is None:
            continue
        center = _project(region, region_3d, target)
        if center is None:
            continue
        _ring(center, 6.0 if item is selected_item else 3.0, COOL_BRIGHT, 1.6)

    if selected_item is not None and selected_item["custom_head"] is not None:
        custom_head = selected_item["custom_head"]
        custom_point = _project(region, region_3d, custom_head)
        target_point = (
            _project(region, region_3d, selected_item["target_head"])
            if selected_item["target_head"] is not None
            else None
        )
        if custom_point is not None:
            _ring(custom_point, 8.5, _heat(selected_item["error"]), 2.0)
            _ring(custom_point, 5.0, WARM, 2.0)
            _cross(custom_point, 5.0, WARM, 1.8)
            if target_point is not None:
                # The connector is a comparison, not an axis trail: it runs from
                # the current custom head to the cool target head and fades warm
                # to cool over the distance.
                steps = 9
                for index in range(steps):
                    start = custom_head.lerp(selected_item["target_head"], index / steps)
                    end = custom_head.lerp(selected_item["target_head"], (index + 1) / steps)
                    first = _project(region, region_3d, start)
                    second = _project(region, region_3d, end)
                    if first is not None and second is not None:
                        _line(
                            [first, second],
                            _lerp(_heat(selected_item["error"]), COOL, index / max(1, steps - 1)),
                            1.4,
                        )
                if (target_point[0] - custom_point[0]) ** 2 + (target_point[1] - custom_point[1]) ** 2 < 25.0:
                    _cross(target_point, 4.0, COOL_BRIGHT, 1.4)

    if selected_item is not None:
        _draw_info(selected_item)
    _draw_legend(selected_item["error"] if selected_item is not None else 0.0)


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
