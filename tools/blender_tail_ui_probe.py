"""Draw the Tails page against a real Blender UI layout.

  blender --python tools/blender_tail_ui_probe.py -- --report artifacts/receipts/tail-ui.json

The probe imports the Familiar extraction, scans its tail sources, then registers a
temporary sidebar panel whose draw calls ``ui._draw_tail``. It records the draw
exception instead of letting Blender swallow it. A headless run still exercises the
layout code, but not the final pixels; the screenshot is requested as evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
DEFAULT_EXTRACTION = (
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
    / "familiar"
)
RESULT: dict = {"checks": {}, "failed": []}
STATE = {"drawn": False, "error": "", "tries": 0}


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", default=str(DEFAULT_EXTRACTION))
    parser.add_argument("--live-cache", default=str(REPO / "artifacts" / "tail-skeletons"))
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "tail-ui.json"))
    parser.add_argument("--screenshot", default=str(REPO / "artifacts" / "receipts" / "tail-ui.png"))
    return parser.parse_args(argv)


def disable_installed() -> list[str]:
    disabled = []
    for module in list(bpy.context.preferences.addons.keys()):
        if module.endswith("hero_retarget_workbench"):
            try:
                bpy.ops.preferences.addon_disable(module=module)
                disabled.append(module)
            except RuntimeError:
                continue
    return disabled


def unshadow_forge() -> dict:
    removed = []
    for entry in list(sys.path):
        try:
            candidate = Path(entry)
        except (TypeError, ValueError):
            continue
        if candidate.name == "hero_retarget_workbench" or (
            candidate / "hero_retarget_workbench" / "forge"
        ).is_dir():
            sys.path.remove(entry)
            removed.append(entry)
    dropped = []
    for name in [name for name in sys.modules if name == "forge" or name.startswith("forge.")]:
        if "hero_retarget_workbench" in str(getattr(sys.modules[name], "__file__", "") or ""):
            del sys.modules[name]
            dropped.append(name)
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))
    return {"path_entries": removed, "modules": dropped}


def load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_tail_ui_probe",
        PACKAGE / "__init__.py",
        submodule_search_locations=[str(PACKAGE)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_tail_ui_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def check(name: str, ok: bool, observed) -> None:
    RESULT["checks"][name] = {"pass": bool(ok), "observed": observed}
    if not ok:
        RESULT["failed"].append(name)
    print(f"TAILUI {'PASS' if ok else 'FAIL'} {name}: {observed}", flush=True)


def finish(code: int | None = None) -> None:
    if code is None:
        code = 0 if not RESULT["failed"] else 1
    RESULT["summary"] = (
        f"{sum(1 for item in RESULT['checks'].values() if item['pass'])}/{len(RESULT['checks'])} checks"
    )
    target = Path(RESULT["report"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(RESULT, indent=2), encoding="utf-8")
    print(f"TAILUI FINISH {RESULT['summary']} {target}", flush=True)
    bpy.ops.wm.quit_blender()


def main() -> int:
    args = arguments()
    RESULT["report"] = str(Path(args.report).resolve())
    RESULT["screenshot"] = str(Path(args.screenshot).resolve())
    extraction = Path(args.extraction)
    body = next(iter(sorted(extraction.rglob("*body8.dmx"))), None)
    if body is None:
        body = next(iter(sorted(extraction.rglob("*body.dmx"))), None)
    if body is None:
        RESULT["skipped"] = str(extraction)
        finish(0)
        return 0
    RESULT["extraction"] = str(extraction)
    RESULT["body"] = str(body)
    RESULT["disabled_installed_addons"] = disable_installed()
    RESULT["unshadowed"] = unshadow_forge()
    addon = load_addon()
    import addon_utils

    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    try:
        bpy.context.preferences.view.show_splash = False
    except Exception:
        pass
    settings = bpy.context.scene.dmf
    settings.project_root = str(REPO / "artifacts" / "tail-ui-workspace")
    settings.extraction_dir = str(extraction)
    settings.body_dmx = str(body)
    result = bpy.ops.dmf.import_hero()
    check("hero-import", result == {"FINISHED"}, str(result))
    tailops = sys.modules["dmf_tail_ui_probe.tailops"]
    count = tailops.discover(settings)
    check("tail-options", count > 0, {"count": count, "rows": len(settings.tail_options)})
    check("previews", all(row.preview and Path(row.preview).is_file() for row in settings.tail_options), [
        row.preview for row in settings.tail_options
    ])
    loaded = tailops.load_option(settings, 0)
    check("tail-load", settings.tail_armature is not None and settings.tail_bones, loaded)
    live_cache = Path(args.live_cache)
    if live_cache.is_dir():
        from forge import live

        live_files = live.tail_skeleton_files(live_cache)
        live_count = tailops.discover(settings, live_files=live_files)
        live_rows = [index for index, option in enumerate(settings.tail_options) if option.source == "LIVE"]
        check("live-options", bool(live_rows), {"count": live_count, "live": len(live_rows)})
        viper = next(
            (index for index, option in enumerate(settings.tail_options) if "viper" in option.label.lower()),
            live_rows[0] if live_rows else -1,
        )
        live_loaded = tailops.load_option(settings, viper)
        check(
            "live-tail-load",
            settings.tail_armature is not None and bool(settings.tail_armature.data.bones),
            live_loaded,
        )
    ui = sys.modules["dmf_tail_ui_probe.ui"]

    def host_draw(self, context):
        try:
            ui._draw_tail(self.layout, settings)
            STATE["drawn"] = True
        except Exception as error:
            STATE["error"] = f"{type(error).__name__}: {error}"
            RESULT["trace"] = traceback.format_exc()

    panel = type(
        "PROBE_PT_tail",
        (bpy.types.Panel,),
        {
            "bl_idname": "PROBE_PT_tail",
            "bl_label": "Tail UI Probe",
            "bl_space_type": "VIEW_3D",
            "bl_region_type": "UI",
            "bl_category": "Deadlock",
            "draw": host_draw,
        },
    )
    bpy.utils.register_class(panel)
    window = bpy.context.window
    if window is None:
        check("window", False, "no window for a real draw")
        finish()
        return 0
    try:
        # The startup splash sits over the sidebar in a screenshot and is not an
        # Area, so dismiss it before the probe starts redrawing.
        window.event_simulate(type="ESC", value="PRESS")
    except Exception:
        pass
    area = next((item for item in window.screen.areas if item.type == "VIEW_3D"), None)
    if area is None:
        area = next(iter(window.screen.areas), None)
        area.type = "VIEW_3D"
    space = area.spaces.active
    if hasattr(space, "show_region_ui"):
        space.show_region_ui = True
    check("window", area is not None, {"type": str(getattr(area, "type", "")), "show_ui": bool(getattr(space, "show_region_ui", False))})

    def step():
        STATE["tries"] += 1
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception as error:
            RESULT.setdefault("redraw_errors", []).append(f"{type(error).__name__}: {error}")
        if STATE["drawn"] or STATE["error"]:
            check("tail-draw", STATE["drawn"] and not STATE["error"], STATE["error"] or "drawn")
            try:
                bpy.ops.screen.screenshot(filepath=RESULT["screenshot"])
            except Exception as error:
                RESULT["screenshot_error"] = f"{type(error).__name__}: {error}"
            bpy.app.timers.register(settle, first_interval=0.3)
            return None
        if STATE["tries"] >= 40:
            check("tail-draw", False, "panel draw never executed")
            finish()
            return None
        return 0.3

    def settle():
        target = Path(RESULT["screenshot"])
        if target.is_file() and target.stat().st_size:
            RESULT["screenshot_bytes"] = target.stat().st_size
            finish()
            return None
        if STATE.setdefault("settle_tries", 0) >= 30:
            RESULT["screenshot_error"] = "screenshot never appeared"
            finish()
            return None
        STATE["settle_tries"] = STATE.get("settle_tries", 0) + 1
        return 0.2

    bpy.app.timers.register(step, first_interval=2.0)
    return 0


if __name__ == "__main__":
    main()
