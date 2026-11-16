"""Exercise the Mods collection on real Blender data, then screenshot it.

  blender --factory-startup --python tools/blender_mods_gui_probe.py

The probe builds a temporary addon folder, a VPK and a standalone blend, scans
them through the real operator, checks the typed lists and contents, creates a
Blender project from the VPK, and leaves the sidebar on the Mods page for a
screenshot. It forces the sidebar surface so the screenshot exercises the same
panel classes released builds use, not the PR-only editor mirrors.
"""
from __future__ import annotations

import importlib.util
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
SPEC = importlib.util.spec_from_file_location(
    "dmf_mods_gui_probe",
    PACKAGE / "__init__.py",
    submodule_search_locations=[str(PACKAGE)],
)
assert SPEC is not None and SPEC.loader is not None
dmf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dmf
SPEC.loader.exec_module(dmf)

OUT = REPO / "artifacts" / "ui-pass" / "mods-collection.png"
TOP = REPO / "artifacts" / "ui-pass" / "mods-scan-folders.png"
MODELDOC = """[
\t{
\t\t"m_keyValues"
\t\t{
\t\t\t{
\t\t\t\t_class = "Softbody"
\t\t\t}
\t\t\t{
\t\t\t\t_class = "RenderMeshList"
\t\t\t}
\t\t\t{
\t\t\t\t_class = "PhysicsJointList"
\t\t\t}
\t\t}
\t}
]
"""


def build_vpk(path: Path, entries: list[tuple[str, str]]) -> Path:
    tree = bytearray()

    def cstring(value: str) -> None:
        tree.extend(value.encode())
        tree.append(0)

    groups: dict[str, dict[str, list[str]]] = {}
    for directory, name in entries:
        stem, extension = name.rsplit(".", 1)
        groups.setdefault(extension, {}).setdefault(directory, []).append(stem)
    for extension, directories in groups.items():
        cstring(extension)
        for directory, stems in directories.items():
            cstring(directory)
            for stem in stems:
                cstring(stem)
                tree.extend(struct.pack("<IHHII", 0, 0, 0x7FFF, 0, 0))
                tree.extend(struct.pack("<H", 0xFFFF))
            cstring("")
        cstring("")
    cstring("")
    header = struct.pack("<III", 0x55AA1234, 2, len(tree))
    header += struct.pack("<IIII", 0, 0, 0, 0)
    path.write_bytes(header + bytes(tree))
    return path


def make_fixture(root: Path) -> Path:
    folder = root / "content" / "citadel_addons" / "old_folder"
    model = folder / "models" / "heroes_staging" / "haze" / "haze.vmdl"
    model.parent.mkdir(parents=True)
    model.write_text(MODELDOC, encoding="utf-8")
    (folder / "materials" / "haze").mkdir(parents=True)
    (folder / "materials" / "haze" / "haze.vmat").write_text("// material\n", encoding="utf-8")
    (folder / "clips").mkdir()
    (folder / "clips" / "haze_idle.vnmclip").write_bytes(b"clip")
    (folder / "source.blend").write_bytes(b"BLENDER")
    build_vpk(
        root / "haze_old.vpk",
        [
            ("models/heroes_staging/haze/", "haze.vmdl_c"),
            ("materials/haze/", "haze.vmat_c"),
            ("clips/", "haze_idle.vnmclip_c"),
        ],
    )
    (root / "standalone.blend").write_bytes(b"BLENDER")
    return root


def settle_scan() -> None:
    while dmf.jobs.is_running():
        active = dmf.jobs.active()
        if active is not None:
            active._tick()
        time.sleep(0.01)


def check(name: str, ok: bool, observed: object) -> None:
    print(f"MODS {'PASS' if ok else 'FAIL'} {name}: {observed}", flush=True)
    if not ok:
        raise RuntimeError(f"{name}: {observed}")


def sidebar() -> None:
    # Only the page under review is shown, so the screenshot is not a column of
    # folded page headers with the Mods contents below the fold.
    for cls in (*dmf.ui.CLASSES, *dmf.ui_mods.CLASSES):
        cls.bl_category = "Item" if cls.bl_idname == "DMF_PT_mods" else "DMF probe hidden"
        cls.bl_options = set()
    dmf.ui_mods.DMF_PT_mods.bl_parent_id = ""
    dmf.ui_mods.DMF_PT_mods.bl_order = -10


