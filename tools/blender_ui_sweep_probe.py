"""Capture every Workbench page in the add-on's own editor surface.

  blender --window-geometry 0 0 960 1000 --factory-startup \
      --enable-event-simulate --python tools/blender_ui_sweep_probe.py -- \
      --screenshots artifacts/ui-pass/pages

The script registers the add-on from this checkout, switches a real area to the
custom editor, then walks each page with screenshot requests. It is the wide
surface check for the HIG sweep; `blender_pages_gui_probe.py` remains the draw
exception probe and does not depend on this file.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
if str(REPO) in sys.path:
    sys.path.remove(str(REPO))
sys.path.insert(0, str(REPO))

RESULT: dict[str, object] = {"pages": [], "errors": []}


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", default=str(REPO / "artifacts" / "ui-pass" / "pages"))
    parser.add_argument("--page", default="")
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "ui-pages.json"))
    return parser.parse_args(argv)


def _disable_installed() -> list[str]:
    disabled = []
    for module in list(bpy.context.preferences.addons.keys()):
        if not module.endswith("hero_retarget_workbench"):
            continue
        try:
            bpy.ops.preferences.addon_disable(module=module)
            disabled.append(module)
        except RuntimeError:
            pass
    return disabled


def _load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_ui_sweep",
        PACKAGE / "__init__.py",
        submodule_search_locations=[str(PACKAGE)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _window():
    return bpy.context.window


def _area():
    window = _window()
    if window is None or window.screen is None:
        return None
    return next((area for area in window.screen.areas if area.type == "VIEW_3D"), None)


def _seed(dmf, settings) -> None:
    settings.build = "6861 Nov 09 2026"
    settings.deadlock_root = r"D:\SteamLibrary\steamapps\common\Deadlock"
    settings.s2v_cli = r"<home>\Downloads\cli-windows-x64\Source2Viewer-CLI.exe"
    settings.csdk_root = r"<home>\Downloads\Reduced_CSDK_13"
    try:
        from types import SimpleNamespace

        dmf.properties.set_model_items(
            [
                SimpleNamespace(
                    slug="artists_gesture_paper",
                    title="Artists Gesture Paper",
                    model_path="models/heroes_wip/artists/gesture_paper.vmdl_c",
                )
            ]
        )
        dmf.ui.heropick.refresh(settings)
    except Exception as error:
        RESULT.setdefault("errors", []).append(f"seed: {type(error).__name__}: {error}")


def main() -> int:
    args = _arguments()
    out_dir = Path(args.screenshots).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    RESULT["disabled"] = _disable_installed()
    dmf = _load_addon()
    ui_props = sys.modules["dmf_ui_sweep.ui_props"]
    ui_space = sys.modules["dmf_ui_sweep.ui_space"]
    settings = bpy.context.scene.dmf
    _seed(dmf, settings)
    pages = [args.page.upper()] if args.page else list(ui_props.PAGES)
    pages = [page for page in pages if page in ui_props.PAGES]
    RESULT["pages"] = pages
    RESULT["surface"] = getattr(dmf, "SURFACE", "")
    RESULT["custom_space_supported"] = ui_space.custom_space_supported()

    area = _area()
    if area is None:
        RESULT["errors"].append("no View3D area")
        _write(args)
        return 1
    try:
        with bpy.context.temp_override(area=area):
            bpy.ops.screen.screen_full_area(use_hide_panels=False)
        area = _area()
    except Exception as error:
        RESULT["errors"].append(f"fullscreen: {type(error).__name__}: {error}")
    if area is None:
        RESULT["errors"].append("no View3D area after fullscreen")
        _write(args)
        return 1
    try:
        area.type = "CUSTOM"
        area.ui_type = ui_space.SPACE_IDNAME
        RESULT["area_type"] = str(area.type)
        RESULT["area_ui_type"] = str(getattr(area, "ui_type", ""))
    except Exception as error:
        RESULT["errors"].append(f"switch: {type(error).__name__}: {error}")
        _write(args)
        return 1

    state = {"index": 0, "tries": 0, "page": ""}

    def capture() -> float | None:
        if state["index"] >= len(pages):
            _write(args)
            bpy.ops.wm.quit_blender()
            return None
        page = pages[state["index"]]
        state["page"] = page
        settings.props_page = page
        if area is not None:
            area.tag_redraw()
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
        except Exception as error:
            RESULT.setdefault("errors", []).append(f"redraw {page}: {type(error).__name__}: {error}")
        path = out_dir / f"{page.lower()}.png"
        try:
            bpy.ops.screen.screenshot(filepath=str(path))
            RESULT.setdefault("shots", []).append({"page": page, "path": str(path)})
        except Exception as error:
            RESULT.setdefault("errors", []).append(f"shot {page}: {type(error).__name__}: {error}")
        state["index"] += 1
        state["tries"] = 0
        bpy.app.timers.register(_wait_for_shot, first_interval=0.4)
        return None

    def _wait_for_shot() -> float | None:
        if state["index"] == 0:
            bpy.app.timers.register(capture, first_interval=0.1)
            return None
        previous = pages[state["index"] - 1]
        path = out_dir / f"{previous.lower()}.png"
        if path.is_file() and path.stat().st_size > 0:
            bpy.app.timers.register(capture, first_interval=0.15)
            return None
        state["tries"] += 1
        if state["tries"] > 30:
            RESULT.setdefault("errors", []).append(f"no screenshot for {previous}")
            bpy.app.timers.register(capture, first_interval=0.1)
            return None
        return 0.2

    # The factory splash sits over the first frame and would be in every shot.
    # Close it once, then let the page walk start.
    try:
        bpy.context.preferences.view.show_splash = False
    except Exception:
        pass

    def begin() -> None:
        window = _window()
        if window is not None:
            try:
                window.event_simulate(type="ESC", value="PRESS")
                window.event_simulate(type="ESC", value="RELEASE")
            except Exception:
                pass
        bpy.app.timers.register(capture, first_interval=1.0)

    bpy.app.timers.register(begin, first_interval=1.2)
    return 0


def _write(args) -> None:
    import json

    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(RESULT, indent=2), encoding="utf-8")
    print(f"UI SWEEP {len(RESULT.get('shots', []))}/{len(RESULT.get('pages', []))} pages", flush=True)


if __name__ == "__main__":
    code = main()
    if code:
        _write(_arguments())
        os._exit(code)
