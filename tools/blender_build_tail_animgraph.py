"""Build tail-keyed AnimGraph 2 clip sources and a tail skeleton.

The game plays ``clips/*.vnmclip_c``, not the model's legacy root clips.  This
tool therefore imports the hero's *gameplay* clips, adds the source tail motion
through ``tailops._write_tail_action``, and writes the edited DMX back into the
``clips`` layout ModelDoc/Source 2 uses.  It then exports a skeleton DMX with
the same tail bones so the clip compiler can validate the new tracks.

Run headless:

    blender --background --factory-startup --python-exit-code 1 \
      --python tools/blender_build_tail_animgraph.py -- \
      --out artifacts/tail-animgraph
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "dmf_tail_animgraph_build"
ADDON_ROOT = ROOT / "blender"
EXTRACTIONS = (
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
)
# Gameplay clip -> the source clip whose tail motion is copied.  The labels are
# source/hero labels, not a hard-coded bone map: the transfer reads the selected
# tail chain from the source rig.  --clips replaces this list; no hero is named
# in this file.
CLIPS = (
    ("weapon_stand_idle", "weapon_stand_idle"),
    ("item_run_center", "item_run_center"),
    ("in_air_loop_apex", "in_air_loop_apex"),
)


def args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="output root for the rebuilt clip documents")
    parser.add_argument("--report", default=str(ROOT / "artifacts" / "receipts" / "tail-animgraph.json"))
    parser.add_argument("--hero-body", required=True, help="the port's body DMX with the tail bones")
    parser.add_argument("--source-body", required=True, help="the tail source hero's body DMX")
    parser.add_argument("--source-clips", required=True, help="the tail source's clip DMX folder")
    parser.add_argument("--hero-clips", required=True, help="the port hero's clip DMX folder")
    parser.add_argument(
        "--clips",
        default="",
        help="comma separated target=source pairs; empty uses the defaults above",
    )
    parser.add_argument(
        "--selection",
        default="",
        help="receipt from tools/input_selection.py justifying the source picked per target clip",
    )
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def unshadow():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def load_addon():
    package = ADDON_ROOT / "hero_retarget_workbench"
    spec = importlib.util.spec_from_file_location(PACKAGE, package / "__init__.py", submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def import_rig(path: Path):
    before = {obj.name for obj in bpy.context.scene.objects}
    source2 = sys.modules[f"{PACKAGE}.source2"]
    source2.import_dmx(path, append="NEW_ARMATURE")
    new = [obj for obj in bpy.context.scene.objects if obj.name not in before]
    rigs = [obj for obj in new if obj.type == "ARMATURE"]
    return max(rigs, key=lambda obj: len(obj.data.bones)) if rigs else None


def import_action(rig, path: Path, name: str):
    before = {action.name for action in bpy.data.actions}
    data = rig.animation_data or rig.animation_data_create()
    data.action = None
    core = sys.modules[f"{PACKAGE}.core"]
    core.select_only(bpy.context, [rig])
    bpy.context.view_layer.objects.active = rig
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    source2 = sys.modules[f"{PACKAGE}.source2"]
    source2.import_dmx(path, append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before]
    if not created:
        raise RuntimeError(f"clip-no-action: {path}")
    action = created[0]
    action.name = name
    data.action = action
    if hasattr(data, "action_slot") and getattr(action, "slots", None):
        data.action_slot = action.slots[0]
    return action


def export_action(rig, action, destination: Path):
    """Write exactly one action through the same PulseSrcOps path the addon uses."""
    clipops = sys.modules[f"{PACKAGE}.clipops"]
    settings = bpy.context.scene.dmf
    row = settings.clips.add()
    row.label = destination.stem
    row.ag = "AG2"
    row.action = action.name
    try:
        return clipops.write_action(settings, row, destination.parents[1])
    finally:
        settings.clips.remove(len(settings.clips) - 1)


def main():
    global CLIPS
    options = args()
    if options.clips:
        CLIPS = tuple(
            tuple(part.strip() for part in pair.split("=", 1))
            for pair in options.clips.split(",")
            if "=" in pair
        )
    out = Path(options.out)
    out.mkdir(parents=True, exist_ok=True)
    unshadow()
    addon_utils = __import__("addon_utils")
    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    load_addon()
    tailops = sys.modules[f"{PACKAGE}.tailops"]
    settings = bpy.context.scene.dmf
    report = {"checks": {}, "clips": {}, "errors": []}

    hero = import_rig(Path(options.hero_body))
    source = import_rig(Path(options.source_body))
    settings.target_armature = hero
    settings.source_armature = source
    settings.tail_armature = source
    tail_names = tailops._tail_names(source)
    report["hero"] = {"rig": hero.name, "bones": len(hero.data.bones), "tail": tail_names}
    report["source"] = {"rig": source.name, "bones": len(source.data.bones), "tail": tail_names}

    # A source picked by hand is not a measurement. `--clips` without a selection
    # receipt is refused: the first attempt paired Haze to Tengu over 28 of Tengu's
    # 188 clips because nobody had counted the set being chosen from.
    if options.clips:
        if str(ROOT / "tools") not in sys.path:
            sys.path.insert(0, str(ROOT / "tools"))
        from input_selection import Refused as SelectionRefused
        from input_selection import require as require_selection

        try:
            selection = require_selection(options.selection or None)
        except SelectionRefused as refusal:
            report["errors"].append(f"{refusal.code}: {refusal.detail}")
            report["ok"] = False
            Path(options.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"REFUSE {refusal.code}: {refusal.detail}", flush=True)
            return 2
        justified = int(selection.get("pairs") or len(selection.get("chosen") or []))
        if len(CLIPS) != justified:
            message = (
                f"hand-picked-input: --clips has {len(CLIPS)} pairs, the selection receipt justifies {justified}"
            )
            report["errors"].append(message)
            report["ok"] = False
            Path(options.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"REFUSE {message}", flush=True)
            return 2

    for target_stem, source_stem in CLIPS:
        target_path = Path(options.hero_clips) / f"{target_stem}.dmx"
        source_path = Path(options.source_clips) / f"{source_stem}.dmx"
        if not target_path.is_file() or not source_path.is_file():
            report["errors"].append(f"missing clip pair: {target_path} / {source_path}")
            continue
        target_action = import_action(hero, target_path, f"DMF tail target {target_stem}")
        source_action = import_action(source, source_path, f"DMF tail source {source_stem}")
        try:
            result = tailops._write_tail_action(
                settings,
                SimpleNamespace(label=target_stem),
                target_action,
                source,
                source_action,
                tail_names,
            )
        except Exception as error:
            report["errors"].append(f"{target_stem}: {type(error).__name__}: {error}")
            continue
        hero_folder = Path(options.hero_clips).parent
        try:
            relative = hero_folder.relative_to(hero_folder.parents[2])
        except (IndexError, ValueError):
            relative = Path(hero_folder.name)
        destination = out / relative / "clips" / f"{target_stem}.dmx"
        written = export_action(hero, target_action, destination)
        report["clips"][target_stem] = {"written": str(written), "bytes": written.stat().st_size, **result}

    report["ok"] = not report["errors"] and bool(report["clips"])
    target = Path(options.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
