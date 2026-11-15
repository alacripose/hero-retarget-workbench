"""Prove the automatic tail pass on a hero that has no tail.

Run headless:

    blender --background --factory-startup --python-exit-code 1 \
        --python tools/blender_tail_auto_probe.py -- \
        --extraction <hero extraction> --report artifacts/receipts/probe-tail-auto.json

The probe imports the hero, imports a few of its clips, discovers the tail source's tail
source, then runs the one-click automatic pass.  It asserts the hero gained the
source tail bones and that each imported hero action gained animated tail keys.
It does not claim a game compile or an observed viewport render.
"""

from __future__ import annotations

import argparse
import addon_utils
import importlib.util
import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]

def _port_target():
    """Load forge.port_target by path: the add-on's vendored `forge` shadows the repo one."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "dmf_port_target", ROOT / "forge" / "port_target.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ADDON_ROOT = ROOT / "blender"
PACKAGE = "dmf_tail_auto_probe"

# Defaults for a quick probe, not a hero list: a real port passes --clips/--hero.
TARGET_LABELS = ("aim_weapon_idle", "cast_start", "flinch_back", "in_air_loop_apex")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", required=True)
    parser.add_argument("--hero", default="", help="hero folder name; empty discovers it from the extraction")
    parser.add_argument("--tail", default="", help="substring of the tail source label; empty takes the first discovered")
    parser.add_argument("--clips", default="", help="comma separated target clips; empty uses the probe defaults")
    parser.add_argument("--report", required=True)
    return parser.parse_args(argv)


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
    if str(ROOT) in sys.path:
        sys.path.remove(str(ROOT))
    sys.path.insert(0, str(ROOT))
    return {"path_entries": removed, "modules": dropped}


def load_addon():
    package = ADDON_ROOT / "hero_retarget_workbench"
    spec = importlib.util.spec_from_file_location(
        PACKAGE,
        package / "__init__.py",
        submodule_search_locations=[str(package)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    module.register()
    return module


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


def main():
    args = parse_args()
    extraction = Path(args.extraction).resolve()
    report_path = Path(args.report)
    report = {
        "probe": "tail-auto",
        "extraction": str(extraction),
        "checks": {},
        "errors": [],
    }

    # A user-installed copy must not shadow the working tree during this probe.
    report["disabled_installed"] = disable_installed()
    report["unshadowed"] = unshadow_forge()

    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    module = load_addon()
    tailops = sys.modules[f"{PACKAGE}.tailops"]
    clipops = sys.modules[f"{PACKAGE}.clipops"]
    settings = bpy.context.scene.dmf

    global TARGET_LABELS
    if args.clips:
        TARGET_LABELS = tuple(name.strip() for name in args.clips.split(",") if name.strip())
    port_target = _port_target()

    root = port_target.hero_root(extraction, args.hero)
    settings.extraction_dir = str(extraction)
    settings.body_dmx = str(port_target.body_dmx(root))
    report["checks"]["hero_root"] = str(root)
    bpy.ops.dmf.import_hero()
    hero = settings.target_armature
    report["checks"]["hero_imported"] = bool(hero)
    report["checks"]["hero_name"] = hero.name if hero else ""

    imported = []
    for label in TARGET_LABELS:
        index = next(
            (i for i, candidate in enumerate(settings.clips) if candidate.label.lower() == label),
            None,
        )
        if index is None:
            report["errors"].append(f"target clip missing: {label}")
            continue
        clipops._import_one(settings, settings.clips[index])
        entry = settings.clips[index]
        state = entry.state
        print(f"PROBE target {label}: state={state} action={entry.action!r}", flush=True)
        if state != "IMPORTED" or not entry.action:
            report["errors"].append(f"target clip did not import: {label} ({state}, {entry.action!r})")
        else:
            imported.append(label)
    report["checks"]["target_clips"] = imported

    tailops.discover(settings, live_files=[])
    choices = [
        (index, option)
        for index, option in enumerate(settings.tail_options)
        if option.count and (not args.tail or args.tail.lower() in option.label.lower())
    ]
    if not choices:
        report["errors"].append(f"no tail source discovered matching {args.tail or 'any'}")
        write_report(report_path, report)
        raise SystemExit(1)
    index, option = choices[0]
    settings.tail_option_index = index
    report["checks"]["tail_source"] = option.label
    report["checks"]["tail_source_path"] = option.path
    report["checks"]["tail_source_bones"] = int(option.count)

    report["checks"]["imported_rows"] = [
        (row.label, row.state, row.action)
        for row in settings.clips
        if row.action
    ]
    try:
        queued = tailops.start_auto(settings, schedule=False)
    except Exception as error:
        report["errors"].append(f"start_auto: {type(error).__name__}: {error}")
        write_report(report_path, report)
        print(json.dumps(report, indent=2), flush=True)
        raise SystemExit(1)
    report["checks"]["queued"] = queued
    guard = 0
    while tailops._AUTO_QUEUE and guard < 100000:
        tailops._auto_tick()
        guard += 1
    report["checks"]["auto_stopped"] = not tailops._AUTO_QUEUE
    report["checks"]["updated"] = getattr(tailops, "_AUTO_UPDATED", 0)
    report["checks"]["skipped"] = getattr(tailops, "_AUTO_SKIPPED", 0)
    report["checks"]["failed"] = getattr(tailops, "_AUTO_FAILED", 0)
    report["checks"]["note"] = settings.tail_note

    source = settings.tail_armature
    tail_names = [name for name in tailops._tail_names(source) if hero.data.bones.get(name)]
    report["checks"]["hero_tail_bones"] = tail_names
    if len(tail_names) < 5:
        report["errors"].append(f"hero gained only {len(tail_names)} tail bones")

    for label in imported:
        row = next(candidate for candidate in settings.clips if candidate.label.lower() == label)
        action = bpy.data.actions.get(row.action)
        animated = sorted(tailops._action_bones(action) & set(tail_names)) if action else []
        report["checks"].setdefault("clip_tail_bones", {})[label] = animated
        if not animated:
            report["errors"].append(f"{label} has no tail keys after the pass")
            continue
        start, end = (int(round(value)) for value in action.frame_range)
        if end <= start:
            report["errors"].append(f"{label} has no frame range")
            continue
        data = hero.animation_data or hero.animation_data_create()
        data.action = action
        if hasattr(data, "action_slot") and getattr(action, "slots", None):
            data.action_slot = action.slots[0]
        motion = {}
        middle = start + (end - start) // 2
        for name in animated:
            bases = []
            for frame in (start, middle, end):
                bpy.context.scene.frame_set(frame)
                bpy.context.view_layer.update()
                bone = hero.pose.bones.get(name)
                bases.append(
                    tuple(round(value, 6) for row in bone.matrix_basis for value in row)
                    if bone else ()
                )
            motion[name] = bases[0] != bases[1] or bases[0] != bases[2]
        report["checks"].setdefault("clip_motion", {})[label] = motion

    moving_clips = [
        label for label, bones in report["checks"].get("clip_motion", {}).items()
        if any(bones.values())
    ]
    report["checks"]["moving_clips"] = moving_clips
    if imported and not moving_clips:
        report["errors"].append("no imported clip's tail moves between its first and last frame")

    report["ok"] = not report["errors"]
    write_report(report_path, report)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
