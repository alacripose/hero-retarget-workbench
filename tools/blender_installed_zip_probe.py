"""Install the built zip into an isolated profile and check the page surface.

The dev probes import the addon from this repo, so they say nothing about the
artifact a user downloads. This one runs against the zip: it installs it through
Blender's own add-on installer into the profile named by ``BLENDER_USER_SCRIPTS``
(set by the caller), enables it, and checks the surface, the sidebar pages and the
installed-copy path.

The page surface is the custom view's own N sidebar: every page is a category in
the UI region and the page's panels are what that tab shows. There is no
WINDOW-region page copy and no page selector, so the probe checks the panels'
region and category rather than a page property.

Usage::

    BLENDER_USER_SCRIPTS=<repo>/artifacts/zip-profile/scripts \\
    blender --factory-startup --python tools/blender_installed_zip_probe.py -- \\
        --zip dist/hero_retarget_workbench-0.8.16.zip \\
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
HEADER_IDNAME = "DMF_HT_workbench"
ROOT_IDNAME = "DMF_PT_space_main"


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expect", choices=("editor", "sidebar"), default="")
    parser.add_argument("--screenshot", default="")
    parser.add_argument("--page", default="", help="page to show before the screenshot")
    parser.add_argument(
        "--demo-job",
        action="store_true",
        help="draw a representative running job so the bar and log are visible",
    )
    return parser.parse_args(argv)


def _page_labels() -> dict[str, str]:
    module = sys.modules.get(MODULE)
    pages = getattr(getattr(module, "ui_props", None), "PAGES", ())
    return {page: page.replace("_", " ").title() for page in pages}


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
        Path(report["addon_file"]).is_relative_to(
            Path(os.environ.get("BLENDER_USER_SCRIPTS", ""))
        ),
        report["addon_file"],
    )

    # The self-heal must not fire on a current build: 0.8.16 left it looking for
    # the removed tab class, so every session re-registered the editor.
    guard = getattr(addon, "_stale_ui_check", None)
    guard_attempts = getattr(addon, "_STALE_ATTEMPTS", -1)
    if guard is not None:
        guard()
    report["guard_attempts"] = getattr(addon, "_STALE_ATTEMPTS", -1)
    check(
        "stale-guard-quiet",
        guard is not None and report["guard_attempts"] == 0,
        {"before": guard_attempts, "after": report["guard_attempts"]},
    )

    spaces = [name for name in dir(bpy.types) if name == SPACE_IDNAME]
    expected = args.expect or ("editor" if spaces else "sidebar")
    report["expect"] = expected
    report["space_registered"] = bool(spaces)
    report["header_registered"] = HEADER_IDNAME in dir(bpy.types)
    check("space-registered", bool(spaces) == (expected == "editor"), spaces or "not on this build")
    check("header-registered", report["header_registered"] == (expected == "editor"), HEADER_IDNAME in dir(bpy.types))
    check("expected-surface", report["surface"] == expected, report["surface"])
    check(
        "surface-consistent",
        bool(spaces) == (report["surface"] == "editor"),
        {"space": bool(spaces), "surface": report["surface"]},
    )

    window = bpy.context.window
    candidates = [
        candidate
        for screen in (candidate.screen for candidate in bpy.context.window_manager.windows if candidate)
        for candidate in screen.areas
        if candidate.type in {"PROPERTIES", "VIEW_3D", "CUSTOM"}
    ]
    area = max(candidates, key=lambda candidate: candidate.width, default=None)
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
        space = area.spaces.active
        if expected == "editor":
            labels = _page_labels()
            pages: dict[str, object] = {}
            for page, label in labels.items():
                cls = getattr(bpy.types, f"DMF_PT_space_{page.lower()}", None)
                pages[label] = None if cls is None else {
                    "region": str(getattr(cls, "bl_region_type", "")),
                    "category": str(getattr(cls, "bl_category", "")),
                }
            report["pages"] = pages
            check(
                "open-workbench",
                switched == {"FINISHED"}
                and SPACE_IDNAME in ui_types
                and not bool(getattr(space, "show_region_ui", True)),
                {
                    "result": str(switched),
                    "type": report["area_type"],
                    "ui_types": ui_types,
                    "sidebar": bool(getattr(space, "show_region_ui", False)),
                },
            )
            check(
                "pages-fill-the-window",
                bool(pages)
                and all(
                    entry and entry["region"] == "WINDOW"
                    for entry in pages.values()
                ),
                pages,
            )
            check(
                "no-window-page-root",
                ROOT_IDNAME not in dir(bpy.types),
                ROOT_IDNAME if ROOT_IDNAME in dir(bpy.types) else "not registered",
            )
            with bpy.context.temp_override(window=window, area=area):
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
            space_module = getattr(sys.modules.get(MODULE), "ui_space", None)
            if space_module is not None:
                space_module._ensure_sidebar()
            check(
                "sidebar-stays-closed",
                space.show_region_ui is False,
                "opened" if space.show_region_ui else "closed",
            )
            if args.page:
                bpy.context.scene.dmf.props_page = args.page
            if args.demo_job:
                settings = bpy.context.scene.dmf
                settings.job_running = True
                settings.job_state = "RUNNING"
                settings.job_label = "Scanning old mods"
                settings.job_message = "citadel_addons: 14 found"
                settings.job_progress = 0.42
                settings.job_log = (
                    "Scanning old mods: starting\n"
                    "scanning 3 folders\n"
                    "citadel_addons: 14 found"
                )
            with bpy.context.temp_override(window=window, area=area):
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
        else:
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
        report["regions"] = [
            {
                "type": region.type,
                "x": region.x,
                "y": region.y,
                "width": region.width,
                "height": region.height,
            }
            for region in area.regions
        ]
        report["space_region_flags"] = {
            name: getattr(space, name, None)
            for name in dir(space)
            if "show_region" in name
        }
        report["page"] = str(bpy.context.scene.dmf.props_page)
        if args.screenshot:
            for _ in range(3):
                bpy.context.view_layer.update()
            bpy.ops.screen.screenshot(filepath=str(Path(args.screenshot).resolve()))
            report["screenshot"] = str(Path(args.screenshot).resolve())

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"ZIPINSTALL {'PASS' if not report['failed'] else 'FAIL'} "
        f"{len(report['checks']) - len(report['failed'])}/{len(report['checks'])} checks",
        flush=True,
    )
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
