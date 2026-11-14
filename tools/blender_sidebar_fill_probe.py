"""Measure the custom view's region layout, including hiding the WINDOW region.

A region's width is read-only from Python, so "the sidebar fills the view" has to
come from the area layout, not from setting a pixel width. This probe records the
regions before and after ``SCREEN_OT_region_toggle(region_type='WINDOW')`` and
quits, so the answer is measured rather than assumed.

Usage::

    blender --factory-startup --python tools/blender_sidebar_fill_probe.py
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "blender"))

report: dict[str, object] = {}


def regions(area) -> list[dict[str, object]]:
    return [
        {
            "type": region.type,
            "x": region.x,
            "y": region.y,
            "width": region.width,
            "height": region.height,
        }
        for region in area.regions
    ]


def main() -> int:
    import hero_retarget_workbench as addon

    report["registered"] = addon.register()
    window = bpy.context.window_manager.windows[0]
    area = max(window.screen.areas, key=lambda candidate: candidate.width)
    area.type = "CUSTOM"
    area.ui_type = "DMF_ST_workbench"
    space = area.spaces.active
    space.show_region_ui = True
    bpy.context.view_layer.update()
    report["area"] = {"width": area.width, "height": area.height}
    report["before"] = regions(area)

    try:
        with bpy.context.temp_override(window=window, area=area):
            result = bpy.ops.screen.region_toggle(region_type="WINDOW")
        report["toggle"] = str(result)
    except Exception as error:
        report["toggle_error"] = f"{type(error).__name__}: {error}"
    bpy.context.view_layer.update()
    report["after_toggle"] = regions(area)

    ui = next((region for region in area.regions if region.type == "UI"), None)
    try:
        with bpy.context.temp_override(window=window, area=area, region=ui):
            result = bpy.ops.screen.region_scale("EXEC_DEFAULT")
        report["scale"] = str(result)
    except Exception as error:
        report["scale_error"] = f"{type(error).__name__}: {error}"
    bpy.context.view_layer.update()
    report["after"] = regions(area)
    report["after_ui_visible"] = bool(getattr(space, "show_region_ui", False))
    out = REPO / "artifacts" / "receipts" / "sidebar-fill.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SIDEBARFILL " + json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 2
    bpy.ops.wm.quit_blender()
    sys.exit(code)
