"""Axis proof checks and artifact minting for the Blender workbench."""
from __future__ import annotations

import math
import re
from pathlib import Path

import bpy

from forge.hashes import blake3_hex
from forge.proof import (
    Admission,
    Check,
    Proof,
    ProofError,
    ProofWindow,
    Refusal,
    TOKEN_ABSENT,
    TOKEN_FAIL,
    TOKEN_PASS,
    TOKEN_REFUSED,
    TOKEN_STALE,
    TOKEN_UNCHECKED,
    admit,
    canonical_bytes,
    read_proof,
    verify_bytes,
    weights_payload,
    world_digest,
    write_artifact,
    write_proof,
)
from forge.weights import fold_source

from . import core

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe(value: str) -> str:
    return _SAFE.sub("_", value).strip("._") or "mesh"


def _round(value: float, places: int = 6) -> float:
    return round(float(value), places)


def _mapping(settings) -> tuple[dict[str, str], dict[str, str], set[str], dict[str, str]]:
    mapped: dict[str, str] = {}
    extra: dict[str, str] = {}
    ignored: set[str] = set()
    states: dict[str, str] = {}
    for entry in settings.bone_map:
        source = (entry.source or "").strip()
        if not source:
            continue
        states[source] = entry.state
        if entry.state == "MAPPED" and (entry.target or "").strip():
            mapped[source] = entry.target.strip()
        elif entry.state == "EXTRA":
            extra[source] = (entry.target or source).strip()
        elif entry.state == "IGNORED":
            ignored.add(source)
    return mapped, extra, ignored, states


def _parents(settings) -> dict[str, str]:
    armature = settings.custom_armature
    if armature is None:
        return {}
    return {
        bone.name: bone.parent.name if bone.parent else ""
        for bone in armature.data.bones
    }


def _mesh_content(mesh) -> str:
    names = {group.index: group.name for group in mesh.vertex_groups}
    parts: list[str] = []
    for vertex in mesh.data.vertices:
        weights = sorted(
            (names.get(item.group, ""), item.weight)
            for item in vertex.groups
            if names.get(item.group)
        )
        parts.append(
            f"{vertex.index}:{vertex.co.x:.6f},{vertex.co.y:.6f},{vertex.co.z:.6f}"
            + ":"
            + ",".join(f"{name}={weight:.6f}" for name, weight in weights)
        )
    return blake3_hex("\n".join(parts).encode("utf-8"))


def world_state(settings) -> dict[str, object]:
    mesh = settings.custom_mesh
    armature = settings.target_armature
    if mesh is None or armature is None:
        return {"mesh": "", "armature": "", "present": False}
    bones = []
    for bone in armature.data.bones:
        bones.append(
            {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else "",
                "head": [_round(part) for part in bone.head_local],
                "tail": [_round(part) for part in bone.tail_local],
            }
        )
    mapped, extra, ignored, states = _mapping(settings)
    return {
        "present": True,
        "mesh": mesh.name,
        "mesh_vertices": len(mesh.data.vertices),
        "mesh_polygons": len(mesh.data.polygons),
        "mesh_groups": sorted(group.name for group in mesh.vertex_groups),
        "mesh_content": _mesh_content(mesh),
        "armature": armature.name,
        "armature_bones": bones,
        "mapping": dict(sorted(mapped.items())),
        "extra": dict(sorted(extra.items())),
        "ignored": sorted(ignored),
        "states": dict(sorted(states.items())),
        "tick": int(settings.axis_tick),
    }


def artifact_payload(settings, options) -> dict[str, object]:
    mesh = settings.custom_mesh
    armature = settings.target_armature
    if mesh is None or armature is None:
        raise ProofError("proof-needs-mesh-and-armature: import and bind the model first")
    names = {group.index: group.name for group in mesh.vertex_groups}
    vertices = []
    for vertex in mesh.data.vertices:
        weights = sorted(
            (names.get(item.group, ""), _round(item.weight))
            for item in vertex.groups
            if names.get(item.group) and item.weight > 1e-8
        )
        vertices.append(
            {
                "p": [_round(part) for part in vertex.co],
                "w": [[name, weight] for name, weight in weights],
            }
        )
    mapped, extra, ignored, states = _mapping(settings)
    return weights_payload(
        mesh=mesh.name,
        armature=armature.name,
        mode=options.mode,
        mapping=mapped,
        extras=extra,
        options={**options.as_dict(), "states": dict(sorted(states.items())), "ignored": sorted(ignored)},
        vertices=vertices,
    )


def _check(name: str, ok: bool, detail: str) -> Check:
    return Check(name, TOKEN_PASS if ok else TOKEN_FAIL, detail)


