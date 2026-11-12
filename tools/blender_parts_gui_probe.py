"""GUI probe for the Parts & Materials panel.

Run without -b so Blender has a real window and 3D area:

  blender --factory-startup --python tools/blender_parts_gui_probe.py
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "deadlock_model_forge"
SPEC = importlib.util.spec_from_file_location(
    "dmf_parts_gui_probe",
    PACKAGE / "__init__.py",
    submodule_search_locations=[str(PACKAGE)],
)
assert SPEC is not None and SPEC.loader is not None
dmf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dmf
SPEC.loader.exec_module(dmf)


def _material(name: str):
    material = bpy.data.materials.new(name)
    return material


def _cube(name: str, location, collection):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def run() -> None:
    try:
        dmf.register()
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)

        bpy.ops.object.armature_add()
        armature = bpy.context.object
        armature.name = "hero_rig"

        body = _cube("hero_body", (0.0, 0.0, 0.0), bpy.context.scene.collection)
        for name in ("hero_body", "hero_head", "hero_hands"):
            body.data.materials.append(_material(name))

        collection = bpy.data.collections.new("DMF Haze Parts")
        bpy.context.scene.collection.children.link(collection)
        parts = [
            _cube("haze_body", (2.0, 0.0, 0.0), collection),
            _cube("haze_backpack", (3.0, 0.0, 0.0), collection),
            _cube("haze_head", (4.0, 0.0, 0.0), collection),
        ]
        for part in parts:
            part.data.materials.append(_material(f"{part.name}_surface"))

        settings = bpy.context.scene.dmf
        settings.target_armature = armature
        settings.target_body = body
        settings.material_source = body
        settings.custom_collection = collection
        dmf.parts.scan_parts(settings)
        settings.custom_mesh = parts[0]
        dmf.parts.use_part(settings, 0)
        dmf.parts.scan_materials(settings)
        print(
            "PART_PANEL_READY",
            len(settings.parts),
            settings.custom_mesh.name,
            settings.source_material_count,
            settings.material_count,
        )

        window = bpy.context.window
        screen = window.screen if window else None
        areas = [area for area in screen.areas if area.type == "VIEW_3D"] if screen else []
        if not areas:
            raise RuntimeError("probe has no 3D area")
        area = areas[0]
        area.spaces.active.show_region_ui = True
        region = next(item for item in area.regions if item.type == "UI")
        with bpy.context.temp_override(window=window, screen=screen, area=area, region=region):
            print("PANEL_RESULT", bpy.ops.wm.call_panel(name="DMF_PT_parts"))

        def screenshot():
            print(
                "SCREENSHOT",
                bpy.ops.screen.screenshot(
                    filepath=str(REPO / "artifacts" / "receipts" / "parts-panel.png")
                ),
            )
            bpy.ops.wm.quit_blender()

        bpy.app.timers.register(screenshot, first_interval=3.0)
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()


bpy.app.timers.register(run, first_interval=1.0)
