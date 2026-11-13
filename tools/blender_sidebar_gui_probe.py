"""Screenshot the sidebar so the restyled panels can be looked at.

The installed addon shadows the package name at startup, so the checkout is
loaded by file location.

  blender --factory-startup --python tools/blender_sidebar_gui_probe.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
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

MODE_ENV = os.environ.get("DMF_PROBE_MODE", "rules").strip().lower()
OUT = REPO / "artifacts" / "ui-pass" / f"sidebar-{MODE_ENV}.png"


def view3d():
    window = bpy.context.window
    if window is None or window.screen is None:
        return None
    for area in window.screen.areas:
        if area.type == "VIEW_3D":
            return area
    return None


def rig(name: str, bones):
    """A tiny armature so the Skeleton page has a real map to show."""
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name, head, tail, parent in bones:
        edit = data.edit_bones.new(bone_name)
        edit.head = head
        edit.tail = tail
        if parent:
            edit.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)
    return obj


def setup() -> None:
    # Blender exposes no way to select a sidebar tab from a script, so the probe
    # registers the same panels under the already-selected Item tab. This is
    # probe-only: the shipped addon stays on its Deadlock tab.
    for cls in dmf.ui.CLASSES:
        cls.bl_category = "Item"
        if cls.bl_idname in KEEP_OPEN:
            # Open the page this render checks: a folded panel cannot be checked
            # for layout, and the shipped defaults stay as they are.
            cls.bl_options = set()
        else:
            # Fold everything else: one window height has to hold the page under
            # review, its editor and its list.
            cls.bl_options = {"DEFAULT_CLOSED"}
    dmf.register()
    settings = bpy.context.scene.dmf
    settings.addon_name = "thicc_mayu_v3"

    # Reproduce the state the owner photographed: a detected build with no S2V
    # CLI and no CSDK, so the status bubble shows the real wording at its real
    # length. The fixture is written inside the repository, not to a scratch
    # folder, so the render can be re-run and inspected later.
    fixture = Path(__file__).resolve().parents[1] / "artifacts" / "probes" / "sidebar-fixture" / "Deadlock"
    if fixture.exists():
        import shutil

        shutil.rmtree(fixture)
    (fixture / "game" / "citadel").mkdir(parents=True)
    (fixture / "game" / "citadel" / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
    (fixture / "game" / "citadel" / "pak01_dir.vpk").write_text("vpk", encoding="utf-8")
    (fixture / "game" / "citadel" / "steam.inf").write_text(
        "ClientVersion=6861\nVersionDate=Nov 09 2026\n", encoding="utf-8"
    )
    settings.deadlock_root = str(fixture)
    settings.s2v_cli = ""
    settings.csdk_root = ""
    bpy.ops.dmf.detect_paths()
    print(f"SIDEBAR status={settings.status!r} kind={settings.status_kind}", flush=True)

    # The Skeleton page renders its rule row and ref-pose controls from a real
    # rig pair, so the screenshot covers the new surface instead of an empty one.
    source = rig(
        "gold_ship_rig",
        [
            ("pelvis", (0.0, 0.0, 1.0), (0.0, 0.0, 1.2), None),
            ("elbow_L", (0.4, 0.0, 1.4), (0.8, 0.0, 1.4), "pelvis"),
            ("elbow_R", (-0.4, 0.0, 1.4), (-0.8, 0.0, 1.4), "pelvis"),
            ("shoulder_L", (0.1, 0.0, 1.45), (0.4, 0.0, 1.45), "pelvis"),
            ("shoulder_R", (-0.1, 0.0, 1.45), (-0.4, 0.0, 1.45), "pelvis"),
        ],
    )
    hero = rig(
        "shiv_body",
        [
            ("pelvis", (0.0, 0.0, 1.0), (0.0, 0.0, 1.2), None),
            ("arm_lower_L", (0.4, 0.0, 1.2), (0.6, 0.0, 0.9), "pelvis"),
            ("arm_lower_R", (-0.4, 0.0, 1.2), (-0.6, 0.0, 0.9), "pelvis"),
            ("arm_upper_L", (0.1, 0.0, 1.5), (0.3, 0.0, 1.35), "pelvis"),
            ("arm_upper_R", (-0.1, 0.0, 1.5), (-0.3, 0.0, 1.35), "pelvis"),
        ],
    )
    settings.target_armature = hero
    settings.custom_armature = source
    settings.custom_name = "Gold_Ship"
    dmf.workbench.scan_bone_map(settings)
    rows = {entry.source: entry for entry in settings.bone_map}
    rows["elbow_L"].state = "MAPPED"
    rows["elbow_L"].target = "arm_lower_L"
    shoulder_rule = settings.bone_rules.add()
    shoulder_rule.source = "shoulder"
    shoulder_rule.target = "arm_upper_L"
    shoulder_rule.side_aware = True
    shoulder_rule.state = "MAPPED"
    shoulder_rule.origin = "user"
    dmf.rules.fill(settings)
    settings.bone_rule_index = 0
    dmf.poseview.refresh(settings)
    settings.pose_preview = True
    print(
        f"SIDEBAR mirror={rows['elbow_R'].target!r} rules={len(settings.bone_rules)} "
        f"pose={settings.pose_stance!r} error={settings.pose_preview_error!r}",
        flush=True,
    )
    area = view3d()
    if area is None:
        raise RuntimeError("no 3D viewport")
    space = area.spaces.active
    space.show_region_ui = True
    print("SIDEBAR tabs", [item for item in dir(space) if "categor" in item.lower()], flush=True)



# Which pages this render keeps open. Set DMF_PROBE_MODE=skeleton to check the
# ref-pose section, rules (the default) to check the rule editor.
MODE = MODE_ENV
KEEP_OPEN = (
    {"DMF_PT_main", "DMF_PT_rules", "DMF_PT_animations"}
    if MODE != "skeleton"
    else {"DMF_PT_main", "DMF_PT_skeleton"}
)


def scroll_sidebar(steps: int = 40) -> None:
    """Wheel the sidebar down so the lower pages are actually in the frame.

    The render is one window tall; Skeleton sits under the Workbench card, and an
    unscrolled shot only proves its header exists.
    """
    window = bpy.context.window
    if window is None:
        return
    area = view3d()
    if area is None:
        return
    region = next((item for item in area.regions if item.type == "UI"), None)
    if region is None:
        return
    x = region.x + region.width // 2
    y = region.y + region.height // 2
    for _ in range(steps):
        try:
            window.event_simulate(type="WHEELDOWNMOUSE", value="PRESS", x=x, y=y)
        except Exception as error:  # pragma: no cover - GUI-only path
            print("SIDEBAR scroll failed", type(error).__name__, error, flush=True)
            return
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass
    print(f"SIDEBAR scrolled {steps} steps at {x},{y}", flush=True)


def shoot() -> None:
    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    except Exception as error:
        print("SIDEBAR redraw failed", type(error).__name__, error, flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    scroll_sidebar(10)
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
