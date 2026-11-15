"""Build the the hero + the tail source tail component inputs.

This does not replace the hero's body.  It exports:

* ``hero_body_tailbones.dmx`` - the hero's own body with the tail source's tail bones
  added to its skeleton (the body mesh is untouched).
* ``<hero>_tail.dmx`` - only the tail source's tail geometry, skinned to those same
  tail bones, for a separate RenderMeshFile component.
* ``<target>.dmx`` and ``<target>.dmx`` - the hero's own
  clips with the the tail source source tail keys copied in.

Run headless:

    blender --background --factory-startup --python-exit-code 1 \
      --python tools/blender_build_tail_component.py -- \
      --hero-extraction <hero extraction> --source-extraction <tail source extraction> \n      --clips target_clip=source_clip --out artifacts/tail-build --report artifacts/receipts/tail-build.json
"""

from __future__ import annotations

import argparse
import addon_utils
import importlib.util
import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]

def _port_target():
    """Load forge.port_target by path: the add-on's vendored `forge` shadows the repo one."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "dmf_port_target", ROOT / "forge" / "port_target.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ADDON_ROOT = ROOT / "blender"
PACKAGE = "dmf_tail_component_build"
EXTRACTIONS = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "Blender Foundation"
    / "Blender"
    / "5.4"
    / "datafiles"
    / "hero_retarget_workbench"
    / "artifacts"
    / "extractions"
)
# Resolved from --hero-extraction/--source-extraction in main; no hero is named
# in this file, so the same builder serves any pair.
HERO = None
SOURCE = None
CLIPS = ()


def args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--hero-extraction", required=True, help="extraction holding the hero to put a tail on")
    parser.add_argument("--hero", default="", help="hero folder name inside that extraction")
    parser.add_argument("--source-extraction", required=True, help="extraction holding the tail source hero")
    parser.add_argument("--source-hero", default="", help="tail source hero folder name")
    parser.add_argument("--clips", default="", help="comma separated target=source clip pairs")
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args(argv)


def unshadow() -> None:
    for entry in list(sys.path):
        try:
            candidate = Path(entry)
        except (TypeError, ValueError):
            continue
        if candidate.name == "hero_retarget_workbench" or (candidate / "hero_retarget_workbench" / "forge").is_dir():
            sys.path.remove(entry)
    for name in [name for name in sys.modules if name == "forge" or name.startswith("forge.")]:
        module = sys.modules[name]
        if "hero_retarget_workbench" in str(getattr(module, "__file__", "") or ""):
            del sys.modules[name]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def load_addon():
    package = ADDON_ROOT / "hero_retarget_workbench"
    spec = importlib.util.spec_from_file_location(
        PACKAGE, package / "__init__.py", submodule_search_locations=[str(package)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def import_body(path: Path):
    before = {obj.name for obj in bpy.context.scene.objects}
    s2 = sys.modules[f"{PACKAGE}.source2"]
    s2.import_dmx(path, append="NEW_ARMATURE")
    new = [obj for obj in bpy.context.scene.objects if obj.name not in before]
    rig = max((obj for obj in new if obj.type == "ARMATURE"), key=lambda obj: len(obj.data.bones))
    meshes = [obj for obj in new if obj.type == "MESH"]
    mesh = max(meshes, key=lambda obj: len(obj.data.vertices))
    return rig, mesh, new


def export_collection(name: str, objects, destination: Path, stem: str) -> Path:
    scene = bpy.context.scene
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    for obj in objects:
        collection.objects.link(obj)
    old = {
        "path": scene.vs.export_path,
        "format": scene.vs.export_format,
        "engine": scene.vs.engine,
        "dmx": scene.vs.dmx_format,
        "encoding": scene.vs.dmx_encoding,
    }
    old_list = [(row.name, row.ob_type, getattr(row, "icon", ""), row.collection.name if row.collection else "") for row in scene.vs.export_list]
    old_flags = {obj.name: bool(getattr(getattr(obj, "vs", None), "export", False)) for obj in objects}
    destination.mkdir(parents=True, exist_ok=True)
    try:
        for obj in objects:
            if hasattr(obj, "vs"):
                obj.vs.export = True
            if obj.type == "MESH" and hasattr(obj.vs, "generate_lods"):
                obj.vs.generate_lods = False
        collection.vs.export = True
        scene.vs.export_path = str(destination) + "/"
        scene.vs.export_format = "DMX"
        scene.vs.engine = "SOURCE"
        scene.vs.dmx_format = "22_modeldoc"
        scene.vs.dmx_encoding = "3"
        scene.vs.export_list.clear()
        row = scene.vs.export_list.add()
        row.name = collection.name
        row.ob_type = "COLLECTION"
        row.icon = "GROUP"
        row.collection = collection
        before = {path for path in destination.rglob("*.dmx")}
        old_debug = bpy.app.debug_value
        bpy.app.debug_value = max(2, old_debug)
        try:
            result = bpy.ops.export_scene.smd(collection=collection.name)
        finally:
            bpy.app.debug_value = old_debug
        if "FINISHED" not in result:
            raise RuntimeError(f"export did not finish: {result}")
        created = [path for path in destination.rglob("*.dmx") if path not in before]
        if not created:
            raise RuntimeError(f"export produced no DMX for {name}")
        chosen = max(created, key=lambda path: path.stat().st_size)
        target = destination / f"{stem}.dmx"
        if chosen != target:
            chosen.replace(target)
        return target
    finally:
        scene.vs.export_path = old["path"]
        scene.vs.export_format = old["format"]
        scene.vs.engine = old["engine"]
        scene.vs.dmx_format = old["dmx"]
        scene.vs.dmx_encoding = old["encoding"]
        scene.vs.export_list.clear()
        for _name, ob_type, icon, collection_name in old_list:
            row = scene.vs.export_list.add()
            row.name = _name
            row.ob_type = ob_type
            if icon:
                row.icon = icon
            if collection_name:
                row.collection = bpy.data.collections.get(collection_name)
        for obj in objects:
            if hasattr(obj, "vs"):
                obj.vs.export = old_flags.get(obj.name, False)
        bpy.data.collections.remove(collection)


def extract_tail(source_mesh: bpy.types.Object, target_rig: bpy.types.Object) -> bpy.types.Object:
    import bmesh

    tail = source_mesh.copy()
    tail.data = source_mesh.data.copy()
    tail.name = "DMF Tail"
    tail.data.name = "DMF Tail"
    bpy.context.scene.collection.objects.link(tail)
    groups = [group for group in tail.vertex_groups if group.name.lower().startswith("tail_")]
    if not groups:
        raise RuntimeError("tail-source-groups-missing")
    ids = {group.index for group in groups}
    selected = {
        vertex.index
        for vertex in tail.data.vertices
        if any(group.group in ids and group.weight > 0.0 for group in vertex.groups)
    }
    if not selected:
        raise RuntimeError("tail-source-vertices-missing")
    bm = bmesh.new()
    bm.from_mesh(tail.data)
    drop = [vertex for vertex in bm.verts if vertex.index not in selected]
    if drop:
        bmesh.ops.delete(bm, geom=drop, context="VERTS")
    bm.to_mesh(tail.data)
    bm.free()
    tail.data.update()
    # The copy kept the source armature modifier; point it at the hero's rig.
    for modifier in tail.modifiers:
        if modifier.type == "ARMATURE":
            modifier.object = target_rig
    if not any(modifier.type == "ARMATURE" for modifier in tail.modifiers):
        tail.modifiers.new("Armature", "ARMATURE").object = target_rig
    tail.parent = target_rig
    return tail


def action_tail_stats(action) -> dict:
    animated = set()
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for bag in getattr(strip, "channelbags", ()):
                for curve in bag.fcurves:
                    if curve.data_path.startswith('pose.bones["tail_'):
                        animated.add(curve.data_path.split('"')[1])
    return {"tail_bones": sorted(animated), "frames": [int(round(v)) for v in action.frame_range]}


def main() -> int:
    global HERO, SOURCE, CLIPS
    options = args()
    port_target = _port_target()

    HERO = port_target.hero_root(options.hero_extraction, options.hero)
    SOURCE = port_target.hero_root(options.source_extraction, options.source_hero)
    CLIPS = tuple(
        tuple(part.strip() for part in pair.split("=", 1))
        for pair in options.clips.split(",")
        if "=" in pair
    )
    out = Path(options.out)
    out.mkdir(parents=True, exist_ok=True)
    unshadow()
    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    load_addon()
    tailops = sys.modules[f"{PACKAGE}.tailops"]
    clipops = sys.modules[f"{PACKAGE}.clipops"]
    settings = bpy.context.scene.dmf
    report = {"checks": {}, "errors": [], "outputs": {}}

    hero_body = port_target.body_dmx(HERO)
    source_body = port_target.body_dmx(SOURCE)
    settings.extraction_dir = str(Path(options.hero_extraction).resolve())
    settings.body_dmx = str(hero_body)
    hero_rig, hero_mesh, _ = import_body(hero_body)
    settings.target_armature = hero_rig
    report[HERO.name] = {"rig": hero_rig.name, "bones": len(hero_rig.data.bones), "vertices": len(hero_mesh.data.vertices)}

    wolf_rig, wolf_mesh, wolf_objects = import_body(source_body)
    report[SOURCE.name] = {"rig": wolf_rig.name, "bones": len(wolf_rig.data.bones), "vertices": len(wolf_mesh.data.vertices)}
    tail = extract_tail(wolf_mesh, hero_rig)
    report["tail"] = {"vertices": len(tail.data.vertices), "vertices_total": len(wolf_mesh.data.vertices)}
    for obj in wolf_objects:
        if obj.type == "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)
    # Keep the source rig for the source clips.
    source = wolf_rig
    settings.tail_armature = source

    copied = tailops._copy_tail_bones(settings, source)
    report["bones"] = copied
    report["tail_bones"] = tailops._tail_names(source)
    if len([name for name in report["tail_bones"] if hero_rig.data.bones.get(name)]) < 6:
        report["errors"].append("tail-bones-missing-on-hero")

    body = export_collection("DMF Tail Body Export", [hero_mesh, hero_rig], out, f"{HERO.name}_body_tailbones")
    tail_dmx = export_collection("DMF Tail Component Export", [tail, hero_rig], out, f"{HERO.name}_tail")
    report["outputs"]["body"] = str(body)
    report["outputs"]["tail"] = str(tail_dmx)

    for target_stem, source_stem in CLIPS:
        target_path = HERO / f"{target_stem}.dmx"
        source_path = SOURCE / "dmx" / "animation" / f"{source_stem}.dmx"
        if not source_path.is_file():
            source_path = SOURCE / "clips" / f"{source_stem}.dmx"
        if not target_path.is_file() or not source_path.is_file():
            report["errors"].append(f"clip-missing: {target_stem} <- {source_stem}")
            continue
        target_action = clipops._import_one(settings, type("Row", (), {
            "path": str(target_path), "label": target_stem, "name": target_path.name,
            "action": "", "state": "", "source_hero": "",
        })())
        source_action = tailops._import_source_clip(source, source_path, source_stem)
        result = tailops._write_tail_action(settings, type("Row", (), {"label": target_stem})(), bpy.data.actions[target_action], source, source_action, report["tail_bones"])
        entry = type("Row", (), {"action": target_action, "label": target_stem, "ag": "AG2"})()
        written = clipops.write_action(settings, entry, out / "clips")
        destination = out / f"{target_stem}.dmx"
        if written != destination:
            written.replace(destination)
        report["outputs"][target_stem] = str(destination)
        report["checks"][target_stem] = {**result, **action_tail_stats(bpy.data.actions[target_action])}

    report["ok"] = not report["errors"]
    path = Path(options.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    bpy.ops.wm.quit_blender()
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
