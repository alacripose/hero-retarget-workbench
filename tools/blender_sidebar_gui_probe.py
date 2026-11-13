"""Screenshot the sidebar so the restyled panels can be looked at.

The installed addon shadows the package name at startup, so the checkout is
loaded by file location.

  blender --factory-startup --python tools/blender_sidebar_gui_probe.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
SPEC = importlib.util.spec_from_file_location(
    "dmf_sidebar_gui_probe",
    PACKAGE / "__init__.py",
    submodule_search_locations=[str(PACKAGE)],
)
assert SPEC is not None and SPEC.loader is not None
dmf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dmf
SPEC.loader.exec_module(dmf)

OUT = REPO / "artifacts" / "ui-pass" / "sidebar.png"


def view3d():
    window = bpy.context.window
    if window is None or window.screen is None:
        return None
    for area in window.screen.areas:
        if area.type == "VIEW_3D":
            return area
    return None


def setup() -> None:
    # Blender exposes no way to select a sidebar tab from a script, so the probe
    # registers the same panels under the already-selected Item tab. This is
    # probe-only: the shipped addon stays on its Deadlock tab.
    for cls in dmf.ui.CLASSES:
        cls.bl_category = "Item"
    dmf.register()
    settings = bpy.context.scene.dmf
    settings.build = "6861 Nov 09 2026"
    settings.status = "Hero extracted; import the skeleton, then fit your model."
    settings.status_kind = "INFO"
    settings.addon_name = "thicc_mayu_v3"
    area = view3d()
    if area is None:
        raise RuntimeError("no 3D viewport")
    space = area.spaces.active
    space.show_region_ui = True
    print("SIDEBAR tabs", [item for item in dir(space) if "categor" in item.lower()], flush=True)



def shoot() -> None:
    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    except Exception as error:
        print("SIDEBAR redraw failed", type(error).__name__, error, flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.screen.screenshot(filepath=str(OUT))
    print(f"SIDEBAR screenshot {OUT}", flush=True)
    print(f"SIDEBAR panels={len(dmf.ui.CLASSES)}", flush=True)
    bpy.ops.wm.quit_blender()


def bail() -> None:
    print("SIDEBAR timeout", flush=True)
    bpy.ops.wm.quit_blender()


try:
    setup()
except Exception as error:
    print("SIDEBAR setup failed", type(error).__name__, error, flush=True)
    bpy.ops.wm.quit_blender()
else:
    bpy.app.timers.register(shoot, first_interval=2.5)
    bpy.app.timers.register(bail, first_interval=25.0)
