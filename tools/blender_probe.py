"""Headless Blender evidence probe.

Run:
  blender -b --python tools/blender_probe.py -- \
    --dmx <live haze body.dmx> --vmat <live haze_body.vmat> --out <temp stage>

This is a developer probe, not part of the addon runtime. It exercises the real
Blender operators against live-extracted files and a byte-marker vmdl fixture;
it never creates a vmdl for production and never compiles.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import addon_utils
import bpy

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "blender"))
import deadlock_model_forge as dmf  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settle_weight_job(settings) -> None:
    while dmf.weights.is_running():
        job = dmf.weights._ACTIVE
        if job is None:
            break
        job._tick()
    if settings.proof_status != "current":
        raise RuntimeError(f"weight solve did not mint a current proof: {settings.proof_status} {settings.status}")


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--dmx", required=True)
    parser.add_argument("--vmat", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    source_dmx = Path(args.dmx).resolve()
    source_vmat = Path(args.vmat).resolve()
    temp = Path(tempfile.mkdtemp(prefix="dmf-probe-"))
    extraction = temp / "extraction"
    extraction.mkdir()
    shutil.copyfile(source_dmx, extraction / "haze_body.dmx")
    (extraction / "materials").mkdir()
    shutil.copyfile(source_vmat, extraction / "materials" / "haze_body.vmat")
    vmdl = extraction / "haze.vmdl"
    vmdl.write_bytes(b"BYTE-MARKER-VMDL\n\x00\xff")
    out = Path(args.out).resolve() if args.out else temp / "staged"

    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    dmf.register()
    assert hasattr(bpy.types.Scene, "dmf"), "addon did not register"
    settings = bpy.context.scene.dmf
    settings.project_root = str(REPO)
    settings.stage_dir = str(out)
    settings.addon_name = "probe"
    settings.vmdl = str(vmdl)
    settings.extraction_dir = str(extraction)
    settings.vmdl_relative = "models/heroes_staging/haze/haze.vmdl"
    settings.target_dmx_relative = "models/heroes_staging/haze/haze_body.dmx"

    before = {obj.name for obj in bpy.context.scene.objects}
    result = bpy.ops.import_scene.kst_dmx(
        filepath=str(source_dmx),
        append="NEW_ARMATURE",
        upAxis="Z",
        forwardAxis="-Y",
    )
    assert "FINISHED" in result, result
    imported = [obj for obj in bpy.context.scene.objects if obj.name not in before]
    armature = max((obj for obj in imported if obj.type == "ARMATURE"), key=lambda obj: len(obj.data.bones))
    body = max((obj for obj in imported if obj.type == "MESH"), key=lambda obj: len(obj.data.vertices))
    print(f"IMPORT armature={armature.name} bones={len(armature.data.bones)} mesh={body.name} verts={len(body.data.vertices)}")
    assert len(armature.data.bones) >= 100
    assert len(body.data.vertices) > 1000

    bpy.ops.mesh.primitive_cube_add()
    custom = bpy.context.active_object
    custom.name = "probe_custom"
    collection = bpy.data.collections.new("probe_parts")
    bpy.context.scene.collection.children.link(collection)
    for old in list(custom.users_collection):
        old.objects.unlink(custom)
    collection.objects.link(custom)
    bpy.ops.mesh.primitive_cube_add(location=(2.0, 0.0, 0.0))
    other = bpy.context.active_object
    other.name = "probe_other_part"
    for old in list(other.users_collection):
        old.objects.unlink(other)
    collection.objects.link(other)
    settings.custom_collection = collection
    settings.custom_mesh = custom
    settings.target_armature = armature
    settings.target_body = body
    settings.material_source = body
    result = bpy.ops.dmf.scan_parts()
    assert "FINISHED" in result, result
    assert len(settings.parts) == 2, len(settings.parts)
    other_index = next(index for index, part in enumerate(settings.parts) if part.object == other)
    custom_index = next(index for index, part in enumerate(settings.parts) if part.object == custom)
    settings.part_index = other_index
    result = bpy.ops.dmf.use_part()
    assert "FINISHED" in result, result
    assert settings.custom_mesh == other
    settings.part_index = custom_index
    result = bpy.ops.dmf.use_part()
    assert "FINISHED" in result, result
    assert settings.custom_mesh == custom
    result = bpy.ops.dmf.scan_materials()
    assert "FINISHED" in result, result
    assert settings.source_material_count == len(body.data.materials)
    settings.weight_mode = "HYBRID"
    settings.proof_presenter = "probe"
    settings.proof_ticket = "TICKET-0002"
    settings.fit_to_height = False
    settings.axis_preset = "identity"

    result = bpy.ops.dmf.fit()
    assert "FINISHED" in result, result
    result = bpy.ops.dmf.retarget()
    assert "FINISHED" in result, result
    settle_weight_job(settings)
    assert any(modifier.type == "ARMATURE" for modifier in custom.modifiers)
    for index in range(len(body.data.materials)):
        settings.source_material_index = index
        result = bpy.ops.dmf.append_material()
        assert "FINISHED" in result, result
    assert len(custom.data.materials) == len(body.data.materials)
    settings.part_material_index = 0
    settings.source_material_index = 0
    result = bpy.ops.dmf.assign_material()
    assert "FINISHED" in result, result
    assert len(custom.data.materials) == len(body.data.materials)
    settings.part_material_index = len(custom.data.materials) - 1
    result = bpy.ops.dmf.clear_part_material()
    assert "FINISHED" in result, result
    assert len(custom.data.materials) == len(body.data.materials) - 1
    settings.source_material_index = len(body.data.materials) - 1
    result = bpy.ops.dmf.append_material()
    assert "FINISHED" in result, result
    assert len(custom.data.materials) == len(body.data.materials)

    result = bpy.ops.dmf.export_stage()
    assert "FINISHED" in result, result
    manifest = out / "content" / "citadel_addons" / "probe" / "stage.json"
    staged_vmdl = out / "content" / "citadel_addons" / "probe" / "models" / "heroes_staging" / "haze" / "haze.vmdl"
    staged_dmx = out / "content" / "citadel_addons" / "probe" / "models" / "heroes_staging" / "haze" / "haze_body.dmx"
    assert manifest.is_file(), manifest
    assert staged_vmdl.read_bytes() == vmdl.read_bytes(), "stage changed the vmdl"
    assert digest(staged_vmdl) == digest(vmdl)
    assert staged_dmx.is_file() and staged_dmx.stat().st_size > 1000
    print(f"STAGE manifest={manifest}")
    print(f"STAGE vmdl_sha256={digest(staged_vmdl)} dmx_bytes={staged_dmx.stat().st_size}")
    dmf.unregister()
    shutil.rmtree(temp, ignore_errors=True)
    print("PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
