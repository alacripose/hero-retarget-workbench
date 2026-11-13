"""Project a bone tree into a 2D diagram.

Pure geometry, no Blender imports, so the layout can be tested without a GPU.
The addon draws these points in the 3D viewport; the tests check the projection,
the aspect fit and the hit test.
"""
from __future__ import annotations

from dataclasses import dataclass

# Plane name -> the two axes of the bone's local position that face the viewer.
PLANES: dict[str, tuple[int, int]] = {
    "FRONT": (0, 2),
    "SIDE": (1, 2),
    "TOP": (0, 1),
}


@dataclass(frozen=True)
class Bone:
    """One bone in the diagram: its name, parent and rest head/tail."""

    name: str
    parent: str | None
    head: tuple[float, float, float]
    tail: tuple[float, float, float]


@dataclass(frozen=True)
class Placed:
    """Where a bone's head and tail landed, in the rectangle's own pixels."""

    name: str
    parent: str | None
    depth: int
    head: tuple[float, float]
    tail: tuple[float, float]


def project(point, plane: str = "FRONT") -> tuple[float, float]:
    """The two coordinates that plane shows. Depth on the hidden axis is dropped."""
    axes = PLANES[plane] if isinstance(plane, str) else tuple(plane)
    return (float(point[axes[0]]), float(point[axes[1]]))


def depths(bones: list[Bone]) -> dict[str, int]:
    """Distance from a root, with cycles and orphans pinned to zero instead of hanging."""
    parents = {bone.name: bone.parent for bone in bones}
    cache: dict[str, int] = {}

    def walk(name: str, seen: frozenset[str]) -> int:
        if name in cache:
            return cache[name]
        parent = parents.get(name)
        if parent is None or parent not in parents or parent in seen:
            cache[name] = 0
            return 0
        value = walk(parent, seen | {name}) + 1
        cache[name] = value
        return value

    return {bone.name: walk(bone.name, frozenset()) for bone in bones}


def layout(
    bones: list[Bone],
    plane: str = "FRONT",
    rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    padding: float = 0.07,
) -> dict[str, Placed]:
    """Fit the bone tree into ``rect`` (x, y, width, height), keeping its aspect.

    The longest axis of the silhouette is what gets scaled into the box, so a tall
    rig is not stretched to the box's width and a bone's angle in the diagram is
    the angle it has in the rig.
    """
    if not bones:
        return {}
    x0, y0, width, height = rect
    span_w = width * (1.0 - 2.0 * padding)
    span_h = height * (1.0 - 2.0 * padding)
    projected = {
        bone.name: (project(bone.head, plane), project(bone.tail, plane)) for bone in bones
    }
    us = [point[0] for pair in projected.values() for point in pair]
    vs = [point[1] for pair in projected.values() for point in pair]
    min_u, max_u = min(us), max(us)
    min_v, max_v = min(vs), max(vs)
    span_u = max(max_u - min_u, 1e-6)
    span_v = max(max_v - min_v, 1e-6)
    scale = min(span_w / span_u, span_h / span_v)
    # Centre whatever the aspect fit leaves over, so the silhouette sits in the middle.
    offset_u = x0 + width / 2.0 - (min_u + max_u) / 2.0 * scale
    offset_v = y0 + height / 2.0 - (min_v + max_v) / 2.0 * scale

    def place(point: tuple[float, float]) -> tuple[float, float]:
        return (offset_u + point[0] * scale, offset_v + point[1] * scale)

    level = depths(bones)
    placed: dict[str, Placed] = {}
    for bone in bones:
        head, tail = projected[bone.name]
        placed[bone.name] = Placed(
            name=bone.name,
            parent=bone.parent if bone.parent in projected else None,
            depth=level[bone.name],
            head=place(head),
            tail=place(tail),
        )
    return placed


def nearest(placed: dict[str, Placed], x: float, y: float, limit: float = 16.0) -> str | None:
    """The bone whose head is closest to ``(x, y)``, if one is within ``limit`` pixels.

    Distance to the head, not the segment: the head is the joint the user means
    when two bones overlap, and a long bone would otherwise swallow its children.
    """
    best: tuple[float, str] | None = None
    for name, item in placed.items():
        distance = ((item.head[0] - x) ** 2 + (item.head[1] - y) ** 2) ** 0.5
        if distance > limit:
            continue
        if best is None or distance < best[0]:
            best = (distance, name)
    return best[1] if best is not None else None


def chain(placed: dict[str, Placed], name: str) -> list[str]:
    """The bone and its ancestors, nearest first."""
    seen: list[str] = []
    item = placed.get(name)
    while item is not None and item.name not in seen:
        seen.append(item.name)
        item = placed.get(item.parent) if item.parent else None
    return seen


def children(placed: dict[str, Placed], name: str) -> list[str]:
    """Direct children of a bone, in layout order."""
    return [item.name for item in placed.values() if item.parent == name]
