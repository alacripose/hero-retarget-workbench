"""The bone map: the hero rig's bone tree drawn in the 3D viewport.

This is the visual half of the hierarchy editor. It draws every bone at its rest
position relative to the others (not a list of names), colours it by depth, marks
the selected bone and its chain, and hit-tests a click so a bone can be chosen
from the picture. ``dmf.pick_bone_map`` is the click handler; the drawing here is
registered once and only paints when the toggle is on.

Drawing is a POST_PIXEL handler in the viewport. It must never raise: an
exception inside a draw handler repeats every frame, so each pass is guarded and
the failure is reported in the panel through ``settings.bone_map_error``.
"""
from __future__ import annotations

import math

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from forge import rigmap

_HANDLER = None
_CACHE: dict[str, object] = {"key": None, "placed": {}}

CARD_MARGIN = 14.0
CARD_WIDTH = 0.38
CARD_HEIGHT = 0.64
CARD_MAX_WIDTH = 560.0
TEXT = (0.86, 0.88, 0.91, 1.0)
TEXT_DIM = (0.60, 0.64, 0.70, 1.0)
BONE = (0.42, 0.48, 0.58, 1.0)
LINK = (0.26, 0.29, 0.34, 1.0)
SELECTED = (1.00, 0.78, 0.24, 1.0)
ANCESTOR = (1.00, 0.62, 0.30, 1.0)
CHILD = (0.36, 0.80, 0.78, 1.0)
HOVER = (0.94, 0.94, 0.98, 1.0)


def card_rect(region) -> tuple[float, float, float, float]:
    """The floating map card, anchored to the viewport's top right."""
    width = min(region.width * CARD_WIDTH, CARD_MAX_WIDTH)
    height = max(180.0, min(region.height * CARD_HEIGHT, 640.0))
    x = region.width - width - CARD_MARGIN
    y = region.height - height - CARD_MARGIN
    return (x, y, width, height)


def bones_from(armature) -> list[rigmap.Bone]:
    """Rest-pose segments for every bone, in the armature's own space."""
    return [
        rigmap.Bone(
            name=bone.name,
            parent=bone.parent.name if bone.parent else None,
            head=tuple(bone.head_local),
            tail=tuple(bone.tail_local),
        )
        for bone in armature.data.bones
    ]


def placed_for(context, settings, region=None) -> dict[str, rigmap.Placed]:
    """Cached layout for the current rig, plane and viewport rect."""
    armature = settings.target_armature
    region = region if region is not None else context.region
    if armature is None or region is None:
        return {}
    rect = card_rect(region)
    key = (
        armature.name,
        armature.data.name,
        len(armature.data.bones),
        settings.bone_map_plane,
        settings.axis_tick,
        round(rect[0], 1),
        round(rect[1], 1),
        round(rect[2], 1),
        round(rect[3], 1),
    )
    if _CACHE["key"] == key:
        return _CACHE["placed"]  # type: ignore[return-value]
    placed = rigmap.layout(bones_from(armature), settings.bone_map_plane, rect)
    _CACHE["key"] = key
    _CACHE["placed"] = placed
    return placed


def invalidate() -> None:
    """Forget the cached layout; the next draw re-reads the rig."""
    _CACHE["key"] = None
    _CACHE["placed"] = {}


def hit_test(
    context, window_x: float, window_y: float, limit: float = 16.0, region=None
) -> str | None:
    """Bone under a window-space pointer position, in this viewport's map."""
    settings = getattr(context.scene, "dmf", None)
    region = region if region is not None else context.region
    if settings is None or region is None:
        return None
    placed = placed_for(context, settings, region)
    return rigmap.nearest(placed, window_x - region.x, window_y - region.y, limit)


# --- drawing primitives ---------------------------------------------------


def _shader():
    return gpu.shader.from_builtin("UNIFORM_COLOR")


def _lines(coords: list[tuple[float, float]], color, width: float = 1.0) -> None:
    if len(coords) < 2:
        return
    shader = _shader()
    batch = batch_for_shader(shader, "LINES", {"pos": coords})
    gpu.state.line_width_set(width)
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _fill(coords: list[tuple[float, float]], color) -> None:
    if len(coords) < 3:
        return
    shader = _shader()
    batch = batch_for_shader(shader, "TRI_FAN", {"pos": coords})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _ring(center: tuple[float, float], radius: float, color, width: float = 1.4) -> None:
    steps = 12
    points = [
        (
            center[0] + radius * math.cos(2.0 * math.pi * index / steps),
            center[1] + radius * math.sin(2.0 * math.pi * index / steps),
        )
        for index in range(steps + 1)
    ]
    coords: list[tuple[float, float]] = []
    for index in range(steps):
        coords.append(points[index])
        coords.append(points[index + 1])
    _lines(coords, color, width)


def _label(text: str, x: float, y: float, size: float = 11.0, color=TEXT) -> None:
    font = 0
    blf.size(font, size)
    blf.color(font, *color)
    blf.position(font, x, y, 0.0)
    blf.draw(font, text)


def _depth_color(depth: int) -> tuple[float, float, float, float]:
    """Warm at the root, cool at the tips, so the chain reads without labels."""
    ratio = min(depth / 6.0, 1.0)
    return (
        0.72 - 0.30 * ratio,
        0.66 - 0.02 * ratio,
        0.52 + 0.24 * ratio,
        1.0,
    )


