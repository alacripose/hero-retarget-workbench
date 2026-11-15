"""Merge the tail chain into every stock clip of a hero, in bulk.

The measured failure of the body bake is that it re-authors bones the stock clip
already owns: the IK/aim targets (`arm_L_IKTARGET` turned 120 deg, the leg and
chest offsets 240 deg) and the pelvis height (authored movement clips sit ~54
units above stock, which is the hero lifting off the ground as they start to
move).  The stock clip is correct for all of that, so this pass keeps every stock
track and adds only the tail chain.

Each clip gets its own clean scene: the skeleton is imported fresh (use a
skeleton-only DMX, not the 31 MB mesh export -- that import alone takes minutes),
the stock clip is appended onto it, and the tail chain is sampled from the
matching authored clip, falling back to one named clip when there is no
counterpart.  Reusing a rig between clips makes the next APPEND reuse the previous
action and every clip reports "no action", which is exactly what the first run of
this tool did.

  blender -b --python tools/shiv_bulk_merge.py -- \
      --skeleton <skeleton-only tailbones.dmx> --stock <dir> --tail <dir> \
      --out <dir> --report <json> [--fallback <clip>.dmx]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")
TAIL = ["tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end"]


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--stock", required=True)
    parser.add_argument("--tail", required=True)
    parser.add_argument("--fallback", default="")
    parser.add_argument("--tail-bones", default=",".join(TAIL))
    parser.add_argument("--out", default=str(REPO / "artifacts" / "oldviper" / "shiv-bulk-merge"))
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "shiv-bulk-merge.json"))
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--reuse-skeleton",
        action="store_true",
        help="import the skeleton once and detach the clip action between clips; needed for the 31 MB skeleton, where a fresh import per clip costs minutes",
    )
    return parser.parse_args(argv)


def _enable_pulse() -> None:
    if hasattr(bpy.types.Scene, "vs") and hasattr(bpy.ops.export_scene, "smd"):
        return
    for module in PULSE_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except RuntimeError:
            continue
        if hasattr(bpy.types.Scene, "vs"):
            return
    raise RuntimeError("pulse-src-ops-missing")


def _disable_installed_addon() -> None:
    for module in list(bpy.context.preferences.addons.keys()):
        if module.endswith("hero_retarget_workbench") and module != "dmf_bulk_merge":
            try:
                bpy.ops.preferences.addon_disable(module=module)
            except RuntimeError:
                continue


def _unshadow_forge() -> None:
    for entry in list(sys.path):
        if Path(str(entry)).name == "hero_retarget_workbench":
            sys.path.remove(entry)
    for name in [name for name in sys.modules if name == "forge" or name.startswith("forge.")]:
        if "hero_retarget_workbench" in str(getattr(sys.modules[name], "__file__", "") or ""):
            del sys.modules[name]
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))


def _load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_bulk_merge", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_bulk_merge"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _clear() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _new_armature(path: Path):
    before_objects = {obj.name for obj in bpy.context.scene.objects}
    before_actions = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE")
    created_objects = [obj for obj in bpy.context.scene.objects if obj.name not in before_objects]
    created_actions = [action for action in bpy.data.actions if action.name not in before_actions]
    rig = next(obj for obj in created_objects if obj.type == "ARMATURE")
    return rig, (created_actions[-1] if created_actions else None)


def _append(path: Path, rig):
    before_actions = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before_actions]
    if not created:
        return None
    action = created[-1]
    rig.animation_data_create()
    rig.animation_data.action = action
    if getattr(action, "slots", None):
        rig.animation_data.action_slot = action.slots[0]
    return action


def main() -> int:
    args = _arguments()
    _enable_pulse()
    _disable_installed_addon()
    _unshadow_forge()
    _load_addon()
    tailops = sys.modules["dmf_bulk_merge.tailops"]
    sys.path.insert(0, str(REPO / "tools"))
    clipops = sys.modules["dmf_bulk_merge.clipops"]

    stock_dir = Path(args.stock)
    tail_dir = Path(args.tail)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    clips = sorted(stock_dir.glob("*.dmx"))
    tail_names = [name.strip() for name in args.tail_bones.split(",") if name.strip()]
    fallback = Path(args.fallback) if args.fallback else None
    settings_target = Path(args.report)

    report: dict[str, object] = {"skeleton": args.skeleton, "clips": [], "failed": []}
    hero = None
    reuse = bool(args.reuse_skeleton)
    if reuse:
        _clear()
        bpy.context.scene.render.fps = 30
        hero, _ = _new_armature(Path(args.skeleton))
    for path in clips:
        if args.skip_existing and (out / path.name).is_file():
            continue
        source = tail_dir / path.name
        if not source.is_file():
            source = fallback
        if source is None:
            report["failed"].append({"clip": path.name, "why": "no tail source"})
            continue
        action = None
        before_objects = {obj.name for obj in bpy.context.scene.objects}
        try:
            if not reuse:
                _clear()
                bpy.context.scene.render.fps = 30
                hero, _ = _new_armature(Path(args.skeleton))
            else:
                # Detach the previous clip's action: a rig that keeps it makes the
                # next APPEND reuse that action instead of creating one.
                if hero.animation_data is not None:
                    hero.animation_data.action = None
            action = _append(path, hero)
            if action is None:
                report["failed"].append({"clip": path.name, "why": "no action"})
                print(f"BULK-FAIL {path.name}: no action", flush=True)
                continue
            tail_rig, tail_action = _new_armature(source)
            if tail_action is not None:
                tail_rig.animation_data_create()
                tail_rig.animation_data.action = tail_action
                if getattr(tail_action, "slots", None):
                    tail_rig.animation_data.action_slot = tail_action.slots[0]
            settings = bpy.context.scene.dmf
            settings.target_armature = hero
            row = settings.clips.add()
            row.name = path.name
            row.label = path.stem
            row.kind = "dmx"
            row.action = action.name
            row.state = "IMPORTED"
            row.ag = "AG2"
            written = tailops._write_tail_action(settings, row, action, tail_rig, tail_action, tail_names)
            # Do not re-parent pelvis under root_motion here: the body curves are
            # authored against a 90 degree root and inheriting it lays the body on
            # its side in game (AGENTS.md, 2026-11-15 regression").
            target = clipops.write_action(settings, row, out, target=out / path.name)
            report["clips"].append(
                {"clip": path.name, "tail_from": source.name, **written, "bytes": target.stat().st_size}
            )
            print(f"BULK {path.name} tail<-{source.name} bones={written.get('bones')} {target.stat().st_size}b", flush=True)
        except Exception as error:
            report["failed"].append({"clip": path.name, "why": f"{type(error).__name__}: {error}"})
            print(f"BULK-FAIL {path.name}: {type(error).__name__}: {error}", flush=True)
        finally:
            # The cleanup has to run on the failure path too: a clip that raises
            # after APPEND leaves its action on the shared rig, and every clip
            # after it then reports "no action" instead of appending.
            if reuse:
                if hero.animation_data is not None:
                    hero.animation_data.action = None
                if action is not None and action.name in bpy.data.actions:
                    bpy.data.actions.remove(action)
                for obj in [o for o in bpy.context.scene.objects if o.name not in before_objects]:
                    bpy.data.objects.remove(obj, do_unlink=True)
        # Write the receipt as we go so a long run is not lost to one crash.
        settings_target.parent.mkdir(parents=True, exist_ok=True)
        settings_target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"BULK done {len(report['clips'])} merged, {len(report['failed'])} failed", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
