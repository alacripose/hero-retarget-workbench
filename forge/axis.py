"""Exact axis conversions for model fitting.

Weights are joint indices and normalized values. They are never multiplied by
an axis matrix. This module transforms geometry only, using integer matrices and
Fractions until the final float handoff to Blender.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Sequence


class AxisError(ValueError):
    pass


Matrix3 = tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]

# Coordinates are named by their semantic directions. The matrices map a source
# vector into the target frame. All listed presets preserve handedness.
PRESETS: dict[str, Matrix3] = {
    "identity": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    # Blender: +X right, +Y forward, +Z up.
    # Source 2: +X forward, +Y left, +Z up.
    "blender-to-source2": ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    "source2-to-blender": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    # glTF: +X right, +Y up, +Z toward the viewer. Source 2's +X forward
    # appears as glTF +Z, and Source 2's +Y left appears as glTF +X.
    "gltf-to-source2": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "source2-to-gltf": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    # A deliberate mirror, kept separate from the rigid presets.
    "mirror-x": ((-1, 0, 0), (0, 1, 0), (0, 0, 1)),
}


def determinant(matrix: Sequence[Sequence[int]]) -> int:
    a, b, c = matrix
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def _is_permutation(matrix: Sequence[Sequence[int]]) -> bool:
    for row in matrix:
        if sorted(abs(value) for value in row) != [0, 0, 1]:
            return False
    return True


@dataclass(frozen=True)
class AxisTransform:
    name: str
    matrix: Matrix3
    scale: Fraction = Fraction(1)
    allow_mirror: bool = False

    def __post_init__(self) -> None:
        det = determinant(self.matrix)
        if not _is_permutation(self.matrix):
            raise AxisError(f"axis-matrix-not-permutation: {self.name}")
        if det == 0:
            raise AxisError(f"axis-matrix-singular: {self.name}")
        if det < 0 and not self.allow_mirror:
            raise AxisError(f"axis-mirror-refused: {self.name}; name the mirror explicitly")
        if self.scale <= 0:
            raise AxisError(f"axis-scale-not-positive: {self.scale}")

    @classmethod
    def preset(
        cls,
        name: str,
        *,
        scale: Fraction | int | float = 1,
        allow_mirror: bool = False,
    ) -> "AxisTransform":
        if name not in PRESETS:
            raise AxisError(f"unknown-axis-preset: {name}; known: {', '.join(sorted(PRESETS))}")
        return cls(name, PRESETS[name], Fraction(scale), allow_mirror)

    @property
    def determinant(self) -> int:
        return determinant(self.matrix)

    def vector(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        values = (Fraction(x), Fraction(y), Fraction(z))
        out = []
        for row in self.matrix:
            out.append(sum(Fraction(a) * b for a, b in zip(row, values)) * self.scale)
        return tuple(float(value) for value in out)  # type: ignore[return-value]

    def point(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        return self.vector(x, y, z)

    def normal(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        result = self.vector(x, y, z)
        length = sum(value * value for value in result) ** 0.5
        if length == 0:
            return result
        return tuple(value / length for value in result)  # type: ignore[return-value]

    def matrix4(self) -> tuple[tuple[float, float, float, float], ...]:
        return tuple(
            (
                float(self.matrix[row][0] * self.scale),
                float(self.matrix[row][1] * self.scale),
                float(self.matrix[row][2] * self.scale),
                0.0,
            )
            for row in range(3)
        ) + ((0.0, 0.0, 0.0, 1.0),)

    def witness(self) -> dict[str, object]:
        return {
            "name": self.name,
            "matrix": [list(row) for row in self.matrix],
            "determinant": self.determinant,
            "scale": str(self.scale),
            "touches_weights": False,
        }


def apply_positions(transform: AxisTransform, positions: Iterable[Sequence[float]]) -> list[tuple[float, float, float]]:
    return [transform.point(*position) for position in positions]
