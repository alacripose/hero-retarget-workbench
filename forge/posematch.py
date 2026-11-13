"""What the ref-pose preview can drive, and what stance the source rig is in.

The preview itself needs Blender's matrices; the decisions worth testing are
here: which mapped pairs can be posed, in what parent order, how much of the rig
the map covers, and whether the source rig stands in a T-pose or an A-pose. That
last answer is what tells a user why the mesh's arms do not line up with the
hero's until the preview is on.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Vector = tuple[float, float, float]


@dataclass(frozen=True)
class Pair:
    """A mapped row that both rigs can actually pose."""

    source: str
    target: str
    depth: int


def depths(parents: dict[str, str | None]) -> dict[str, int]:
    """Distance from a root; cycles and orphans sit at zero instead of hanging."""
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

    levels = {name: walk(name, frozenset()) for name in parents}
    # A cycle has no root, so no member of it is "deeper" than another: pin the
    # whole loop to zero instead of letting whichever node was visited last
    # decide the depths.
    for name in parents:
        path: list[str] = []
        current = name
        while current in levels and current not in path:
            path.append(current)
            current = parents.get(current)  # type: ignore[assignment]
        if current in path:
            for member in path[path.index(current) :]:
                levels[member] = 0
    return levels


def pairs(
    mapping: dict[str, str],
    parents: dict[str, str | None],
    source_bones: list[str],
    target_bones: list[str],
) -> list[Pair]:
    """Mapped pairs that exist in both rigs, parents before children.

    Parent order matters: a pose is written bone by bone, and a child read
    before its parent inherits the old parent rotation.
    """
    available = set(source_bones)
    heroes = set(target_bones or [])
    level = depths(parents)
    rows: list[Pair] = []
    for source, target in (mapping or {}).items():
        if source not in available or target not in heroes:
            continue
        rows.append(Pair(source=source, target=target, depth=level.get(source, 0)))
    return sorted(rows, key=lambda pair: (pair.depth, pair.source))


def unpaired(
    mapping: dict[str, str], source_bones: list[str], target_bones: list[str]
) -> list[str]:
    """Sources whose target is missing from the hero skeleton.

    These are the rows a preview silently cannot show, so the panel names them
    instead of pretending the whole map moved.
    """
    heroes = set(target_bones or [])
    available = set(source_bones)
    return sorted(
        source
        for source, target in (mapping or {}).items()
        if source in available and target not in heroes
    )


def coverage(mapping: dict[str, str], source_bones: list[str]) -> dict[str, float]:
    """How much of the source rig the map covers, as counts and a ratio."""
    rows = [name for name in source_bones or [] if name]
    mapped = sum(1 for name in rows if (mapping or {}).get(name))
    total = len(rows)
    return {
        "rows": float(total),
        "mapped": float(mapped),
        "ratio": (mapped / total) if total else 0.0,
    }


def angle_below_horizontal(direction: Vector) -> float:
    """Degrees a bone points below the horizontal plane (0 = level, 90 = down)."""
    x, y, z = (float(value) for value in direction)
    flat = math.hypot(x, y)
    return math.degrees(math.atan2(-z, flat))


def stance(directions: list[Vector]) -> tuple[str, float]:
    """``("T", angle)``, ``("A", angle)``, ``("down", angle)`` or ``("unknown", 0)``.

    An arm held level is a T-pose; a rig authored with the arms already lowered
    is an A-pose, and its rest orientation differs from the hero's by roughly
    that angle, which is why a raw bind leaves the elbows in the wrong place.
    """
    rows = [angle_below_horizontal(direction) for direction in directions or []]
    rows = [value for value in rows if math.isfinite(value)]
    if not rows:
        return ("unknown", 0.0)
    mean = sum(rows) / len(rows)
    if mean < 15.0:
        return ("T", mean)
    if mean < 55.0:
        return ("A", mean)
    return ("down", mean)
