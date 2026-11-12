"""Headless LOD and material-preservation probe.

Run from the forge checkout:

  blender -b --python tools/blender_lod_material_probe.py -- \
    --dmx artifacts/vmdl-decompile/models/heroes_staging/haze/haze_body.dmx \
    --extraction artifacts/vmdl-decompile \
    --vmdl artifacts/vmdl-decompile/models/heroes_staging/haze/haze.vmdl \
    --materials-root artifacts/haze-materials \
    --stage artifacts/lod-material-probe \
    --report artifacts/receipts/hero-retarget-workbench-lod-material.json \
    --compile

The probe uses the real Haze body as the ported mesh, gives it one custom vmat
path, and does not call the hero-material assignment button. It then checks the
exported base and every LOD DMX for the custom material, stages them over the
hero's existing `_lod13`, `_lod26` and `_lod39` slots, and optionally compiles.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import addon_utils
import bpy

REPO = Path(__file__).resolve().parents[1]

# The user's Blender may already have an installed copy of this addon in its
# addon scan. Load the checkout under a private module name so the probe always
# exercises the source being edited, even under --factory-startup.
_PACKAGE = REPO / "blender" / "hero_retarget_workbench"
_spec = importlib.util.spec_from_file_location(
    "dmf_lod_probe",
    _PACKAGE / "__init__.py",
    submodule_search_locations=[str(_PACKAGE)],
)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"could not load the checkout addon: {_PACKAGE}")
dmf = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dmf
_spec.loader.exec_module(dmf)


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
    parser.add_argument("--addon-name", default="haze_lod_material")
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--keep-stage", action="store_true")
    return parser.parse_args(argv)


def import_dmx(path: Path) -> tuple[bpy.types.Object, bpy.types.Object]:
    before = {obj.name for obj in bpy.context.scene.objects}
    result = bpy.ops.import_scene.kst_dmx(
        filepath=str(path),
        append="NEW_ARMATURE",
        upAxis="Z",
        forwardAxis="-Y",
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"DMX import did not finish: {result}")
    imported = [obj for obj in bpy.context.scene.objects if obj.name not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    armatures = [obj for obj in imported if obj.type == "ARMATURE"]
    if not meshes or not armatures:
        raise RuntimeError(f"DMX import produced no mesh/armature: {[obj.name for obj in imported]}")
    return max(meshes, key=lambda obj: len(obj.data.vertices)), max(
        armatures, key=lambda obj: len(obj.data.bones)
    )


def mesh_metrics(obj: bpy.types.Object) -> dict:
    return {
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "materials": [material.name if material else "" for material in obj.data.materials],
        "polygon_material_indices": {
            str(key): value
            for key, value in sorted(Counter(polygon.material_index for polygon in obj.data.polygons).items())
        },
    }


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def settle_weight_job(settings) -> None:
    while dmf.weights.is_running():
        job = dmf.weights._ACTIVE
        if job is None:
            break
        job._tick()
    if settings.proof_status != "current":
        raise RuntimeError(f"weight solve did not mint a current proof: {settings.proof_status} {settings.status}")


def main() -> int:
    args = parse_args()
    source_dmx = Path(args.dmx).resolve()
    extraction = Path(args.extraction).resolve()
    vmdl = Path(args.vmdl).resolve()
    materials_root = Path(args.materials_root).resolve()
    stage = Path(args.stage).resolve()
    report_path = Path(args.report).resolve()
    addon = args.addon_name
    target_relative = "models/heroes_staging/haze/haze_body.dmx"
    vmdl_relative = "models/heroes_staging/haze/haze.vmdl"
    custom_relative = "models/custom/materials/custom_port_body.vmat"
    custom_basename = Path(custom_relative).name

    for path, label in (
        (source_dmx, "source DMX"),
        (vmdl, "S2V vmdl"),
        (materials_root, "materials root"),
        (extraction, "extraction root"),
    ):
        if label.endswith("root"):
            if not path.is_dir():
                raise RuntimeError(f"missing {label}: {path}")
        elif not path.is_file():
            raise RuntimeError(f"missing {label}: {path}")

    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    custom_root = stage.parent / f"{stage.name}-materials"
    if custom_root.exists():
        shutil.rmtree(custom_root)
    custom_material = custom_root / custom_relative
    custom_material.parent.mkdir(parents=True, exist_ok=True)
    custom_material.write_text(
        '"Layer0"\n'
        '{\n'
        '\t"shader"\t"pbr.vfx"\n'
        '\t"F_USE_NPR_LIGHTING"\t"1"\n'
        '\t"F_USE_STATUS_EFFECTS_PROXY"\t"1"\n'
        '\t"TextureColor1"\t"materials/default/default_color.tga"\n'
        '}\n',
        encoding="utf-8",
    )

    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    dmf.register()
    report: dict = {
        "source_dmx": str(source_dmx),
        "source_dmx_sha256": digest(source_dmx),
        "source_vmdl": str(vmdl),
        "source_vmdl_sha256": digest(vmdl),
        "extraction": str(extraction),
        "materials_root": str(materials_root),
        "custom_material": custom_relative,
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
        settings.custom_materials_dir = str(custom_root)
        settings.vmdl_relative = vmdl_relative
        settings.target_dmx_relative = target_relative
        settings.weight_mode = "CUSTOM"
        settings.proof_presenter = "lod-material-probe"
        settings.proof_ticket = "TICKET-0002"
        settings.axis_preset = "identity"
        settings.fit_scale = 1.0
        settings.fit_to_height = False
        settings.generate_lods = True
        settings.lod_count = 0
        settings.lod_decimate = 25.0

        body, armature = import_dmx(source_dmx)
        armature.name = "hero_rig"
        body.name = "haze_body"
        custom = body.copy()
        custom.data = body.data.copy()
        bpy.context.scene.collection.objects.link(custom)
        custom.name = "ported_body"
        custom.data.materials.clear()
        custom.data.materials.append(bpy.data.materials.new(name=custom_relative))
        for polygon in custom.data.polygons:
            polygon.material_index = 0

        settings.target_body = body
        settings.target_armature = armature
        settings.custom_mesh = custom
        settings.custom_armature = None
        report["source"] = {
            "body": mesh_metrics(body),
            "custom": mesh_metrics(custom),
            "bones": len(armature.data.bones),
        }

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

        export_stage = bpy.ops.dmf.export_stage()
        if "FINISHED" not in export_stage:
            raise RuntimeError(f"export/stage failed: {export_stage} status={settings.status}")
        settings = bpy.context.scene.dmf
        stage_root = stage / "content" / "citadel_addons" / addon
        manifest_path = stage_root / "stage.json"
        staged_vmdl = stage_root / vmdl_relative
        staged_base = stage_root / target_relative
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("vmdl_modified") is not False:
            raise RuntimeError("stage manifest does not say vmdl_modified=false")
        if digest(staged_vmdl) != digest(vmdl):
            raise RuntimeError("staged vmdl differs from the S2V extraction")
        if bpy.data.objects.get("ported_body") is None or bpy.data.objects.get("haze_body") is None:
            raise RuntimeError("export did not restore the custom and hero source object names")
        if manifest.get("custom_materials") != 1:
            raise RuntimeError(f"custom material was not staged: {manifest.get('custom_materials')}")
        if custom_material.relative_to(custom_root).as_posix() != custom_relative:
            raise RuntimeError("custom material fixture moved")
        staged_custom = stage_root / custom_relative
        if staged_custom.read_bytes() != custom_material.read_bytes():
            raise RuntimeError("staged custom vmat differs from the source vmat")

        expected_lods = [
            "models/heroes_staging/haze/haze_body_lod13.dmx",
            "models/heroes_staging/haze/haze_body_lod26.dmx",
            "models/heroes_staging/haze/haze_body_lod39.dmx",
        ]
        staged_lods = [entry["relative"] for entry in manifest.get("lods", [])]
        if staged_lods != expected_lods:
            raise RuntimeError(f"LOD slots were not replaced: {staged_lods}")
        for index, relative in enumerate(staged_lods, 1):
            path = stage_root / relative
            if not path.is_file():
                raise RuntimeError(f"missing staged LOD {index}: {path}")
            if path.stat().st_size <= 0:
                raise RuntimeError(f"empty staged LOD {index}: {path}")

        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        measurements = {}
        for label, path in [
            ("base", staged_base),
            *[(f"lod{index}", stage_root / relative) for index, relative in enumerate(staged_lods, 1)],
        ]:
            mesh, reimported_arm = import_dmx(path)
            metrics = mesh_metrics(mesh)
            metrics["bones"] = len(reimported_arm.data.bones)
            if len(metrics["materials"]) != 1 or not metrics["materials"][0].endswith(custom_basename):
                raise RuntimeError(f"{label} did not keep the custom material: {metrics['materials']}")
            if metrics["vertices"] <= 0 or metrics["polygons"] <= 0:
                raise RuntimeError(f"{label} is empty: {metrics}")
            measurements[label] = metrics
            clear_scene()

        for index in range(1, 4):
            if measurements[f"lod{index}"]["polygons"] >= measurements["base"]["polygons"]:
                raise RuntimeError(f"lod{index} was not decimated")

        report["stage"] = {
            "root": str(stage_root),
            "manifest": str(manifest_path),
            "vmdl_sha256": digest(staged_vmdl),
            "vmdl_modified": manifest.get("vmdl_modified"),
            "custom_material_count": manifest.get("custom_materials"),
            "lod_slots": staged_lods,
        }
        report["measurements"] = measurements

        if args.compile:
            compile_result = bpy.ops.dmf.compile()
            if "FINISHED" not in compile_result:
                raise RuntimeError(f"compile failed: {compile_result} status={settings.status}")
            compiled = stage / "compiled" / addon / Path(vmdl_relative).with_suffix(".vmdl_c")
            if not compiled.is_file():
                raise RuntimeError(f"compile reported success but produced no output: {compiled}")
            log_path = REPO / "logs" / "compile.log"
            log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            summary = re.search(r"WARNING:\s+(\d+)\s+compiled,\s+(\d+)\s+failed", log_text)
            report["compile"] = {
                "returncode": 0,
                "status": settings.status,
                "log": str(log_path),
                "argv": log_text.splitlines()[0] if log_text else "",
                "compiled": int(summary.group(1)) if summary else None,
                "failed": int(summary.group(2)) if summary else None,
                "warnings": len(re.findall(r"RESOURCE COMPILE WARNING:", log_text)),
                "output": str(compiled),
                "output_bytes": compiled.stat().st_size,
                "output_sha256": digest(compiled),
            }

        report["result"] = "pass"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"result": "pass", "report": str(report_path), "measurements": measurements}, sort_keys=True))
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
        if not args.keep_stage:
            shutil.rmtree(custom_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
