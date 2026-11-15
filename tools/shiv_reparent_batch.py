"""Re-export a whole merged clip folder with the stock pelvis parent restored.

The merge wrote ``pelvis`` as a root bone; the stock clips and the shipped
skeleton have it under ``root_motion``.  Compiling that loses the parent's space
and the pose comes back rotated (see ``tools/clip_rig_space.py``).  This walks a
merged folder, imports the model rig once per clip, restores the link without
moving the rest position, writes the clip back through the workbench exporter,
and records per-clip evidence.

  blender -b --python tools/shiv_reparent_batch.py -- \
      --skeleton <shiv_tailbones.dmx> --merged <merged dir> --out <dir> [--report <json>]
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
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--merged", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "shiv-reparent-batch.json"))
    parser.add_argument("--limit", type=int, default=0)
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
        if module == "dmf_reparent_probe" or not module.endswith("hero_retarget_workbench"):
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
        "dmf_reparent_probe", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_reparent_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def main() -> int:
    args = _arguments()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report)
    report: dict[str, object] = {
        "skeleton": args.skeleton,
        "merged": args.merged,
        "pulse": _enable_pulse(),
        "disabled_installed": _disable_installed_addon(),
        "clips": [],
        "failed": [],
    }
    _unshadow_forge()
    _load_addon()
    clipops = sys.modules["dmf_reparent_probe.clipops"]
    sys.path.insert(0, str(REPO / "tools"))
    from clip_rig_space import parent_pelvis

    def write() -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    clips = sorted(Path(args.merged).glob("*.dmx"))
    if args.limit:
        clips = clips[: args.limit]
    print(f"REPARENT {len(clips)} clips", flush=True)

    for clip in clips:
        started = time.time()
        try:
            for obj in list(bpy.data.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            for action in list(bpy.data.actions):
                bpy.data.actions.remove(action)
            scene = bpy.context.scene
            scene.render.fps = 30
            bpy.ops.import_scene.kst_dmx(filepath=args.skeleton, append="NEW_ARMATURE")
            rig = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"][-1]
            before = {action.name for action in bpy.data.actions}
            bpy.ops.import_scene.kst_dmx(filepath=str(clip), append="APPEND")
            created = [action for action in bpy.data.actions if action.name not in before]
            for obj in [obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj is not rig]:
                bpy.data.objects.remove(obj, do_unlink=True)
            if not created:
                raise RuntimeError("clip-no-action")
            action = created[-1]
            rig.animation_data_create()
            rig.animation_data.action = action
            if getattr(action, "slots", None):
                rig.animation_data.action_slot = action.slots[0]

            link = parent_pelvis(rig)

            settings = scene.dmf
            settings.target_armature = rig
            row = settings.clips.add()
            row.name = "reparent.dmx"
            row.label = "reparent"
            row.kind = "dmx"
            row.action = action.name
            row.state = "IMPORTED"
            row.ag = "AG2"
            target = clipops.write_action(settings, row, out, target=out / clip.name)
            settings.clips.clear()
            report["clips"].append(
                {
                    "clip": clip.stem,
                    "bytes": target.stat().st_size,
                    "link": link,
                    "seconds": round(time.time() - started, 1),
                }
            )
            print(f"REPARENT {clip.stem} -> {target.stat().st_size} b link {link.get('was')}->{link.get('now')}", flush=True)
        except Exception as error:
            report["failed"].append({"clip": clip.stem, "why": f"{type(error).__name__}: {error}"})
            print(f"REPARENT-FAIL {clip.stem}: {error}", flush=True)
        write()

    print(f"REPARENT done {len(report['clips'])} ok, {len(report['failed'])} failed", flush=True)
    return 0 if report["clips"] and not report["failed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