def live_checks(settings, options) -> list[Check]:
    mesh = settings.custom_mesh
    armature = settings.target_armature
    if mesh is None or armature is None:
        return [
            Check("mesh", TOKEN_ABSENT, "custom mesh and hero skeleton are required"),
            Check("weight-coverage", TOKEN_UNCHECKED, "no mesh to read"),
            Check("normalization", TOKEN_UNCHECKED, "no weights to read"),
            Check("influence-limit", TOKEN_UNCHECKED, "no weights to read"),
            Check("bone-map", TOKEN_UNCHECKED, "no mesh to read"),
            Check("binding", TOKEN_UNCHECKED, "no mesh to read"),
            Check("extra-bones", TOKEN_UNCHECKED, "no mesh to read"),
            Check("deformation", TOKEN_UNCHECKED, "no mesh to read"),
        ]
    names = {group.index: group.name for group in mesh.vertex_groups}
    mapped, extra, ignored, states = _mapping(settings)
    parents = _parents(settings)
    totals: dict[str, float] = {}
    unweighted = 0
    negative = 0
    non_finite = 0
    max_influences = 0
    max_error = 0.0
    for vertex in mesh.data.vertices:
        weights = {}
        for item in vertex.groups:
            name = names.get(item.group, "")
            if not name:
                continue
            weight = float(item.weight)
            if not math.isfinite(weight):
                non_finite += 1
                continue
            if weight < -1e-8:
                negative += 1
            if weight > 0:
                weights[name] = weights.get(name, 0.0) + weight
                totals[name] = totals.get(name, 0.0) + weight
        if not weights:
            unweighted += 1
            continue
        max_influences = max(max_influences, len(weights))
        max_error = max(max_error, abs(sum(weights.values()) - 1.0))

    unresolved = []
    target_missing = []
    for name, total in sorted(totals.items()):
        if total <= 1e-8 or name in ignored:
            continue
        state = states.get(name, "")
        if state == "MAPPED" and name in mapped:
            if mapped[name] not in armature.data.bones:
                target_missing.append(f"{name}->{mapped[name]}")
            continue
        if state == "EXTRA" and name in extra:
            if options.extra_policy == "KEEP" and extra[name] not in armature.data.bones:
                target_missing.append(f"{name}->{extra[name]}")
            elif options.extra_policy == "FOLD" and fold_source(
                name, mapped, parents, extra_policy="FOLD", fallback=options.fallback_target
            ) is None:
                unresolved.append(name)
            continue
        if state in ("MAPPED", "EXTRA", "IGNORED"):
            continue
        if options.mode in ("HYBRID", "ENVELOPE") and name in armature.data.bones:
            # An unrigged custom mesh has no source rows. The solver's output is
            # already a target bone, so it is not an unresolved source group.
            continue
        unresolved.append(name)

    binding_ok = any(
        modifier.type == "ARMATURE" and modifier.object is armature
        for modifier in mesh.modifiers
    )
    extra_ok = not target_missing
    if options.extra_policy == "DROP":
        extra_ok = extra_ok and not any(
            states.get(name) == "EXTRA" and total > 1e-8 for name, total in totals.items()
        )
    if options.extra_policy == "FOLD":
        extra_ok = extra_ok and not unresolved
    if options.extra_policy == "KEEP":
        extra_ok = extra_ok and all(
            target in armature.data.bones for target in extra.values()
        )

    deformation_detail = "not evaluated"
    deformation_ok = False
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = mesh.evaluated_get(depsgraph)
        evaluated_mesh = evaluated.to_mesh()
        try:
            if len(evaluated_mesh.vertices) != len(mesh.data.vertices):
                deformation_detail = "evaluated vertex count changed"
            else:
                bad = sum(
                    1
                    for vertex in evaluated_mesh.vertices
                    if not all(math.isfinite(part) for part in vertex.co)
                )
                deformation_ok = bad == 0
                deformation_detail = (
                    f"evaluated {len(evaluated_mesh.vertices):,} vertices at frame "
                    f"{bpy.context.scene.frame_current}; {bad} non-finite"
                )
        finally:
            evaluated.to_mesh_clear()
    except Exception as error:
        deformation_detail = f"evaluation failed: {error}"

    return [
        _check(
            "weight-coverage",
            unweighted == 0,
            f"{len(mesh.data.vertices) - unweighted:,} of {len(mesh.data.vertices):,} vertices weighted",
        ),
        _check(
            "normalization",
            max_error <= 1e-4 and non_finite == 0 and negative == 0,
            f"max sum error {max_error:.6g}; {non_finite} non-finite; {negative} negative",
        ),
        _check(
            "influence-limit",
            max_influences <= options.max_influences,
            f"{max_influences} influences; limit {options.max_influences}",
        ),
        _check(
            "bone-map",
            not unresolved and not target_missing,
            "no unresolved weighted groups"
            if not unresolved and not target_missing
            else "unresolved: " + ", ".join((unresolved + target_missing)[:8]),
        ),
        _check("binding", binding_ok, "armature modifier targets the hero skeleton" if binding_ok else "no hero armature modifier"),
        _check(
            "extra-bones",
            extra_ok,
            f"policy {options.extra_policy}; no extra target is missing"
            if extra_ok
            else "extra groups need a target bone or an explicit policy",
        ),
        _check("deformation", deformation_ok, deformation_detail),
    ]


