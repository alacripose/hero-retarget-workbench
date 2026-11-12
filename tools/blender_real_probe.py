"""End-to-end probe with a real skinned, multi-material hero DMX.

Run from the forge checkout:

  blender -b --python tools/blender_real_probe.py -- \
    --dmx artifacts/vmdl-decompile/models/heroes_staging/haze/haze_body.dmx \
    --extraction artifacts/vmdl-decompile \
    --vmdl artifacts/vmdl-decompile/models/heroes_staging/haze/haze.vmdl \
    --materials-root artifacts/haze-materials \
    --stage artifacts/stage-real \
    --report artifacts/receipts/hero-retarget-workbench-real.json

The probe uses the extracted hero body itself as the replacement mesh. That is a
real skinned, multi-material mesh, not a generated placeholder. It records the
source and re-imported exported counts, stages the untouched S2V vmdl, and
compiles through the addon's compile action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import addon_utils
import bpy

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "blender"))
import hero_retarget_workbench as dmf  # noqa: E402


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--dmx", required=True)
    parser.add_argument("--extraction", required=True)
    parser.add_argument("--vmdl", required=True)
    parser.add_argument("--materials-root", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--addon-name", default="haze_real")
    parser.add_argument("--skip-compile", action="store_true")
    return parser.parse_args(argv)


def imported_meshes(before: set[str]) -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.name not in before]


def settle_weight_job(settings) -> None:
    while dmf.weights.is_running():
        job = dmf.weights._ACTIVE
        if job is None:
            break
        job._tick()
    if settings.proof_status != "current":
        raise RuntimeError(f"weight solve did not mint a current proof: {settings.proof_status} {settings.status}")


def mesh_metrics(obj: bpy.types.Object) -> dict:
    weighted = 0
    links = 0
    weight_sum = 0.0
    for vertex in obj.data.vertices:
        if vertex.groups:
            weighted += 1
        links += len(vertex.groups)
        weight_sum += sum(group.weight for group in vertex.groups)
    materials = [material.name if material else "" for material in obj.data.materials]
    polygon_materials = Counter(polygon.material_index for polygon in obj.data.polygons)
    return {
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "vertex_groups": len(obj.vertex_groups),
        "weighted_vertices": weighted,
        "weight_links": links,
        "weight_sum": round(weight_sum, 6),
        "materials": materials,
        "polygon_material_indices": {str(key): value for key, value in sorted(polygon_materials.items())},
        "armature_modifiers": [
            modifier.object.name if modifier.object else ""
            for modifier in obj.modifiers
            if modifier.type == "ARMATURE"
        ],
    }


def import_body(path: Path) -> tuple[bpy.types.Object, bpy.types.Object]:
    before = {obj.name for obj in bpy.context.scene.objects}
    result = bpy.ops.import_scene.kst_dmx(
        filepath=str(path),
        append="NEW_ARMATURE",
        upAxis="Z",
        forwardAxis="-Y",
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"DMX import did not finish: {result}")
    objects = imported_meshes(before)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if not meshes or not armatures:
        raise RuntimeError(f"DMX import produced no mesh/armature: {[obj.name for obj in objects]}")
    return max(meshes, key=lambda obj: len(obj.data.vertices)), max(
        armatures, key=lambda obj: len(obj.data.bones)
    )


def main() -> int:
    args = parse_args()
    source_dmx = Path(args.dmx).resolve()
    extraction = Path(args.extraction).resolve()
    vmdl = Path(args.vmdl).resolve()
    materials_root = Path(args.materials_root).resolve()
    stage = Path(args.stage).resolve()
    report_path = Path(args.report).resolve()
    addon = args.addon_name
    vmdl_relative = "models/heroes_staging/haze/haze.vmdl"
    target_relative = "models/heroes_staging/haze/haze_body.dmx"

    if not source_dmx.is_file():
        raise RuntimeError(f"missing source DMX: {source_dmx}")
    if not vmdl.is_file():
        raise RuntimeError(f"missing S2V vmdl: {vmdl}")
    if not extraction.is_dir():
        raise RuntimeError(f"missing extraction root: {extraction}")
    if not materials_root.is_dir():
        raise RuntimeError(f"missing materials root: {materials_root}")

    if stage.exists():
        import shutil

        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    dmf.register()
    report: dict = {
        "source_dmx": str(source_dmx),
        "source_dmx_sha256": digest(source_dmx),
        "source_vmdl": str(vmdl),
        "source_vmdl_sha256": digest(vmdl),
        "extraction": str(extraction),
        "materials_root": str(materials_root),
        "stage": str(stage),
        "addon": addon,
    }
    try:
        settings = bpy.context.scene.dmf
        settings.project_root = str(REPO)
        settings.stage_dir = str(stage)
        settings.addon_name = addon
        settings.vmdl = str(vmdl)
        settings.extraction_dir = str(extraction)
        settings.materials_dir = str(materials_root)
        settings.vmdl_relative = vmdl_relative
        settings.target_dmx_relative = target_relative
        settings.weight_mode = "CUSTOM"
        settings.proof_presenter = "real-mesh-probe"
        settings.proof_ticket = "TICKET-0002"
        settings.axis_preset = "identity"
        settings.fit_scale = 1.0
        settings.fit_to_height = False

        body, armature = import_body(source_dmx)
        settings.target_body = body
        settings.target_armature = armature
        collection = bpy.data.collections.new("real_probe_parts")
        bpy.context.scene.collection.children.link(collection)
        for old in list(body.users_collection):
            old.objects.unlink(body)
        collection.objects.link(body)
        settings.custom_collection = collection
        settings.custom_mesh = body
        settings.custom_armature = armature
        settings.material_source = body
        result = bpy.ops.dmf.scan_parts()
        if "FINISHED" not in result:
            raise RuntimeError(f"part scan failed: {result} status={settings.status}")
        result = bpy.ops.dmf.scan_materials()
        if "FINISHED" not in result:
            raise RuntimeError(f"material scan failed: {result} status={settings.status}")
        source_metrics = mesh_metrics(body)
        source_metrics["bones"] = len(armature.data.bones)
        source_metrics["bone_names"] = [bone.name for bone in armature.data.bones]
        report["source"] = source_metrics

        fit = bpy.ops.dmf.fit()
        if "FINISHED" not in fit:
            raise RuntimeError(f"fit failed: {fit} status={settings.status}")
        report["fit"] = {
            "axis": settings.axis_preset,
            "scale": settings.fit_scale,
            "height_match": settings.fit_to_height,
        }
        report["after_fit"] = mesh_metrics(body)

        retarget = bpy.ops.dmf.retarget()
        if "FINISHED" not in retarget:
            raise RuntimeError(f"retarget failed: {retarget} status={settings.status}")
        settle_weight_job(settings)
        if settings.unmatched:
            raise RuntimeError(f"retarget left unmatched groups: {settings.unmatched}")
        report["proof"] = {
            "status": settings.proof_status,
            "digest": settings.proof_digest,
            "artifact": settings.proof_artifact,
            "proof": settings.proof_path,
        }
        report["retarget"] = {
            "mode": settings.weight_mode,
            "unmatched": settings.unmatched,
            "armature_modifiers": [
                modifier.object.name if modifier.object else ""
                for modifier in body.modifiers
                if modifier.type == "ARMATURE"
            ],
            "after": mesh_metrics(body),
        }

        for index in range(settings.source_material_count):
            settings.source_material_index = index
            settings.part_material_index = index
            materials = bpy.ops.dmf.assign_material()
            if "FINISHED" not in materials:
                raise RuntimeError(f"material assignment failed: {materials} status={settings.status}")
        report["materials"] = {
            "mode": "selected-slot",
            "count": settings.material_count,
            "after": mesh_metrics(body),
        }

        export_stage = bpy.ops.dmf.export_stage()
        if "FINISHED" not in export_stage:
            raise RuntimeError(f"export/stage failed: {export_stage} status={settings.status}")
        # PulseSrcOps' export pushes an undo step; the addon re-fetches its
        # settings from the scene, and so must this probe.
        settings = bpy.context.scene.dmf
        stage_root = stage / "content" / "citadel_addons" / addon
        manifest_path = stage_root / "stage.json"
        staged_vmdl = stage_root / vmdl_relative
        staged_dmx = stage_root / target_relative
        if not manifest_path.is_file() or not staged_vmdl.is_file() or not staged_dmx.is_file():
            raise RuntimeError(f"stage did not produce the expected files under {stage_root}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("vmdl_modified") is not False:
            raise RuntimeError("stage manifest does not say vmdl_modified=false")
        if digest(staged_vmdl) != digest(vmdl):
            raise RuntimeError("staged vmdl differs from the S2V extraction")
        if manifest.get("vmdl_sha256") != digest(vmdl):
            raise RuntimeError("manifest vmdl hash differs from the S2V extraction")
        report["stage"] = {
            "root": str(stage_root),
            "manifest": str(manifest_path),
            "vmdl": str(staged_vmdl),
            "vmdl_sha256": digest(staged_vmdl),
            "vmdl_modified": manifest.get("vmdl_modified"),
            "custom_dmx": str(staged_dmx),
            "custom_dmx_bytes": staged_dmx.stat().st_size,
            "custom_dmx_sha256": digest(staged_dmx),
            "materials": manifest.get("materials"),
            "extraction_files": manifest.get("extraction_files"),
        }

        if not args.skip_compile:
            compile_result = bpy.ops.dmf.compile()
            if "FINISHED" not in compile_result:
                raise RuntimeError(f"compile failed: {compile_result} status={settings.status}")
            compiled = stage / "compiled" / addon / Path(vmdl_relative).with_suffix(".vmdl_c")
            if not compiled.is_file():
                raise RuntimeError(f"compile reported success but produced no output: {compiled}")
            log_path = REPO / "logs" / "compile.log"
            log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            summary = re.search(r"WARNING:\s+(\d+)\s+compiled,\s+(\d+)\s+failed", log_text)
            if summary:
                compiled_count, failed_count = (int(value) for value in summary.groups())
            else:
                compiled_count = failed_count = None
            report["compile"] = {
                "returncode": 0,
                "status": settings.status,
                "log": str(log_path),
                "argv": log_text.splitlines()[0] if log_text else "",
                "compiled": compiled_count,
                "failed": failed_count,
                "warnings": len(re.findall(r"RESOURCE COMPILE WARNING:", log_text)),
                "output": str(compiled),
                "output_bytes": compiled.stat().st_size,
                "output_sha256": digest(compiled),
            }

        # Re-import only the exported DMX to measure what actually left Blender.
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        exported_body, exported_armature = import_body(staged_dmx)
        exported_metrics = mesh_metrics(exported_body)
        exported_metrics["bones"] = len(exported_armature.data.bones)
        exported_metrics["bone_names"] = [bone.name for bone in exported_armature.data.bones]
        report["exported"] = exported_metrics

        comparisons = {
            "vertices_match": source_metrics["vertices"] == exported_metrics["vertices"],
            "bones_match": source_metrics["bones"] == exported_metrics["bones"],
            "vertex_groups_match": source_metrics["vertex_groups"] == exported_metrics["vertex_groups"],
            "weighted_vertices_match": source_metrics["weighted_vertices"] == exported_metrics["weighted_vertices"],
            "weight_links_match": source_metrics["weight_links"] == exported_metrics["weight_links"],
            "materials_match": source_metrics["materials"] == exported_metrics["materials"],
            "polygon_materials_match": source_metrics["polygon_material_indices"] == exported_metrics["polygon_material_indices"],
        }
        report["comparisons"] = comparisons
        missing = [name for name, ok in comparisons.items() if not ok]
        if missing:
            raise RuntimeError(f"real mesh comparison failed: {missing}")

        report["result"] = "pass"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"result": "pass", "report": str(report_path), "comparisons": comparisons}, sort_keys=True))
        return 0
    except Exception as error:
        report["result"] = "fail"
        report["error"] = f"{type(error).__name__}: {error}"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"result": "fail", "error": report["error"], "report": str(report_path)}, sort_keys=True))
        raise
    finally:
        try:
            dmf.unregister()
        except Exception as error:
            print(f"DMF_UNREGISTER_WARNING: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
