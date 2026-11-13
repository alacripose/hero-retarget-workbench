"""Screenshot the real viewport so the bone map can be looked at.

The owner's installed addon shadows the ``hero_retarget_workbench`` module name at
Blender startup, so this loads the checkout by file location instead, the same way
``tools/blender_panel_gui_probe.py`` does.

  blender --factory-startup --python tools/blender_bone_map_gui_probe.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
SPEC = importlib.util.spec_from_file_location(
    "dmf_map_gui_probe",
    PACKAGE / "__init__.py",
    submodule_search_locations=[str(PACKAGE)],
)
assert SPEC is not None and SPEC.loader is not None
dmf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dmf
SPEC.loader.exec_module(dmf)

OUT = REPO / "artifacts" / "hierarchy-diag" / "bone-map-viewport.png"

BONES = [
    ("root", None, (0.0, 0.0, 0.0), (0.0, 0.0, 6.0)),
    ("spine_0", "root", (0.0, 0.0, 6.0), (0.0, 0.0, 14.0)),
    ("spine_1", "spine_0", (0.0, 0.0, 14.0), (0.0, 0.0, 22.0)),
    ("neck_0", "spine_1", (0.0, 0.0, 22.0), (0.0, 0.0, 26.0)),
    ("head", "neck_0", (0.0, 0.0, 26.0), (0.0, 0.0, 33.0)),
    ("clavicle_l", "spine_1", (2.0, 0.0, 22.0), (7.0, 0.0, 22.0)),
    ("arm_l", "clavicle_l", (7.0, 0.0, 22.0), (16.0, 0.0, 18.0)),
    ("hand_l", "arm_l", (16.0, 0.0, 18.0), (21.0, 0.0, 15.0)),
    ("clavicle_r", "spine_1", (-2.0, 0.0, 22.0), (-7.0, 0.0, 22.0)),
    ("arm_r", "clavicle_r", (-7.0, 0.0, 22.0), (-16.0, 0.0, 18.0)),
    ("hand_r", "arm_r", (-16.0, 0.0, 18.0), (-21.0, 0.0, 15.0)),
    ("thigh_l", "root", (4.0, 0.0, 0.0), (4.0, 0.0, -18.0)),
    ("calf_l", "thigh_l", (4.0, 0.0, -18.0), (4.0, 0.0, -34.0)),
    ("thigh_r", "root", (-4.0, 0.0, 0.0), (-4.0, 0.0, -18.0)),
    ("calf_r", "thigh_r", (-4.0, 0.0, -18.0), (-4.0, 0.0, -34.0)),
]


def rig() -> bpy.types.Object:
    bpy.ops.object.armature_add(enter_editmode=True)
    armature = bpy.context.object
    armature.name = "map_rig"
    edit = armature.data.edit_bones
    for name, parent, head, tail in BONES:
        bone = edit.get(name) or edit.new(name)
        bone.head = head
        bone.tail = tail
        bone.parent = edit.get(parent) if parent else None
    keep = {item[0] for item in BONES}
    for stale in [bone for bone in edit if bone.name not in keep]:
        edit.remove(stale)
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def setup() -> None:
    dmf.register()
    settings = bpy.context.scene.dmf
    settings.target_armature = rig()
    settings.show_bone_map = True
    settings.bone_map_labels = True
    settings.bone_map_plane = "FRONT"
    dmf.workbench.build_hierarchy(settings)
    settings.hierarchy_index = dmf.workbench.hierarchy_index(settings, "head")
    window = bpy.context.window
    print("GUI windows", len(bpy.context.window_manager.windows), flush=True)
    if window is not None and window.screen is not None:
        print(
            "GUI areas",
            [(area.type, area.width, area.height) for area in window.screen.areas],
            flush=True,
        )


def shoot() -> None:
    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    except Exception as error:
        print("GUI redraw failed", type(error).__name__, error, flush=True)
    try:
        bpy.ops.screen.screenshot(filepath=str(OUT))
        print(f"GUI screenshot {OUT}", flush=True)
    except Exception as error:
        print("GUI screenshot failed", type(error).__name__, error, flush=True)
    print(f"GUI draw_error={bpy.context.scene.dmf.bone_map_error!r}", flush=True)
    bpy.ops.wm.quit_blender()


def bail() -> None:
    print("GUI timeout, quitting", flush=True)
    bpy.ops.wm.quit_blender()


try:
    setup()
except Exception as error:
    print("GUI setup failed", type(error).__name__, error, flush=True)
    bpy.ops.wm.quit_blender()
else:
    bpy.app.timers.register(shoot, first_interval=2.5)
    bpy.app.timers.register(bail, first_interval=25.0)
