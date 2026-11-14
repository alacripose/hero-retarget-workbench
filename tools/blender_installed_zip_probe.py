"""Install the built zip into an isolated profile and check the page surface.

The dev probe imports the addon from this repo, so it says nothing about the
artifact a user downloads. This one runs against the zip: it installs it through
Blender's own add-on installer into the profile named by ``BLENDER_USER_SCRIPTS``
(set by the caller), enables it, and reports which page surface registered, the
area switch, and the page panels.

Usage::

    BLENDER_USER_SCRIPTS=<repo>/artifacts/zip-profile/scripts \
    blender --factory-startup --python tools/blender_installed_zip_probe.py -- \
        --zip dist/hero_retarget_workbench-0.7.1.zip \
        --report artifacts/receipts/zip-install.json
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
MODULE = "hero_retarget_workbench"
SPACE_IDNAME = "DMF_ST_workbench"
PAGES_PANEL_IDNAME = "DMF_PT_space_pages"
HEADER_IDNAME = "DMF_HT_workbench"


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expect", choices=("editor", "sidebar"), default="")
    parser.add_argument("--screenshot", default="")
    return parser.parse_args(argv)


def main() -> int:
    args = _arguments()
    report: dict[str, object] = {
        "zip": str(Path(args.zip).resolve()),
        "blender": bpy.app.version_string,
        "user_scripts": os.environ.get("BLENDER_USER_SCRIPTS", ""),
        "checks": {},
        "failed": [],
    }

    def check(name: str, ok: bool, observed: object) -> None:
        report["checks"][name] = {"pass": bool(ok), "observed": observed}
        print(f"ZIPINSTALL {'PASS' if ok else 'FAIL'} {name}: {observed}", flush=True)
        if not ok:
            report["failed"].append(name)

    installed = bpy.ops.preferences.addon_install(filepath=str(Path(args.zip).resolve()))
    report["install"] = str(installed)
    check("install", installed == {"FINISHED"}, report["install"])

    enabled = bpy.ops.preferences.addon_enable(module=MODULE)
    check("enable", enabled == {"FINISHED"}, str(enabled))

    addon = sys.modules.get(MODULE) or importlib.import_module(MODULE)
    report["addon_file"] = getattr(addon, "__file__", "")
    report["surface"] = getattr(addon, "SURFACE", "")
    report["version"] = ".".join(str(part) for part in addon.bl_info["version"])
    check(
        "installed-copy",
        Path(report["addon_file"]).is_relative_to(Path(os.environ.get("BLENDER_USER_SCRIPTS", ""))),
        report["addon_file"],
    )

    panels = sorted(name for name in dir(bpy.types) if name.startswith("DMF_PT_"))
    spaces = [name for name in dir(bpy.types) if name == SPACE_IDNAME]
    expected = args.expect or ("editor" if spaces else "sidebar")
    report["expect"] = expected
    report["space_registered"] = bool(spaces)
    report["header_registered"] = HEADER_IDNAME in dir(bpy.types)
    report["panels"] = panels
    check("space-registered", bool(spaces) == (expected == "editor"), spaces or "not on this build")
    check("header-registered", report["header_registered"] == (expected == "editor"), HEADER_IDNAME in dir(bpy.types))
    check("pages-registered", bool(panels), len(panels))
    check("expected-surface", report["surface"] == expected, report["surface"])
    check(
        "surface-consistent",
        bool(spaces) == (report["surface"] == "editor"),
        {"space": bool(spaces), "surface": report["surface"]},
    )

    window = bpy.context.window
    area = next(
        (
            candidate
            for screen in (window.screen for window in bpy.context.window_manager.windows if window)
            for candidate in screen.areas
            if candidate.type in {"PROPERTIES", "VIEW_3D", "CUSTOM"}
        ),
        None,
    )
    report["area_found"] = area is not None
    if area is not None:
        before = str(area.type)
        with bpy.context.temp_override(window=window, area=area):
            switched = bpy.ops.dmf.open_workbench()
        report["area_before"] = before
        report["area_type"] = str(area.type)
        report["area_ui_type"] = str(getattr(area, "ui_type", ""))
        ui_types = [
            str(getattr(candidate, "ui_type", ""))
            for candidate in bpy.context.screen.areas
            if candidate.type == "CUSTOM"
        ]
        report["ui_types"] = ui_types
        if expected == "editor":
            report["pages_strip"] = PAGES_PANEL_IDNAME in dir(bpy.types)
            space = area.spaces.active
            check(
                "open-workbench",
                switched == {"FINISHED"}
                and SPACE_IDNAME in ui_types
                and bool(getattr(space, "show_region_ui", False))
                and report["pages_strip"],
                {
                    "result": str(switched),
                    "type": report["area_type"],
                    "ui_types": ui_types,
                    "sidebar": bool(getattr(space, "show_region_ui", False)),
                    "pages_panel": report["pages_strip"],
                },
            )
        else:
            space = area.spaces.active
            check(
                "open-workbench",
                switched == {"FINISHED"}
                and report["area_type"] == "VIEW_3D"
                and bool(getattr(space, "show_region_ui", False)),
                {
                    "result": str(switched),
                    "type": report["area_type"],
                    "sidebar": bool(getattr(space, "show_region_ui", False)),
                },
            )
        if args.screenshot:
            for _ in range(3):
                bpy.context.view_layer.update()
            bpy.ops.screen.screenshot(filepath=str(Path(args.screenshot).resolve()))
            report["screenshot"] = str(Path(args.screenshot).resolve())

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"ZIPINSTALL {'PASS' if not report['failed'] else 'FAIL'} {len(report['checks']) - len(report['failed'])}/{len(report['checks'])} checks", flush=True)
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
