"""GUI probe for every Deadlock panel and the compare split.

Run without -b so Blender has a real window and 3D area:

  blender --factory-startup --python tools/blender_panel_gui_probe.py
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
SPEC = importlib.util.spec_from_file_location(
    "dmf_compare_gui_probe",
    PACKAGE / "__init__.py",
    submodule_search_locations=[str(PACKAGE)],
)
assert SPEC is not None and SPEC.loader is not None
dmf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dmf
SPEC.loader.exec_module(dmf)


def run() -> None:
    try:
        dmf.register()
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.object.armature_add()
        armature = bpy.context.object
        armature.name = "hero_rig"
        bpy.ops.mesh.primitive_cube_add()
        mesh = bpy.context.object
        mesh.name = "custom_mesh"
        settings = bpy.context.scene.dmf
        settings.target_armature = armature
        settings.target_body = mesh
        settings.custom_mesh = mesh

        window = bpy.context.window
        screen = window.screen if window else None
        areas = [area for area in screen.areas if area.type == "VIEW_3D"] if screen else []
        print("AREAS_BEFORE", len(areas), [(area.x, area.y, area.width, area.height) for area in areas])
        if not areas:
            raise RuntimeError("probe has no 3D area")
        areas[0].spaces.active.show_region_ui = True
        region = next(item for area in areas for item in area.regions if item.type == "WINDOW")
        with bpy.context.temp_override(window=window, screen=screen, area=areas[0], region=region):
            result = bpy.ops.dmf.compare_split()
        print("OPERATOR_RESULT", result)
        print("STATUS", settings.status, settings.status_kind, "ACTIVE", settings.compare_active)
        after = [area for area in screen.areas if area.type == "VIEW_3D"]
        print("AREAS_AFTER", len(after), [(area.x, area.y, area.width, area.height) for area in after])
        for area in after:
            print("LOCAL_VIEW", area.x, area.y, area.spaces.active.local_view is not None)
        ui_region = next(item for item in areas[0].regions if item.type == "UI")
        for panel in (
            "DMF_PT_source",
            "DMF_PT_parts",
            "DMF_PT_compare",
            "DMF_PT_skeleton",
            "DMF_PT_weights",
            "DMF_PT_handoff",
        ):
            with bpy.context.temp_override(window=window, screen=screen, area=areas[0], region=ui_region):
                print("PANEL_RESULT", panel, bpy.ops.wm.call_panel(name=panel))

        def screenshot():
            print("SCREENSHOT", bpy.ops.screen.screenshot(filepath=str(REPO / "artifacts" / "receipts" / "compare-panel.png")))
            bpy.ops.wm.quit_blender()

        bpy.app.timers.register(screenshot, first_interval=0.8)
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()


bpy.app.timers.register(run, first_interval=1.0)