def _set_checks(settings, checks) -> None:
    settings.proof_checks.clear()
    for check in checks:
        row = settings.proof_checks.add()
        row.name = check.name
        row.token = check.token
        row.detail = check.detail


def _apply(settings, proof: Proof, admission, root: Path) -> None:
    settings.proof_path = str(root / f"artifacts/proofs/{_safe(settings.custom_mesh.name)}-weights-{proof.tick_span[0]}.proof.json")
    settings.proof_artifact = str(root / proof.artifact)
    settings.proof_digest = proof.artifact_digest
    settings.proof_claim = proof.claim
    settings.proof_tick = f"{proof.tick_span[0]}..{proof.tick_span[1]}"
    settings.proof_world_digest = proof.world_digest
    settings.proof_status = "current" if admission.ok else "refused"
    _set_checks(settings, proof.checks)


def mint(settings, options) -> tuple[Proof, Admission]:
    root = core.project_root(settings)
    mesh = settings.custom_mesh
    armature = settings.target_armature
    if mesh is None or armature is None:
        raise ProofError("proof-needs-mesh-and-armature: import and bind the model first")
    payload = artifact_payload(settings, options)
    tick = int(settings.axis_tick)
    artifact_relative = f"artifacts/proofs/{_safe(mesh.name)}-weights-{tick}.json"
    artifact_path, digest = write_artifact(root, artifact_relative, payload)
    checks = live_checks(settings, options)
    checks.append(Check("artifact", TOKEN_PASS, f"{artifact_path.name} written"))
    weighted = sum(
        1 for vertex in mesh.data.vertices if any(item.weight > 1e-8 for item in vertex.groups)
    )
    proof = Proof(
        artifact=artifact_relative,
        artifact_digest=digest,
        claim=f"vertex weights for {mesh.name} on {armature.name}",
        origin="executed",
        evidence=(
            f"{len(mesh.data.vertices):,} vertices; {weighted:,} weighted; "
            f"method {options.mode}; extra policy {options.extra_policy}"
        ),
        tick_span=(tick, tick),
        world_digest=world_digest(world_state(settings)),
        presenter=(settings.proof_presenter or "").strip(),
        ticket=(settings.proof_ticket or "").strip(),
        checks=tuple(checks),
    )
    proof_relative = f"artifacts/proofs/{_safe(mesh.name)}-weights-{tick}.proof.json"
    write_proof(root, proof_relative, proof)
    admission = admit(proof, root, ProofWindow(current_tick=tick, max_age_ticks=0))
    _apply(settings, proof, admission, root)
    return proof, admission


def verify(settings) -> Admission:
    root = core.project_root(settings)
    path_text = settings.proof_path
    if not path_text:
        settings.proof_status = "unchecked"
        return Admission(refusals=[Refusal(TOKEN_UNCHECKED, "no Axis proof has been minted")])
    path = Path(path_text)
    if not path.is_file():
        settings.proof_status = "absent"
        return Admission(refusals=[Refusal(TOKEN_ABSENT, f"proof is not on disk: {path}")])
    try:
        proof = read_proof(path)
    except Exception as error:
        settings.proof_status = "refused"
        return Admission(refusals=[Refusal(TOKEN_REFUSED, f"proof cannot be read: {error}")])
    admission = admit(proof, root, ProofWindow(current_tick=int(settings.axis_tick), max_age_ticks=0))
    current_world = world_digest(world_state(settings))
    if current_world != proof.world_digest:
        admission.refusals.append(
            Refusal(TOKEN_STALE, "mesh, rig or bone map changed since the proof was minted")
        )
    from .weights import WeightOptions

    current_checks = live_checks(settings, WeightOptions.from_settings(settings))
    current_checks.append(Check("artifact", TOKEN_PASS if not verify_bytes(root, proof) else TOKEN_FAIL, "artifact bytes checked"))
    for check in current_checks:
        if check.token != TOKEN_PASS:
            admission.refusals.append(
                Refusal(TOKEN_REFUSED, f"live check {check.name} returned {check.token}: {check.detail}")
            )
    _set_checks(settings, current_checks)
    settings.proof_status = "current" if admission.ok else "stale"
    return admission


def require_current(settings) -> Admission:
    admission = verify(settings)
    if not admission.ok:
        raise ProofError("axis-proof-refused: " + "; ".join(admission.reasons()))
    return admission


def invalidate(settings, reason: str = "") -> None:
    if settings.proof_status == "unchecked":
        return
    settings.proof_status = "stale"


def bump_tick(settings) -> None:
    settings.axis_tick += 1
    invalidate(settings)
