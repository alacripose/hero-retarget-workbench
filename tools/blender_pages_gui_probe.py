"""Draw every Workbench page in a running Blender and screenshot the surface.

  blender --python tools/blender_pages_gui_probe.py -- --report artifacts/receipts/pages.json

The add-on has two possible homes for its pages, chosen at registration: its own
editor type (``DMF_ST_workbench``) on a build that can register a Space, or the
Properties editor tab on every other build. This probe reads which one this
Blender got, switches an area to it, draws every page against a real ``UILayout``
inside a real draw pass, and records every exception instead of letting the
renderer swallow it.

It also builds one chain into cloth first, so the Cloth page renders real rows,
and saves a screenshot of the surface that was used.

Without the extraction it reports SKIP and exits 0: CI has no game install.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
if str(REPO) in sys.path:
    sys.path.remove(str(REPO))
sys.path.insert(0, str(REPO))
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")
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
    / "shiv"
)

RESULT: dict[str, object] = {"checks": {}, "page_draws": [], "errors": []}
FAILED: list[str] = []


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", default=str(DEFAULT_EXTRACTION))
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "pages.json"))
    parser.add_argument("--log", default=str(REPO / "artifacts" / "receipts" / "pages-run.log"))
    parser.add_argument(
        "--screenshot",
        default=str(REPO / "artifacts" / "receipts" / "workbench-surface.png"),
    )
    return parser.parse_args(argv)


def _finish(code: int) -> None:
    report_path = Path(str(RESULT.get("receipt", "")))
    if report_path.name:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(RESULT, indent=2), encoding="utf-8")
    print(f"PAGES {'PASS' if code == 0 else 'FAIL'} {RESULT.get('summary', '')}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def _disable_installed_addon() -> list[str]:
    disabled = []
    for module in list(bpy.context.preferences.addons.keys()):
        if module == "dmf_pages_probe" or not module.endswith("hero_retarget_workbench"):
            continue
        try:
            bpy.ops.preferences.addon_disable(module=module)
            disabled.append(module)
        except RuntimeError:
            continue
    return disabled


def _enable_pulse() -> str:
    if hasattr(bpy.types.Scene, "vs") and hasattr(bpy.ops.import_scene, "kst_dmx"):
        return "already enabled"
    for module in PULSE_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except RuntimeError:
            continue
        if hasattr(bpy.ops.import_scene, "kst_dmx"):
            return module
    raise RuntimeError("pulse-src-ops-missing: enable the PulseSrcOps Blender extension first")


def _unshadow_forge() -> dict[str, object]:
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
        path = str(getattr(sys.modules[name], "__file__", "") or "")
        if "hero_retarget_workbench" in path:
            del sys.modules[name]
            dropped.append(name)
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))
    return {"path_entries": removed, "modules": dropped}


def _load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_pages_probe",
        PACKAGE / "__init__.py",
        submodule_search_locations=[str(PACKAGE)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_pages_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module



def _scan_log(path: Path, markers: tuple[str, ...]) -> list[str]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    found = []
    for index, line in enumerate(lines):
        if "Traceback (most recent call last)" in line:
            block = chr(10).join(lines[index : index + 40])
            if any(marker in block for marker in markers):
                found.append(lines[index : index + 6])
    return found


def _any_area():
    window = bpy.context.window
    if window is None or window.screen is None:
        return None, None
    for area in window.screen.areas:
        if area.type == "PROPERTIES":
            return window, area
    return window, next(iter(window.screen.areas), None)


def _region(area, kind: str):
    return next((item for item in area.regions if item.type == kind), None)


def _check(name: str, ok: bool, observed: object) -> None:
    RESULT["checks"][name] = {"pass": bool(ok), "observed": observed}
    print(f"PAGE {'PASS' if ok else 'FAIL'} {name}: {observed}", flush=True)
    if not ok:
        FAILED.append(name)


class _Shim:
    """What a panel draw actually touches: ``self.layout``."""

    def __init__(self, layout):
        self.layout = layout


def main() -> int:
    args = _arguments()
    # Blender writes a screenshot only to an absolute path; a relative one is
    # accepted by the operator and never lands on disk.
    args.screenshot = str(Path(args.screenshot).resolve())
    args.report = str(Path(args.report).resolve())
    RESULT["receipt"] = str(args.report)
    extraction = Path(args.extraction)
    body_dmx = next(iter(sorted(extraction.rglob("shiv_body.dmx"))), None)
    if body_dmx is None:
        RESULT["skipped"] = f"no shiv_body.dmx under {extraction}"
        RESULT["summary"] = "skipped (no extraction)"
        print(f"PAGES SKIP extraction not found: {extraction}", flush=True)
        _finish(0)

    RESULT["disabled_installed_addons"] = _disable_installed_addon()
    RESULT["pulse_src_ops"] = _enable_pulse()
    RESULT["unshadowed"] = _unshadow_forge()
    addon = _load_addon()
    ui = sys.modules["dmf_pages_probe.ui"]
    ui_props = sys.modules["dmf_pages_probe.ui_props"]
    ui_space = sys.modules["dmf_pages_probe.ui_space"]
    cloth_ops = sys.modules["dmf_pages_probe.cloth_ops"]
    surface = getattr(addon, "SURFACE", "sidebar")
    RESULT["surface"] = surface
    RESULT["blender"] = bpy.app.version_string
    RESULT["custom_space_supported"] = ui_space.custom_space_supported()
    _check(
        "surface-match",
        surface == ("editor" if ui_space.custom_space_supported() else "sidebar"),
        {"surface": surface, "supported": ui_space.custom_space_supported()},
    )

    root = getattr(
        bpy.types,
        "DMF_PT_space_main" if surface == "editor" else "DMF_PT_main",
        None,
    )
    _check(
        "surface-open-control",
        hasattr(bpy.ops.dmf, "open_workbench") and root is not None,
        {
            "operator": hasattr(bpy.ops.dmf, "open_workbench"),
            "root": getattr(root, "bl_idname", ""),
        },
    )

    settings = bpy.context.scene.dmf
    settings.body_dmx = str(body_dmx)
    bpy.ops.object.select_all(action="DESELECT")
    outcome = bpy.ops.dmf.import_hero()
    _check("hero-import", outcome == {"FINISHED"} and settings.target_armature is not None, str(outcome))
    # No rescan: the import scanned the chains and built their cloth; a rescan
    # here would clear the built rows this probe asserts on.
    _check("chains", len(settings.cloth_chains) > 0, len(settings.cloth_chains))
    # No manual build here: the import is expected to have left the cloth parts
    # built already, which is the symptom this probe exists to guard.
    built_rows = [
        {"chain": row.name, "mesh": getattr(row.target_mesh, "name", ""), "pin": row.pin_group}
        for row in settings.cloth_chains
        if row.target_mesh is not None
    ]
    RESULT["cloth_rows"] = built_rows
    _check(
        "import-built-cloth",
        any("jacket" in row["mesh"].lower() for row in built_rows)
        and any("hair" in row["mesh"].lower() for row in built_rows),
        built_rows,
    )
    settings.props_page = "CLOTH"

    prefix = "space" if surface == "editor" else "props"
    pages = [("root", getattr(bpy.types, f"DMF_PT_{prefix}_main").draw, "ALL")]
    for panel_idname, page in ui_props.PAGE_BY_ID.items():
        name = f"DMF_PT_{prefix}_{panel_idname[len('DMF_PT_'):]}"
        cls = getattr(bpy.types, name, None)
        if cls is not None:
            pages.append((name, cls.draw, page))
    RESULT["pages"] = sorted({page for _, _, page in pages})

    def host_draw(self, context):
        results = []
        for name, draw, page in pages:
            box = self.layout.box()
            box.label(text=f"{page}: {name}", icon="INFO")
            try:
                draw(_Shim(box), context)
                results.append({"page": page, "panel": name, "drew": True})
            except Exception as error:  # recorded, and the probe fails on it
                results.append(
                    {
                        "page": page,
                        "panel": name,
                        "drew": False,
                        "error": f"{type(error).__name__}: {error}",
                        "trace": traceback.format_exc(),
                    }
                )
        RESULT["page_draws"] = results

    attributes = {
        "bl_idname": "PROBE_PT_pages",
        "bl_label": "Workbench Draw Probe",
        "bl_region_type": "WINDOW",
        "bl_order": -100,
        "bl_options": set(),
        "draw": host_draw,
    }
    if surface == "editor":
        attributes["bl_space_type"] = "CUSTOM"
        attributes["bl_space_idname"] = ui_space.SPACE_IDNAME
    else:
        attributes["bl_space_type"] = "VIEW_3D"
        attributes["bl_region_type"] = "UI"
    bpy.utils.register_class(type("PROBE_PT_pages", (bpy.types.Panel,), attributes))

    window, area = _any_area()
    RESULT["area_found"] = area is not None
    if area is not None and surface == "editor":
        try:
            # The PR's custom space is a subtype of the CUSTOM host.
            area.type = "CUSTOM"
            area.ui_type = ui_space.SPACE_IDNAME
            RESULT["area_type"] = str(area.type)
            RESULT["area_ui_type"] = str(getattr(area, "ui_type", ""))
        except Exception as error:
            RESULT["area_switch_error"] = f"{type(error).__name__}: {error}"
    elif area is not None:
        space = area.spaces.active
        if hasattr(space, "context"):
            try:
                space.context = "SCENE"
            except (TypeError, AttributeError) as error:
                RESULT["context_error"] = f"{type(error).__name__}: {error}"
        RESULT["area_type"] = str(area.type)
    _check(
        "surface-active",
        area is not None
        and (
            surface != "editor"
            or str(getattr(area, "ui_type", "")) == ui_space.SPACE_IDNAME
        ),
        {
            "requested": surface,
            "area_type": RESULT.get("area_type"),
            "area_ui_type": RESULT.get("area_ui_type"),
            "error": RESULT.get("area_switch_error", ""),
        },
    )

    state = {"tries": 0}
    max_tries = 40

    def finish():
        draws = RESULT.get("page_draws") or []
        errors = [entry for entry in draws if not entry.get("drew")]
        RESULT["draw_errors"] = errors
        _check("pages-drawn", len(draws) == len(pages), f"{len(draws)}/{len(pages)}")
        _check(
            "draws-without-exception",
            not errors,
            [entry["panel"] + ": " + entry.get("error", "") for entry in errors],
        )
        log_path = Path(args.log)
        tracebacks = _scan_log(log_path, ("hero_retarget_workbench", "dmf_cloth_probe", "dmf_pages_probe"))
        RESULT["log"] = {"path": str(log_path), "scanned": log_path.is_file(), "addon_tracebacks": tracebacks}
        _check("log-without-addon-exceptions", not tracebacks, tracebacks or "clean")
        # Point the page at a cloth part so the shot shows a built jacket/hair row.
        for index, row in enumerate(settings.cloth_chains):
            if row.target_mesh is not None and "hair" in row.target_mesh.name.lower():
                settings.cloth_index = index
                break
        bpy.context.view_layer.update()
        Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
        RESULT["summary"] = f"{surface} surface, {len(draws)} page draws, {len(errors)} exceptions"
        try:
            # The screenshot operator runs on the next event loop pass, so the
            # process must stay alive until the file lands; exit is deferred.
            bpy.ops.screen.screenshot(filepath=str(args.screenshot))
            RESULT["screenshot_requested"] = str(args.screenshot)
        except Exception as error:
            RESULT["screenshot_error"] = f"{type(error).__name__}: {error}"
        pending["code"] = 0 if not FAILED else 1
        bpy.app.timers.register(settle, first_interval=0.2)
        return None

    def step():
        state["tries"] += 1
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception as error:
            RESULT.setdefault("redraw_errors", []).append(f"{type(error).__name__}: {error}")
        draws = RESULT.get("page_draws") or []
        if len(draws) >= len(pages):
            return finish()
        if state["tries"] >= max_tries:
            RESULT["summary"] = f"only {len(draws)}/{len(pages)} page draws executed"
            _finish(1)
        if window is not None and area is not None:
            region = _region(area, "WINDOW")
            if region is not None:
                try:
                    window.event_simulate(
                        type="WHEELDOWNMOUSE",
                        value="PRESS",
                        x=region.x + region.width // 2,
                        y=region.y + region.height // 2,
                    )
                except Exception:
                    pass
        return 0.4

    pending = {"code": 0, "tries": 0}

    def settle():
        pending["tries"] += 1
        target = Path(args.screenshot)
        print(f"PAGE screenshot {args.screenshot} ({RESULT.get('screenshot_bytes', 0)} bytes)", flush=True)
        if target.is_file() and target.stat().st_size > 0:
            RESULT["screenshot"] = str(args.screenshot)
            RESULT["screenshot_bytes"] = target.stat().st_size
            print(f"PAGE screenshot saved: {RESULT['screenshot_bytes']} bytes", flush=True)
            _finish(pending["code"])
            return None
        if pending["tries"] >= 40:
            RESULT["screenshot_error"] = "screenshot never appeared on disk"
            _finish(1)
            return None
        return 0.2

    bpy.app.timers.register(step, first_interval=2.0)
    return 0


if __name__ == "__main__":
    main()
