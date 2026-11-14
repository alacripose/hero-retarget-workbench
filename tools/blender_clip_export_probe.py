"""Headless probe for writing an imported clip action back out as animation DMX.

  blender -b --python tools/blender_clip_export_probe.py -- \
    --report artifacts/receipts/clip-export.json

This probe needs PulseSrcOps, so it runs with the owner's preferences instead of
``--factory-startup``: the extension is enabled first and the addon is loaded from
this checkout by path, with any installed copy of the addon disabled so its older
operators cannot shadow the one under test.

It proves the four things the Animations page claims: one imported action becomes
``<folder>/anims/<clip>.dmx`` through ``export_scene.smd``, the written file is
non-empty, the row records what was written, and the file imports back as an
action with the same length — a round trip, not a file that merely exists. It
also checks the export did not leave its own action filter, subdir or export list
behind on the rig.

It does not run a game animgraph compile, and it does not import one of the
extraction's own clips: those live in the owner's S2V output, not in this repo.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Euler

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
# A previously installed copy of this addon keeps a top-level ``forge`` package in
# Blender's addon folder, which is on sys.path. Put this checkout first so the
# probe tests the code in the repo and not the installed version's older forge.
if str(REPO) in sys.path:
    sys.path.remove(str(REPO))
sys.path.insert(0, str(REPO))
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "clip-export.json"))
    parser.add_argument("--folder", default=str(REPO / "artifacts" / "probes" / "clip-export"))
    return parser.parse_args(argv)


def _disable_installed_addon() -> list[str]:
    disabled = []
    for module in list(bpy.context.preferences.addons.keys()):
        if module == "dmf_clip_probe" or not module.endswith("hero_retarget_workbench"):
            continue
        try:
            bpy.ops.preferences.addon_disable(module=module)
            disabled.append(module)
        except RuntimeError:
            continue
    return disabled


def _enable_pulse() -> str:
    if hasattr(bpy.types.Scene, "vs") and hasattr(bpy.ops.export_scene, "smd"):
        return "already enabled"
    for module in PULSE_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except RuntimeError:
            continue
        if hasattr(bpy.types.Scene, "vs") and hasattr(bpy.ops.export_scene, "smd"):
            return module
    raise RuntimeError(
        "pulse-src-ops-missing: enable the PulseSrcOps Blender extension before running this probe"
    )


def _unshadow_forge() -> dict[str, object]:
    """Point ``forge`` at this checkout, not at an installed copy of the addon.

    Blender keeps an enabled addon's package folder on ``sys.path``, so a previous
    install of this addon can serve its own bundled ``forge`` to a probe that means
    to test the repo. Removing that entry and the modules it already loaded is the
    only way the check is about this tree.
    """
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
        "dmf_clip_probe",
        PACKAGE / "__init__.py",
        submodule_search_locations=[str(PACKAGE)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_clip_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _build_rig():
    bpy.ops.object.armature_add(enter_editmode=True)
    armature = bpy.context.object
    armature.name = "hero"
    root = armature.data.edit_bones[0]
    root.name = "pelvis"
    child = armature.data.edit_bones.new("spine_0")
    child.head = root.tail
    child.tail = root.tail + root.tail.__class__((0.0, 0.0, 0.3))
    child.parent = root
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _build_action(armature, label: str):
    armature.animation_data_create()
    action = bpy.data.actions.new(label)
    armature.animation_data.action = action
    if getattr(action, "slots", None) is not None and len(action.slots) == 0:
        action.slots.new(id_type="OBJECT", name=armature.name)
    if getattr(action, "slots", None):
        armature.animation_data.action_slot = action.slots[0]
    bone = armature.pose.bones["spine_0"]
    for frame, angle in ((5, 0.25), (15, -0.2), (25, 0.1)):
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = Euler((angle, 0.0, 0.0)).to_quaternion()
        bone.keyframe_insert("rotation_quaternion", frame=frame)
    return action


def main() -> int:
    args = _arguments()
    report: dict[str, object] = {"checks": {}, "receipt": str(args.report)}
    failed: list[str] = []

    def check(name: str, ok: bool, observed: object) -> None:
        report["checks"][name] = {"pass": bool(ok), "observed": observed}
        print(f"CLIP EXPORT {'PASS' if ok else 'FAIL'} {name}: {observed}")
        if not ok:
            failed.append(name)

    report["disabled_installed_addons"] = _disable_installed_addon()
    report["pulse_src_ops"] = _enable_pulse()
    report["unshadowed"] = _unshadow_forge()
    addon = _load_addon()
    clipops = sys.modules["dmf_clip_probe.clipops"]
    forge_clips = sys.modules.get("forge.clips")
    report["forge_clips"] = getattr(forge_clips, "__file__", "")
    if forge_clips is None or not Path(report["forge_clips"]).resolve().is_relative_to(REPO):
        raise RuntimeError(f"forge-shadowed: forge.clips came from {report['forge_clips']}")

    _clear_scene()
    scene = bpy.context.scene
    settings = scene.dmf
    destination = Path(args.folder)
    if destination.exists():
        for stale in sorted(destination.rglob("*.dmx")):
            stale.unlink()
    destination.mkdir(parents=True, exist_ok=True)

    armature = _build_rig()
    label = "walk_lower_L"
    action = _build_action(armature, label)
    settings.target_armature = armature
    settings.clip_export_dir = str(destination)
    entry = settings.clips.add()
    entry.name = f"{label}.dmx"
    entry.label = label
    entry.kind = "dmx"
    entry.path = str(destination / "source" / f"{label}.dmx")
    entry.action = action.name
    entry.state = "IMPORTED"
    entry.ag = "AG2"

    before_export_path = scene.vs.export_path
    armature.vs.subdir = "keep_me"
    armature.data.vs.action_selection = "CURRENT"

    written = clipops.write_action(settings, entry, destination)
    expected = destination / "clips" / f"{label}.dmx"
    check("writes an AG2 clip under clips", written == expected and expected.is_file(), str(written))
    size = expected.stat().st_size if expected.is_file() else 0
    check("the written DMX is not empty", size > 0, f"{size} bytes")
    check(
        "the row records what was written",
        entry.state == "WRITTEN" and Path(entry.exported) == expected and entry.export_bytes == size,
        f"state={entry.state} bytes={entry.export_bytes}",
    )
    check(
        "the rig and scene keep their own export settings",
        scene.vs.export_path == before_export_path
        and armature.vs.subdir == "keep_me"
        and armature.data.vs.action_selection == "CURRENT"
        and all(row.item is not None for row in scene.vs.export_list),
        f"path={scene.vs.export_path!r} subdir={armature.vs.subdir!r} "
        f"selection={armature.data.vs.action_selection}",
    )
    check("only one file was written", len(list(destination.rglob('*.dmx'))) == 1, len(list(destination.rglob('*.dmx'))))

    legacy_label = "walk_upper_L"
    legacy_action = _build_action(armature, legacy_label)
    legacy = settings.clips.add()
    legacy.name = f"{legacy_label}.dmx"
    legacy.label = legacy_label
    legacy.kind = "dmx"
    legacy.path = str(destination / "source" / f"{legacy_label}.dmx")
    legacy.action = legacy_action.name
    legacy.state = "IMPORTED"
    legacy.ag = "AG1"
    legacy_written = clipops.write_action(settings, legacy, destination)
    legacy_expected = destination / "anims" / f"{legacy_label}.dmx"
    check(
        "writes an AG1 clip under anims",
        legacy_written == legacy_expected and legacy_expected.is_file(),
        str(legacy_written),
    )

    source_length = round(action.frame_range[1] - action.frame_range[0])
    existing = {found.name for found in bpy.data.actions}
    result = bpy.ops.import_scene.kst_dmx(filepath=str(expected), append="NEW_ARMATURE")
    created = [found for found in bpy.data.actions if found.name not in existing]
    check("the written DMX imports back", "FINISHED" in result and bool(created), f"{len(created)} action(s)")
    if created:
        imported = created[0]
        length = round(imported.frame_range[1] - imported.frame_range[0])
        check(
            "the round trip keeps the clip length",
            length == source_length,
            f"source={source_length} reimported={length}",
        )
        curves = sum(
            len(bag.fcurves)
            for layer in getattr(imported, "layers", [])
            for strip in getattr(layer, "strips", [])
            for bag in getattr(strip, "channelbags", [])
        )
        check(
            "the round trip carries bone channels",
            curves > 0,
            f"{curves} fcurves",
        )

    report["folder"] = str(destination)
    report["written_bytes"] = size
    report["failed"] = failed
    receipt = Path(args.report)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"CLIP EXPORT {'OK' if not failed else 'FAILED'} {len(failed)} failed of {len(report['checks'])}")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
