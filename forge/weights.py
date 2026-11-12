"""Weight arithmetic that does not depend on Blender.

The solver in the addon prepares geometry, then calls these functions per
vertex. The same functions are unit-tested without a viewport.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

WeightMap = dict[str, float]


class WeightError(ValueError):
    pass


@dataclass(frozen=True)
class BoneSegment:
    name: str
    head: tuple[float, float, float]
    tail: tuple[float, float, float]


def _finite(value: float) -> bool:
    return math.isfinite(value)


def normalize_weights(
    weights: Mapping[str, float],
    max_influences: int = 4,
    epsilon: float = 1e-8,
) -> WeightMap:
    if max_influences < 1:
        raise WeightError(f"weight-influence-limit: {max_influences}")
    clean = [
        (name, float(weight))
        for name, weight in weights.items()
        if _finite(float(weight)) and float(weight) > epsilon
    ]
    clean.sort(key=lambda item: (-item[1], item[0]))
    clean = clean[:max_influences]
    total = sum(weight for _, weight in clean)
    if total <= epsilon:
        return {}
    return {name: weight / total for name, weight in clean}


def merge_weights(*maps: Mapping[str, float]) -> WeightMap:
    merged: WeightMap = {}
    for values in maps:
        for name, weight in values.items():
            if _finite(float(weight)) and weight > 0:
                merged[name] = merged.get(name, 0.0) + float(weight)
    return merged


def segment_distance(
    point: Sequence[float],
    head: Sequence[float],
    tail: Sequence[float],
) -> float:
    px, py, pz = (float(part) for part in point)
    ax, ay, az = (float(part) for part in head)
    bx, by, bz = (float(part) for part in tail)
    abx, aby, abz = bx - ax, by - ay, bz - az
    apx, apy, apz = px - ax, py - ay, pz - az
    length_squared = abx * abx + aby * aby + abz * abz
    if length_squared <= 1e-12:
        return math.dist(point, head)
    t = (apx * abx + apy * aby + apz * abz) / length_squared
    t = max(0.0, min(1.0, t))
    closest = (ax + abx * t, ay + aby * t, az + abz * t)
    return math.dist(point, closest)


def envelope_weights(
    point: Sequence[float],
    segments: Iterable[BoneSegment],
    *,
    max_distance: float,
    falloff: float = 2.0,
    max_influences: int = 4,
) -> WeightMap:
    scored: WeightMap = {}
    nearest = None
    for segment in segments:
        distance = segment_distance(point, segment.head, segment.tail)
        nearest = distance if nearest is None else min(nearest, distance)
        if distance > max_distance:
            continue
        scored[segment.name] = scored.get(segment.name, 0.0) + (1.0 / (distance + 1e-6)) ** falloff
    if not scored and nearest is not None:
        # A point outside the declared envelope still needs its nearest declared
        # bone, otherwise a wing or tail vertex becomes unweighted.
        for segment in segments:
            distance = segment_distance(point, segment.head, segment.tail)
            if abs(distance - nearest) <= 1e-6:
                scored[segment.name] = 1.0
    return normalize_weights(scored, max_influences=max_influences)


def fold_source(
    name: str,
    mapping: Mapping[str, str],
    parents: Mapping[str, str],
    *,
    extra_policy: str,
    fallback: str = "",
) -> str | None:
    if name in mapping:
        return mapping[name] or None
    if extra_policy == "KEEP":
        return name
    if extra_policy == "DROP":
        return None
    if extra_policy != "FOLD":
        raise WeightError(f"unknown-extra-policy: {extra_policy}")
    current = parents.get(name, "")
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        if current in mapping:
            return mapping[current] or None
        current = parents.get(current, "")
    return fallback or None