def run() -> None:
    # The PR editor surface is tested by the pages probe; this screenshot is the
    # released-build sidebar, so skip custom space registration deliberately.
    dmf.ui_space.custom_space_supported = lambda: False
    sidebar()
    dmf.register()
    settings = bpy.context.scene.dmf
    temp = Path(tempfile.mkdtemp(prefix="dmf-mods-probe-"))
    root = make_fixture(temp)
    # The probe loads the checkout addon directly, so the scan needs the checkout
    # root to import forge. The project itself is created under the temp workspace.
    settings.project_root = str(REPO)
    settings.mod_report = str(temp / "old-mods.json")
    settings.scan_roots.add().path = str(root)
    settings.scan_root_index = 0
    settings.scan_since = "2024-01-01"
    settings.scan_until = ""

    result = bpy.ops.dmf.scan_mods()
    check("scan-started", result == {"FINISHED"}, result)
    settle_scan()
    check("scan-count", settings.mods_scanned == 3, settings.mods_scanned)
    kinds = sorted(row.kind for row in settings.mods)
    check("typed-records", kinds == ["addon", "blend", "vpk"], kinds)
    check("visible-all", len(settings.mod_rows) == 3, len(settings.mod_rows))
    settings.mod_filter = "FOLDER"
    check("visible-folders", len(settings.mod_rows) == 1, len(settings.mod_rows))
    settings.mod_filter = "VPK"
    check("visible-vpks", len(settings.mod_rows) == 1, len(settings.mod_rows))
    settings.mod_filter = "BLEND"
    check("visible-blends", len(settings.mod_rows) == 1, len(settings.mod_rows))
    settings.mod_filter = "ALL"

    folder_index = next(i for i, row in enumerate(settings.mod_rows) if row.kind == "addon")
    settings.mod_index = folder_index
    categories = {row.category for row in settings.mod_contents}
    check("contents-typed", categories == {"models", "materials", "clips", "blends"}, categories)
    check("contents-files", len(settings.mod_contents) == 4, len(settings.mod_contents))
    settings.mod_content_filter = "MODELS"
    check("contents-filter", len(settings.mod_content_rows) == 1, len(settings.mod_content_rows))
    settings.mod_content_filter = "ALL"

    vpk_index = next(i for i, row in enumerate(settings.mod_rows) if row.kind == "vpk")
    settings.mod_index = vpk_index
    settings.mod_content_filter = "ALL"
    settings.project_root = str(temp / "workspace")
    result = bpy.ops.dmf.create_mod_project()
    check("project-created", result == {"FINISHED"} and Path(settings.project_file).is_file(), settings.project_file)
    check("project-root", Path(settings.project_root).is_dir(), settings.project_root)
    check("project-under-workspace", Path(settings.project_file).is_relative_to(temp), settings.project_file)

    settings.mod_filter = "ALL"
    bpy.context.preferences.view.show_splash = False
    window = bpy.context.window
    if window is not None and window.screen is not None:
        area = next((item for item in window.screen.areas if item.type == "VIEW_3D"), None)
        if area is not None:
            area.spaces.active.show_region_ui = True
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    print(f"MODS project={settings.project_file}", flush=True)
    print(f"MODS note={settings.mod_note}", flush=True)


def scroll_sidebar(steps: int = 18) -> None:
    window = bpy.context.window
    if window is None or window.screen is None:
        return
    area = next((item for item in window.screen.areas if item.type == "VIEW_3D"), None)
    if area is None:
        return
    region = next((item for item in area.regions if item.type == "UI"), None)
    if region is None:
        return
    x = region.x + region.width // 2
    y = region.y + region.height // 2
    for _ in range(steps):
        window.event_simulate(type="WHEELDOWNMOUSE", value="PRESS", x=x, y=y)
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)


def shoot() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.screen.screenshot(filepath=str(TOP))
    scroll_sidebar()
    bpy.app.timers.register(capture, first_interval=0.6)


def capture() -> None:
    bpy.ops.screen.screenshot(filepath=str(OUT))
    print(f"MODS screenshot {OUT}", flush=True)
    print(f"MODS scan screenshot {TOP}", flush=True)
    bpy.ops.wm.quit_blender()


try:
    run()
except Exception as error:
    print(f"MODS FAIL {type(error).__name__}: {error}", flush=True)
    bpy.ops.wm.quit_blender()
else:
    bpy.app.timers.register(shoot, first_interval=2.5)
    bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender(), first_interval=20.0)
