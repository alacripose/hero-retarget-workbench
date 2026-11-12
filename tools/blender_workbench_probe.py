"""Headless probe for the workbench, solver and Axis proof.

Run from the forge checkout:

  blender -b --factory-startup --python tools/blender_workbench_probe.py -- \
    --report artifacts/receipts/hero-retarget-workbench-workbench.json

The probe builds two tiny rigs and meshes. It exercises the code paths that do
not need a visible viewport: registration, bone scan, rename, rest alignment,
the hybrid solver, proof minting, proof verification and proof staleness. It
does not claim the split viewport was visually checked.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
_spec = importlib.util.spec_from_file_location(
    "dmf_workbench_probe",
    PACKAGE / "__init__.py",
    submodule_search_locations=[str(PACKAGE)],
)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"could not load checkout addon: {PACKAGE}")
dmf = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dmf
_spec.loader.exec_module(dmf)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="artifacts/receipts/hero-retarget-workbench-workbench.json")
    return parser.parse_args(argv)


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def armature(name: str, bones: list[tuple[str, tuple[float, float, float], tuple[float, float, float], str]]):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name, head, tail, parent in bones:
        edit = data.edit_bones.new(bone_name)
        edit.head = head
        edit.tail = tail
        if parent:
            edit.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def mesh(name: str, vertices, faces, groups: dict[str, list[int]]):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    for group_name, indices in groups.items():
        group = obj.vertex_groups.new(name=group_name)
        group.add(indices, 1.0, "REPLACE")
    return obj


def main() -> int:
    args = parse_args()
    report_path = REPO / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="dmf-workbench-probe-"))
    report: dict[str, object] = {"result": "fail", "temp": str(temp)}

    dmf.register()
    try:
        settings = bpy.context.scene.dmf
        settings.project_root = str(REPO)
        settings.proof_presenter = "probe"
        settings.proof_ticket = "TICKET-0002"
        settings.weight_mode = "HYBRID"
        settings.extra_policy = "FOLD"
        settings.fallback_bone = "spine_01"
        settings.max_distance = 1.0
        settings.max_influences = 4
        settings.clear_existing = True

        target_arm = armature(
            "hero_rig",
            [
                ("spine_01", (0, 0, 0), (0, 0, 1.0), ""),
                ("head", (0, 0, 1.0), (0, 0, 2.0), "spine_01"),
            ],
        )
        target_body = mesh(
            "hero_body",
            [(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0),
             (-0.5, -0.5, 2), (0.5, -0.5, 2), (0.5, 0.5, 2), (-0.5, 0.5, 2)],
            [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
            {"spine_01": [0, 1, 2, 3], "head": [4, 5, 6, 7]},
        )
        target_body.modifiers.new("Hero Armature", "ARMATURE").object = target_arm

        custom_arm = armature(
            "custom_rig",
            [
                ("spine_01", (0, 0, 0), (0, 0, 1.0), ""),
                ("rename_me", (0, 0, 1.0), (0, 0, 2.0), "spine_01"),
                ("tail_01", (0, 0, -1.0), (0, 0, -2.0), "spine_01"),
            ],
        )
        custom = mesh(
            "custom_mesh",
            [
                (0, 0, 0.1), (0, 0, 0.6), (0, 0, 1.6),
                (3.0, 0, -1.4), (0, 0, -2.1),
            ],
            [(0, 1, 2), (2, 3, 4)],
            {"spine_01": [0, 1], "rename_me": [2], "tail_01": [3, 4]},
        )
        settings.target_armature = target_arm
        settings.target_body = target_body
        settings.custom_armature = custom_arm
        settings.custom_mesh = custom

        count = dmf.workbench.scan_bone_map(settings)
        by_source = {entry.source: entry for entry in settings.bone_map}
        if count != 3 or by_source["spine_01"].state != "MAPPED":
            raise RuntimeError(f"bone scan failed: {[(e.source, e.state, e.target) for e in settings.bone_map]}")
        rename = by_source["rename_me"]
        rename.target = "head"
        rename.state = "MAPPED"
        settings.bone_map_index = list(settings.bone_map).index(rename)
        result = bpy.ops.dmf.rename_bones()
        if "FINISHED" not in result or custom_arm.data.bones.get("head") is None:
            raise RuntimeError(f"rename failed: {result} status={settings.status} bones={[b.name for b in custom_arm.data.bones]}")
        if custom.vertex_groups.get("head") is None:
            raise RuntimeError("rename did not move the matching vertex group")

        by_source = {entry.source: entry for entry in settings.bone_map}
        tail = by_source["tail_01"]
        tail.state = "EXTRA"
        tail.target = "tail_01"
        settings.bone_map_index = list(settings.bone_map).index(tail)
        result = bpy.ops.dmf.align_all_bones()
        if "FINISHED" not in result:
            raise RuntimeError(f"align failed: {result} status={settings.status}")
        head_bone = custom_arm.data.bones["head"]
        if (head_bone.head_local - target_arm.data.bones["head"].head_local).length > 1e-5:
            raise RuntimeError("head bone was not aligned to the hero rest pose")

        options = dmf.weights.WeightOptions.from_settings(settings)
        solver = dmf.weights.run_to_completion(settings, options)
        stats = solver.stats()
        if stats["unweighted"]:
            raise RuntimeError(f"solver left unweighted vertices: {stats}")
        if custom.vertex_groups.get("spine_01") is None:
            raise RuntimeError("solver did not write the hero spine group")

        proof, admission = dmf.proofing.mint(settings, options)
        if not admission.ok:
            raise RuntimeError(f"proof refused: {admission.reasons()}")
        if not proof.artifact_digest.startswith("blake3:"):
            raise RuntimeError(f"proof was not BLAKE3: {proof.artifact_digest}")
        verified = dmf.proofing.verify(settings)
        if not verified.ok:
            raise RuntimeError(f"verify refused: {verified.reasons()}")

        artifact = REPO / proof.artifact
        original = artifact.read_bytes()
        dummy_vmdl = temp / "haze.vmdl"
        dummy_vmdl.write_bytes(b"opaque vmdl marker\n")
        settings.vmdl = str(dummy_vmdl)
        settings.target_dmx_relative = "models/heroes_staging/haze/haze_body.dmx"
        settings.addon_name = "probe_addon"
        artifact.write_bytes(original + b" ")
        stale = dmf.proofing.verify(settings)
        if stale.ok:
            raise RuntimeError("tampered proof artifact was still admitted")
        try:
            export_refused = bpy.ops.dmf.export_stage()
        except RuntimeError:
            export_refused = {"CANCELLED"}
        if "CANCELLED" not in export_refused:
            raise RuntimeError("export did not refuse a stale proof")
        artifact.write_bytes(original)
        restored = dmf.proofing.verify(settings)
        if not restored.ok:
            raise RuntimeError(f"restored proof did not verify: {restored.reasons()}")

        custom2_arm = armature(
            "custom_rig_keep",
            [
                ("spine_01", (0, 0, 0), (0, 0, 1.0), ""),
                ("tail_keep", (0, 0, -1.0), (0, 0, -2.0), "spine_01"),
            ],
        )
        custom2 = mesh(
            "custom_mesh_keep",
            [(0, 0, 0.2), (0, 0, 0.8), (3.0, 0, -1.5)],
            [(0, 1, 2)],
            {"spine_01": [0, 1], "tail_keep": [2]},
        )
        settings.custom_armature = custom2_arm
        settings.custom_mesh = custom2
        settings.extra_policy = "KEEP"
        dmf.workbench.scan_bone_map(settings)
        for entry in settings.bone_map:
            if entry.source == "tail_keep":
                entry.state = "EXTRA"
                entry.target = "tail_keep"
        options2 = dmf.weights.WeightOptions.from_settings(settings)
        dmf.weights.run_to_completion(settings, options2)
        if target_arm.data.bones.get("tail_keep") is None:
            raise RuntimeError("Keep extra bones did not copy tail_keep into the hero rig")
        proof2, admission2 = dmf.proofing.mint(settings, options2)
        if not admission2.ok:
            raise RuntimeError(f"keep-extra proof refused: {admission2.reasons()}")
        if not proof2.artifact_digest.startswith("blake3:"):
            raise RuntimeError("keep-extra proof was not BLAKE3")

        left, right = dmf.workbench._compare_objects(settings)
        if not left or not right or settings.custom_mesh not in right:
            raise RuntimeError(f"compare object sets are wrong: left={left} right={right}")

        # Exercise the timer-backed background wrapper without a visible event loop.
        background_seen = []
        error = dmf.jobs.start(
            settings,
            "probe background",
            lambda progress: (progress(0.5, "halfway"), 42)[1],
            lambda result: background_seen.append(result),
            lambda failure: background_seen.append(failure),
        )
        if error:
            raise RuntimeError(error)
        while dmf.jobs.is_running():
            active_job = dmf.jobs.active()
            if active_job is not None:
                active_job._tick()
            time.sleep(0.01)
        if background_seen != [42]:
            raise RuntimeError(f"background job failed: {background_seen}")

        # Exercise the chunked weight job itself, not just run_to_completion.
        settings.custom_mesh = custom
        settings.custom_armature = custom_arm
        settings.extra_policy = "FOLD"
        dmf.workbench.scan_bone_map(settings)
        for entry in settings.bone_map:
            if entry.state == "UNMATCHED":
                entry.state = "EXTRA"
                entry.target = entry.source
        options3 = dmf.weights.WeightOptions.from_settings(settings)
        dmf.weights.start(settings, options3)
        while dmf.weights.is_running():
            active_weight = dmf.weights._ACTIVE
            if active_weight is not None:
                active_weight._tick()
            time.sleep(0.01)
        if settings.job_running or settings.proof_status != "current":
            raise RuntimeError(
                f"chunked weight job did not finish current: {settings.proof_status} {settings.status}"
            )

        report.update(
            {
                "result": "pass",
                "bone_map": [
                    {"source": entry.source, "target": entry.target, "state": entry.state}
                    for entry in settings.bone_map
                ],
                "solver": stats,
                "proof": {
                    "artifact": proof.artifact,
                    "artifact_digest": proof.artifact_digest,
                    "tick_span": proof.tick_span,
                    "status_after_restore": settings.proof_status,
                    "checks": [{"name": c.name, "token": c.token, "detail": c.detail} for c in proof.checks],
                },
                "keep_extra_proof": {
                    "artifact": proof2.artifact,
                    "artifact_digest": proof2.artifact_digest,
                    "tick_span": proof2.tick_span,
                    "target_bone": "tail_keep",
                },
                "stale_refusal": [refusal.detail for refusal in stale.refusals],
                "export_refused": "CANCELLED" in export_refused,
                "background_job": background_seen[0],
                "chunked_weight_job": {
                    "status": settings.proof_status,
                    "job_running": settings.job_running,
                    "job_progress": settings.job_progress,
                },
                "compare": {"left": [obj.name for obj in left], "right": [obj.name for obj in right]},
            }
        )
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"result": "pass", "report": str(report_path), "proof": settings.proof_status}, sort_keys=True))
        return 0
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"result": "fail", "error": report["error"], "report": str(report_path)}, sort_keys=True))
        raise
    finally:
        try:
            dmf.unregister()
        except Exception as error:
            print(f"DMF_UNREGISTER_WARNING: {error}", file=sys.stderr)
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
