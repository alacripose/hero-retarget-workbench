"""Merge the working tail motion into the stock Shiv clip, keeping stock arms/head.

Measured on the accepted 6:47 build: its authored clips key 168 bones, but the
stock clip the game ships keys 140.  The difference is not harmless.  The bake
adds the tail chain and 28 ``*_end`` leaf bones the stock clip never animates,
and it **loses ``weaponHand_L`` and ``weaponHand_R``**, which the stock clip does
animate: those are the bones the arms are aimed with, and the model rig the bake
authors on does not have them.  That is the shape of the owner's report -- tail
works, body upright, arms and head rotated wrong.

The bake is also faithful: solved pose matrices match the stock pose at 0.000 deg
on all 138 shared bones, and the written DMX re-imports at 0.000 deg, so the pose
is not being mangled -- the track set is what changes.

This tool takes the stock clip as-is and copies only the tail chain onto it,
sampled from the 6:47 clip that the owner confirmed works.  Nothing else in the
stock clip is touched, so ``weaponHand_*`` and the arms/head keep their stock
values and the ``*_end`` leaves stay unanimated.

  blender -b --python tools/shiv_stock_tail_merge.py -- \
      --skeleton <shiv_tailbones.dmx> --stock <stock clip.dmx> \
      --tail-source <6:47 clip.dmx> --out <dir> --report <json>
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
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from action_curves import action_fcurves  # noqa: E402
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")
TAIL = ["tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end"]


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--stock", required=True)
    parser.add_argument("--tail-source", required=True)
    parser.add_argument("--tail", default=",".join(TAIL))
    parser.add_argument("--out", default=str(REPO / "artifacts" / "oldviper" / "shiv-merge"))
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "shiv-stock-tail-merge.json"))
    return parser.parse_args(argv)


def _enable_pulse() -> str:
    if hasattr(bpy.types.Scene, "vs") and hasattr(bpy.ops.export_scene, "smd"):
        return "already enabled"
    for module in PULSE_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except RuntimeError:
            continue
        if hasattr(bpy.types.Scene, "vs"):
            return module
    raise RuntimeError("pulse-src-ops-missing")


def _disable_installed_addon() -> list[str]:
    disabled = []
    for module in list(bpy.context.preferences.addons.keys()):
        if module == "dmf_merge_probe" or not module.endswith("hero_retarget_workbench"):
            continue
        try:
            bpy.ops.preferences.addon_disable(module=module)
            disabled.append(module)
        except RuntimeError:
            continue
    return disabled


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
        "dmf_merge_probe", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_merge_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _clear() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _keyed_bones(action) -> list[str]:
    order: list[str] = []
    for curve in action_fcurves(action):
        path = curve.data_path
        if 'pose.bones["' not in path:
            continue
        name = path.split('pose.bones["', 1)[1].split('"]', 1)[0]
        if name not in order:
            order.append(name)
    return order


def main() -> int:
    args = _arguments()
    report: dict[str, object] = {
        "skeleton": args.skeleton,
        "stock": args.stock,
        "tail_source": args.tail_source,
        "pulse": _enable_pulse(),
        "disabled_installed": _disable_installed_addon(),
    }
    _unshadow_forge()
    _load_addon()
    tailops = sys.modules["dmf_merge_probe.tailops"]
    clipops = sys.modules["dmf_merge_probe.clipops"]

    _clear()
    scene = bpy.context.scene
    scene.render.fps = 30
    bpy.ops.import_scene.kst_dmx(filepath=args.skeleton, append="NEW_ARMATURE")
    hero = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"][-1]

    before = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=args.stock, append="APPEND")
    stock_actions = [action for action in bpy.data.actions if action.name not in before]
    if not stock_actions:
        raise RuntimeError("stock-clip-no-action")
    stock = stock_actions[-1]
    hero.animation_data_create()
    hero.animation_data.action = stock
    if getattr(stock, "slots", None):
        hero.animation_data.action_slot = stock.slots[0]
    stock_bones = _keyed_bones(stock)
    report["stock_bones"] = len(stock_bones)
    report["stock_has_weapon_hands"] = [name for name in ("weaponHand_L", "weaponHand_R") if name in stock_bones]

    before = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=args.tail_source, append="NEW_ARMATURE")
    tail_rig = [obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj != hero][-1]
    tail_actions = [action for action in bpy.data.actions if action.name not in before]
    if not tail_actions:
        raise RuntimeError("tail-source-no-action")
    tail_action = tail_actions[-1]
    tail_rig.animation_data_create()
    tail_rig.animation_data.action = tail_action
    if getattr(tail_action, "slots", None):
        tail_rig.animation_data.action_slot = tail_action.slots[0]
    tail_names = [name.strip() for name in args.tail.split(",") if name.strip()]
    report["tail_requested"] = tail_names
    report["tail_on_source"] = [name for name in tail_names if tail_rig.pose.bones.get(name) is not None]

    settings = scene.dmf
    settings.target_armature = hero
    row = settings.clips.add()
    row.name = "merged.dmx"
    row.label = "merged"
    row.kind = "dmx"
    row.action = stock.name
    row.state = "IMPORTED"
    row.ag = "AG2"
    written = tailops._write_tail_action(settings, row, stock, tail_rig, tail_action, tail_names)
    # Do not re-parent pelvis under root_motion: the body curves are authored
    # against a 90 degree root, and inheriting it lays the body on its side in
    # game (AGENTS.md, 2026-11-15 regression).
    merged_bones = _keyed_bones(stock)
    report["merged"] = written
    report["merged_bones"] = len(merged_bones)
    report["added"] = [name for name in merged_bones if name not in stock_bones]
    report["removed"] = [name for name in stock_bones if name not in merged_bones]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    row.action = stock.name
    target = clipops.write_action(settings, row, out, target=out / Path(args.stock).name)
    report["written"] = {"path": str(target), "bytes": target.stat().st_size}

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"MERGE stock={len(stock_bones)} merged={len(merged_bones)} added={report['added']} "
        f"removed={report['removed']} bytes={target.stat().st_size}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
