"""Chunked retarget solver for large custom meshes.

The solver does not use Blender's DATA_TRANSFER modifier. It reads the custom
mesh's own groups, maps or folds them, samples the hero body with a KD-tree when
the mesh is close, and falls back to mapped bone envelopes for geometry outside
the body. Work is processed in timer-sized chunks so the viewport stays alive.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import bpy
from mathutils import Vector, kdtree

from forge.weights import (
    BoneSegment,
    WeightError,
    envelope_weights,
    fold_source,
    merge_weights,
    normalize_weights,
)

from . import core

_CHUNK = 1200
_ACTIVE: "WeightJob | None" = None


@dataclass
class WeightOptions:
    mode: str = "HYBRID"
    max_distance: float = 0.35
    falloff: float = 2.0
    max_influences: int = 4
    surface_samples: int = 4
    extra_policy: str = "FOLD"
    fallback_target: str = ""
    protected: tuple[str, ...] = ()
    clear_existing: bool = True

    @classmethod
    def from_settings(cls, settings) -> "WeightOptions":
        protected = tuple(
            part.strip()
            for part in (settings.protected_groups or "").split(",")
            if part.strip()
        )
        return cls(
            mode=settings.weight_mode,
            max_distance=float(settings.max_distance),
            falloff=float(settings.falloff),
            max_influences=int(settings.max_influences),
            surface_samples=int(settings.surface_samples),
            extra_policy=settings.extra_policy,
            fallback_target=settings.fallback_bone,
            protected=protected,
            clear_existing=bool(settings.clear_existing),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "max_distance": self.max_distance,
            "falloff": self.falloff,
            "max_influences": self.max_influences,
            "surface_samples": self.surface_samples,
            "extra_policy": self.extra_policy,
            "fallback_target": self.fallback_target,
            "protected": list(self.protected),
            "clear_existing": self.clear_existing,
            "solver": "hybrid-kdtree-envelope",
            "uses_data_transfer": False,
        }


def _weight_dict(vertex, names: dict[int, str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for membership in vertex.groups:
        name = names.get(membership.group)
        if name and math.isfinite(membership.weight) and membership.weight > 0:
            result[name] = result.get(name, 0.0) + float(membership.weight)
    return result


def _body_samples(body, names: dict[int, str]):
    points = []
    weights = []
    for vertex in body.data.vertices:
        points.append(body.matrix_world @ vertex.co)
        weights.append(_weight_dict(vertex, names))
    tree = kdtree.KDTree(len(points))
    for index, point in enumerate(points):
        tree.insert(point, index)
    tree.balance()
    return tree, weights


class WeightSolver:
    def __init__(self, settings, options: WeightOptions):
        self.settings = settings
        self.options = options
        self.mesh = settings.custom_mesh
        self.armature = settings.target_armature
        self.body = settings.target_body
        self.custom_armature = settings.custom_armature
        if self.mesh is None or self.armature is None:
            raise WeightError("bind-needs-hero-and-mesh: choose a hero skeleton and a custom mesh")
        if self.options.max_influences < 1:
            raise WeightError("weight-influence-limit: max influences must be at least 1")

        self.group_names = {group.index: group.name for group in self.mesh.vertex_groups}
        self.source_weights = [_weight_dict(vertex, self.group_names) for vertex in self.mesh.data.vertices]
        self.parents: dict[str, str] = {}
        if self.custom_armature is not None:
            self.parents = {
                bone.name: bone.parent.name if bone.parent else ""
                for bone in self.custom_armature.data.bones
            }

        self.mapping: dict[str, str] = {}
        self.extra: dict[str, str] = {}
        self.ignored: set[str] = set()
        self.unmatched: list[str] = []
        self.source_totals: dict[str, float] = {}
        for weights_for_vertex in self.source_weights:
            for name, weight in weights_for_vertex.items():
                self.source_totals[name] = self.source_totals.get(name, 0.0) + weight
        self._read_map()
        self._validate_map()
        if self.options.extra_policy == "KEEP":
            self._copy_extra_bones()

        self.target_bones = set(self.armature.data.bones.keys())
        self.segments = self._target_segments()
        self.allowed_segments = [
            segment
            for segment in self.segments
            if not self.mapping or segment.name in set(self.mapping.values()) | set(self.extra.values())
        ]
        if not self.allowed_segments:
            self.allowed_segments = self.segments
        self.tree = None
        self.body_weights = []
        if self.body is not None and self.options.mode == "HYBRID":
            body_names = {group.index: group.name for group in self.body.vertex_groups}
            self.tree, self.body_weights = _body_samples(self.body, body_names)
        self._groups: dict[str, bpy.types.VertexGroup] = {}
        self.used_groups: set[str] = set()
        self.processed = 0
        self.total = len(self.mesh.data.vertices)
        self.unweighted = 0
        self.max_influences_seen = 0
        self.max_error = 0.0
        self.started = time.monotonic()
        if self.options.clear_existing:
            self._clear_groups()

    def _read_map(self) -> None:
        for entry in self.settings.bone_map:
            source = (entry.source or "").strip()
            if not source:
                continue
            if entry.state == "MAPPED":
                target = (entry.target or "").strip()
                if target:
                    self.mapping[source] = target
                else:
                    self.unmatched.append(source)
            elif entry.state == "EXTRA":
                self.extra[source] = (entry.target or source).strip()
            elif entry.state == "IGNORED":
                self.ignored.add(source)
            elif entry.state == "UNMATCHED":
                self.unmatched.append(source)

    def _validate_map(self) -> None:
        missing = sorted(
            {target for target in self.mapping.values() if target not in self.armature.data.bones}
        )
        if missing:
            raise WeightError("bone-map-target-missing: " + ", ".join(missing[:8]))
        collisions: dict[str, list[str]] = {}
        for source, target in self.mapping.items():
            collisions.setdefault(target, []).append(source)
        duplicate = [(target, sources) for target, sources in collisions.items() if len(sources) > 1]
        if duplicate:
            target, sources = duplicate[0]
            raise WeightError(
                f"bone-map-collision: {target} is the target of {', '.join(sorted(sources))}; "
                "choose one or mark the other as extra/ignored"
            )
        for source in self.unmatched:
            if self.source_totals.get(source, 0.0) > 1e-8:
                raise WeightError(
                    "bone-map-unresolved: "
                    f"{source} has weights but no target; choose a target, mark it Extra, or Ignore it"
                )

    def _target_segments(self) -> list[BoneSegment]:
        segments = []
        for bone in self.armature.data.bones:
            if not getattr(bone, "use_deform", True):
                continue
            head = self.armature.matrix_world @ bone.head_local
            tail = self.armature.matrix_world @ bone.tail_local
            segments.append(BoneSegment(bone.name, tuple(head), tuple(tail)))
        return segments

    def _copy_extra_bones(self) -> None:
        if self.custom_armature is None:
            raise WeightError(
                "extra-bones-need-custom-rig: Keep extra bones needs the custom armature; "
                "choose the rig or set Extra bones to Fold"
            )
        wanted = []
        for source in self.extra:
            if source not in self.armature.data.bones and source not in wanted:
                wanted.append(source)
        if not wanted:
            return
        core.select_only(bpy.context, [self.armature])
        bpy.context.view_layer.objects.active = self.armature
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            edit_bones = self.armature.data.edit_bones
            ordered = sorted(
                wanted,
                key=lambda name: self._depth(name),
            )
            for source in ordered:
                if source in edit_bones:
                    continue
                bone = self.custom_armature.data.bones.get(source)
                if bone is None:
                    raise WeightError(f"extra-bone-missing: {source} is not on the custom rig")
                created = edit_bones.new(source)
                created.matrix = (
                    self.armature.matrix_world.inverted()
                    @ self.custom_armature.matrix_world
                    @ bone.matrix_local
                )
                created.use_deform = True
                parent_source = bone.parent.name if bone.parent else ""
                parent_target = self.mapping.get(parent_source) or self.extra.get(parent_source) or ""
                if parent_source and parent_source in edit_bones and not parent_target:
                    parent_target = parent_source
                if parent_target and parent_target in edit_bones:
                    created.parent = edit_bones[parent_target]
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.context.view_layer.update()

    def _depth(self, name: str) -> int:
        depth = 0
        current = name
        seen = set()
        while current and current not in seen:
            seen.add(current)
            parent = self.parents.get(current, "")
            if not parent:
                break
            depth += 1
            current = parent
        return depth

    def _clear_groups(self) -> None:
        protected = set(self.options.protected)
        for group in list(self.mesh.vertex_groups):
            if group.name not in protected:
                self.mesh.vertex_groups.remove(group)
        self.group_names = {group.index: group.name for group in self.mesh.vertex_groups}

    def _group(self, name: str):
        group = self.mesh.vertex_groups.get(name)
        if group is None:
            group = self.mesh.vertex_groups.new(name=name)
        return group

    def _surface(self, point: Vector) -> dict[str, float]:
        if self.tree is None or not self.body_weights:
            return {}
        found = self.tree.find_n(point, max(1, self.options.surface_samples))
        merged: dict[str, float] = {}
        for _, index, distance in found:
            if distance > self.options.max_distance:
                continue
            factor = (1.0 / (distance + 1e-6)) ** self.options.falloff
            allowed = self.target_bones | set(self.extra.values())
            for name, weight in self.body_weights[index].items():
                if name in allowed:
                    merged[name] = merged.get(name, 0.0) + weight * factor
        return normalize_weights(merged, max_influences=self.options.max_influences)

    def _vertex_weights(self, index: int) -> dict[str, float]:
        prior = self.source_weights[index]
        protected = set(self.options.protected)
        base: dict[str, float] = {}
        for name, weight in prior.items():
            if name in protected:
                continue
            if name in self.ignored:
                continue
            target = fold_source(
                name,
                self.mapping,
                self.parents,
                extra_policy=self.options.extra_policy,
                fallback=self.options.fallback_target,
            )
            if target:
                base[target] = base.get(target, 0.0) + weight
        point = self.mesh.matrix_world @ self.mesh.data.vertices[index].co
        if self.options.mode == "CUSTOM":
            result = base
        elif self.options.mode == "ENVELOPE":
            result = envelope_weights(
                point,
                self.allowed_segments,
                max_distance=self.options.max_distance,
                falloff=self.options.falloff,
                max_influences=self.options.max_influences,
            )
        else:
            if base and sum(base.values()) >= 0.35:
                result = base
            else:
                surface = self._surface(point)
                if surface:
                    result = merge_weights(base, surface)
                else:
                    result = base or envelope_weights(
                        point,
                        self.allowed_segments,
                        max_distance=self.options.max_distance,
                        falloff=self.options.falloff,
                        max_influences=self.options.max_influences,
                    )
        return normalize_weights(result, max_influences=self.options.max_influences)

    def solve_range(self, start: int, end: int) -> None:
        end = min(end, self.total)
        for index in range(start, end):
            weights = self._vertex_weights(index)
            total = sum(weights.values())
            if total <= 1e-8:
                self.unweighted += 1
                continue
            self.max_influences_seen = max(self.max_influences_seen, len(weights))
            self.max_error = max(self.max_error, abs(total - 1.0))
            for name, weight in weights.items():
                if name in self.options.protected:
                    continue
                group = self._groups.get(name)
                if group is None:
                    group = self._group(name)
                    self._groups[name] = group
                group.add([index], weight, "REPLACE")
                self.used_groups.add(name)
            self.processed += 1

    def finish(self) -> None:
        if self.options.clear_existing:
            for group in list(self.mesh.vertex_groups):
                if group.name in self.used_groups or group.name in self.options.protected:
                    continue
                self.mesh.vertex_groups.remove(group)
        for modifier in [mod for mod in self.mesh.modifiers if mod.type == "ARMATURE"]:
            self.mesh.modifiers.remove(modifier)
        bind = self.mesh.modifiers.new("Deadlock Hero Armature", "ARMATURE")
        bind.object = self.armature
        bind.use_vertex_groups = True
        self.settings.unmatched = ", ".join(sorted(set(self.unmatched))[:8])
        bpy.context.view_layer.update()

    def stats(self) -> dict[str, object]:
        return {
            "vertices": self.total,
            "processed": self.processed,
            "unweighted": self.unweighted,
            "max_influences": self.max_influences_seen,
            "max_error": self.max_error,
            "seconds": round(time.monotonic() - self.started, 3),
            "mode": self.options.mode,
            "extra_policy": self.options.extra_policy,
        }


class WeightJob:
    def __init__(self, settings, options: WeightOptions):
        self.settings = settings
        self.options = options
        self.solver = WeightSolver(settings, options)
        self.settings.job_running = True
        self.settings.job_kind = "WEIGHTS"
        self.settings.job_label = "Solving weights"
        self.settings.job_message = "prepared; writing chunks"
        self.settings.job_progress = 0.0
        self.settings.job_cancellable = True
        self.settings.axis_tick += 1
        self._cancelled = False
        self._timer = bpy.app.timers.register(self._tick, first_interval=0.01, persistent=True)

    def _tick(self):
        global _ACTIVE
        if self._cancelled:
            return self._finish("cancelled")
        start = self.solver.processed
        end = min(start + _CHUNK, self.solver.total)
        try:
            self.solver.solve_range(start, end)
        except Exception as error:
            return self._finish(f"{type(error).__name__}: {error}")
        progress = end / max(1, self.solver.total)
        self.settings.job_progress = progress
        self.settings.job_message = f"{end:,} of {self.solver.total:,} vertices"
        if end < self.solver.total:
            return 0.01
        return self._finish(None)

    def _finish(self, error: str | None):
        global _ACTIVE
        self.settings.job_running = False
        self.settings.job_cancellable = False
        _ACTIVE = None
        if error:
            self.settings.job_progress = 0.0
            self.settings.job_message = ""
            core.set_status(self.settings, f"Weight solve stopped: {error}", "ERROR")
            return None
        try:
            self.solver.finish()
            from . import proofing

            proof, admission = proofing.mint(self.settings, self.options)
            stats = self.solver.stats()
            self.settings.job_progress = 1.0
            self.settings.job_message = ""
            if admission.ok:
                core.set_status(
                    self.settings,
                    f"Bound {stats['vertices']:,} vertices in {stats['seconds']}s; proof {proof.artifact_digest[:18]} is current",
                    "OK",
                )
            else:
                core.set_status(
                    self.settings,
                    "Weights solved but the Axis proof is refused: " + "; ".join(admission.reasons()),
                    "ERROR",
                )
        except Exception as error:  # keep the weights, name the failing proof/check
            core.set_status(self.settings, f"Weights solved but binding/proof failed: {error}", "ERROR")
        return None

    def cancel(self) -> None:
        self._cancelled = True


def start(settings, options: WeightOptions) -> None:
    global _ACTIVE
    if _ACTIVE is not None:
        raise WeightError("weight-job-running: another weight solve is already running")
    _ACTIVE = WeightJob(settings, options)


def cancel() -> None:
    if _ACTIVE is not None:
        _ACTIVE.cancel()


def is_running() -> bool:
    return _ACTIVE is not None


def run_to_completion(settings, options: WeightOptions, chunk: int = 2000) -> WeightSolver:
    """Used by the headless probe; production uses the timer chunks."""
    solver = WeightSolver(settings, options)
    while solver.processed < solver.total:
        solver.solve_range(solver.processed, min(solver.processed + chunk, solver.total))
    solver.finish()
    return solver


def unregister() -> None:
    global _ACTIVE
    if _ACTIVE is not None:
        try:
            bpy.app.timers.unregister(_ACTIVE._tick)
        except Exception:
            pass
        _ACTIVE = None
