"""Measure whether tail bones actually move in source and built clips.

The automatic pass used to call a clip "animated" when it merely had tail
fcurves.  A constant curve still passes that check.  This probe reads the pose
at several frames and reports the largest change per tail bone, so a static
source idle cannot be mistaken for working blend.

Run headless:

    blender --background --factory-startup --python-exit-code 1 \
      --python tools/blender_tail_motion_probe.py -- \
      --report artifacts/receipts/tail-motion.json
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

PACKAGE_NAME = "dmf_tail_motion_probe"
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
# No hero is named here: --source-extraction names the tail source and --build
# names the port's own build folder, so the probe runs the same on any pair.
SOURCE_RIG = None
BUILD = None
SOURCE_CLIPS = ()
BUILT_CLIPS = ()
AG_CLIPS = ()


def args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(ROOT / "artifacts" / "receipts" / "tail-motion.json"))
    parser.add_argument("--source-extraction", required=True, help="extraction holding the tail source hero")
    parser.add_argument("--source-hero", default="", help="hero folder name inside the source extraction")
    parser.add_argument("--build", required=True, help="the port's build folder, holding its body and clips")
    parser.add_argument("--source-clips", default="", help="comma separated source clip stems to sample")
    parser.add_argument("--built-clips", default="", help="comma separated built clip stems to compare")
    parser.add_argument("--ag-clips", default="", help="comma separated relative clip documents")
    parser.add_argument("--animgraph-root", default=str(ROOT / "artifacts" / "tail-animgraph"), help="where rebuilt clip documents were written")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def load_addon():
    package = ADDON_ROOT / "hero_retarget_workbench"
    spec = importlib.util.spec_from_file_location(PACKAGE_NAME, package / "__init__.py", submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def import_model(path: Path):
    before = {obj.name for obj in bpy.context.scene.objects}
    source2 = sys.modules[f"{PACKAGE_NAME}.source2"]
    source2.import_dmx(path, append="NEW_ARMATURE")
    new = [obj for obj in bpy.context.scene.objects if obj.name not in before]
    rigs = [obj for obj in new if obj.type == "ARMATURE"]
    return max(rigs, key=lambda obj: len(obj.data.bones)) if rigs else None


def import_action(rig, path: Path):
    before = {action.name for action in bpy.data.actions}
    data = rig.animation_data or rig.animation_data_create()
    data.action = None
    source2 = sys.modules[f"{PACKAGE_NAME}.source2"]
    source2.import_dmx(path, append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before]
    if not created:
        return None
    action = created[0]
    data.action = action
    if hasattr(data, "action_slot") and getattr(action, "slots", None):
        data.action_slot = action.slots[0]
    return action


def tail_names(rig):
    tailops = sys.modules[f"{PACKAGE_NAME}.tailops"]
    return [name for name in tailops._tail_names(rig) if rig.pose.bones.get(name)]


def motion(rig, action, names):
    start, end = (int(round(value)) for value in action.frame_range)
    if end <= start:
        return {"frames": [start, end], "moving": {}, "max_delta": 0.0}
    frames = sorted({start, start + (end - start) // 4, start + (end - start) // 2, start + (3 * (end - start)) // 4, end})
    samples = {name: [] for name in names}
    data = rig.animation_data or rig.animation_data_create()
    data.action = action
    if hasattr(data, "action_slot") and getattr(action, "slots", None):
        data.action_slot = action.slots[0]
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        for name in names:
            bone = rig.pose.bones.get(name)
            if bone is not None:
                samples[name].append(tuple(round(value, 8) for row in bone.matrix_basis for value in row))
    moving = {}
    deltas = {}
    for name, rows in samples.items():
        delta = max(
            (abs(a - b) for first, second in zip(rows, rows[1:]) for a, b in zip(first, second)),
            default=0.0,
        )
        moving[name] = delta > 1e-6
        deltas[name] = round(delta, 8)
    return {"frames": [start, end, frames], "moving": moving, "deltas": deltas, "max_delta": max(deltas.values(), default=0.0)}


def main():
    global SOURCE_RIG, BUILD, SOURCE_CLIPS, BUILT_CLIPS, AG_CLIPS
    options = args()
    port_target = _port_target()

    SOURCE_RIG = port_target.hero_root(options.source_extraction, options.source_hero)
    BUILD = Path(options.build)
    split = lambda text: tuple(name.strip() for name in text.split(",") if name.strip())
    SOURCE_CLIPS = split(options.source_clips) or tuple(
        sorted({path.stem.split(".vnmclip")[0] for path in (SOURCE_RIG / "clips").glob("*.dmx")})
    )
    BUILT_CLIPS = split(options.built_clips) or tuple(
        sorted({path.stem for path in BUILD.glob("*.dmx")})
    )
    AG_CLIPS = split(options.ag_clips)
    report = {"checks": {}, "errors": []}
    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    load_addon()
    port_target = _port_target()

    source = import_model(port_target.body_dmx(SOURCE_RIG))
    names = tail_names(source)
    report["source_rig"] = {"name": source.name, "bones": len(source.data.bones), "tail": names}
    report["source"] = {}
    for stem in SOURCE_CLIPS:
        candidates = [SOURCE_RIG / f"{stem}.dmx", SOURCE_RIG / "dmx" / "animation" / f"{stem}.dmx", SOURCE_RIG / "clips" / f"{stem}.dmx"]
        path = next((item for item in candidates if item.is_file()), candidates[0])
        if not path.is_file():
            report["source"][stem] = {"missing": str(path)}
            continue
        action = import_action(source, path)
        report["source"][stem] = motion(source, action, names) if action else {"no_action": True}
        report["source"][stem]["path"] = str(path)
    built_body = next(iter(sorted(BUILD.glob("*body*.dmx"))), None)
    if built_body is None:
        raise SystemExit(f"no built body dmx under {BUILD}")
    built = import_model(built_body)
    built_names = tail_names(built)
    report["built_rig"] = {"name": built.name, "bones": len(built.data.bones), "tail": built_names}
    report["built"] = {}
    for stem in BUILT_CLIPS:
        path = BUILD / f"{stem}.dmx"
        if not path.is_file():
            report["built"][stem] = {"missing": str(path)}
            continue
        action = import_action(built, path)
        report["built"][stem] = motion(built, action, built_names) if action else {"no_action": True}
    report["animgraph"] = {}
    for stem in AG_CLIPS:
        path = Path(options.animgraph_root) / Path(SOURCE_RIG).relative_to(Path(SOURCE_RIG).parents[2]) / f"{stem}.dmx"
        if not path.is_file():
            report["animgraph"][stem] = {"missing": str(path)}
            continue
        action = import_action(built, path)
        report["animgraph"][stem] = motion(built, action, built_names) if action else {"no_action": True}
    report["ok"] = all(
        row.get("max_delta", 0.0) > 0.0
        for section in ("source", "built", "animgraph")
        for row in report[section].values()
        if "missing" not in row and "no_action" not in row
    )
    target = Path(options.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