def _draw(context) -> None:
    settings = getattr(context.scene, "dmf", None)
    if settings is None or not settings.show_bone_map:
        return
    region = context.region
    if region is None or region.width < 220 or region.height < 220:
        return
    armature = settings.target_armature
    if armature is None or armature.type != "ARMATURE":
        return
    placed = placed_for(context, settings)
    if not placed:
        return
    selected = ""
    if settings.hierarchy and 0 <= settings.hierarchy_index < len(settings.hierarchy):
        selected = settings.hierarchy[settings.hierarchy_index].name
    if selected not in placed:
        selected = ""
    ancestor_names = set(rigmap.chain(placed, selected)[1:]) if selected else set()
    child_names = set(rigmap.children(placed, selected)) if selected else set()
    hovered = settings.bone_map_hover if settings.bone_map_hover in placed else ""

    x, y, width, height = card_rect(region)
    gpu.state.blend_set("ALPHA")
    _fill(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        (0.045, 0.055, 0.070, 0.88),
    )
    # A LINES batch is a flat run of endpoints, not a list of pairs.
    corners = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
    border: list[tuple[float, float]] = []
    for index in range(4):
        border.append(corners[index])
        border.append(corners[(index + 1) % 4])
    _lines(border, (0.20, 0.23, 0.28, 1.0), 1.0)
    _label(
        f"Bone map · {settings.bone_map_plane.lower()} · {len(placed)} bones",
        x + 10.0,
        y + height - 18.0,
        11.5,
        TEXT,
    )

    # Parent links first, so bone segments stay legible over them.
    links: list[tuple[float, float]] = []
    for item in placed.values():
        if not item.parent:
            continue
        parent = placed.get(item.parent)
        if parent is None:
            continue
        links.append(parent.head)
        links.append(item.head)
    _lines(links, LINK, 1.0)

    for item in sorted(placed.values(), key=lambda entry: entry.depth):
        color = _depth_color(item.depth)
        width_px = 1.5
        if item.name == selected:
            color, width_px = SELECTED, 3.0
        elif item.name in ancestor_names:
            color, width_px = ANCESTOR, 2.2
        elif item.name in child_names:
            color, width_px = CHILD, 2.0
        elif item.name == hovered:
            color, width_px = HOVER, 2.4
        _lines([item.head, item.tail], color, width_px)
        _ring(item.head, 3.4 if item.name == selected else 1.7, color, 2.0 if item.name == selected else 1.2)

    label_floor = y + 26.0
    labels: list[tuple[str, tuple[float, float], tuple[float, float, float, float]]] = []
    if settings.bone_map_labels:
        for item in placed.values():
            labels.append((item.name, item.head, TEXT_DIM))
    for name in [selected] + sorted(ancestor_names) + sorted(child_names) + ([hovered] if hovered else []):
        if not name or name not in placed:
            continue
        item = placed[name]
        color = SELECTED if name == selected else HOVER if name == hovered else TEXT
        labels.append((name, item.head, color))
    # Labels dodge each other downward: a rig's joints cluster at the shoulders
    # and a straight 6px offset prints them on top of each other.
    seen: set[str] = set()
    taken: list[tuple[float, float, float]] = []
    for name, point, color in sorted(labels, key=lambda item: -item[1][1]):
        if name in seen:
            continue
        seen.add(name)
        text = name if len(name) <= 26 else name[:25] + "…"
        size = 10.0
        text_width = size * 0.62 * len(text)
        label_x = min(point[0] + 6.0, x + width - 8.0 - text_width)
        label_y = point[1] + 4.0
        for _attempt in range(8):
            clash = any(
                abs(label_x - other_x) < (text_width + other_width) / 2.0
                and abs(label_y - other_y) < size + 1.5
                for other_x, other_y, other_width in taken
            )
            if not clash:
                break
            label_y -= size + 1.5
        label_y = max(label_y, label_floor)
        taken.append((label_x, label_y, text_width))
        _label(text, label_x, label_y, size, color)

    if selected:
        item = placed[selected]
        _label(
            f"{selected}  →  {item.parent or 'root'}",
            x + 10.0,
            y + 10.0,
            10.5,
            SELECTED,
        )
    else:
        _label("Click a joint to select its bone", x + 10.0, y + 10.0, 10.5, TEXT_DIM)


def draw(_self=None, context=None) -> None:
    """Draw handler body: every failure is caught and surfaced once."""
    try:
        _draw(context or bpy.context)
    except Exception as error:  # A raising draw handler spams the console every frame.
        settings = getattr(bpy.context.scene, "dmf", None)
        if settings is not None and settings.bone_map_error != str(error):
            settings.bone_map_error = str(error)


def register() -> None:
    global _HANDLER
    if _HANDLER is not None:
        return
    _HANDLER = bpy.types.SpaceView3D.draw_handler_add(draw, (None, None), "WINDOW", "POST_PIXEL")
    bpy.app.handlers.load_post.append(_on_load)


def unregister() -> None:
    global _HANDLER
    if _HANDLER is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_HANDLER, "WINDOW")
        _HANDLER = None
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    invalidate()


def _on_load(_dummy) -> None:
    invalidate()
