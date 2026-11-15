"""Bring the old Viper slide's leg-hide and tail scale onto the live slide clips.

The owner's old Vyper addon hides the legs and sizes the tail during a slide:

    slide_forward  leg_upper_L 0.0, leg_lower_L 0.0, leg_upper_R 0.0,
                   tail_0 2.0, tail_1 0.75
    slide_aim      all 1.0
    slide_getup    all 1.0

Later builds replaced that with a legs-out slide.  The pose itself is not what
this ports: the live game's own slide clips already play correctly against the
modern model, so they are the source.  This probe imports each live clip, keys
the old scale channels onto it, and writes the clip back with the workbench's own
exporter — one importer and one exporter, no cross-rig axis maths.

It also round-trips one clip unchanged first and measures the difference, so a
"port" cannot silently be an axis change.

  blender -b --python tools/oldvyper_slide_scale.py -- --report artifacts/receipts/oldvyper-slide-scale.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
if str(REPO) in sys.path:
    sys.path.remove(str(REPO))
sys.path.insert(0, str(REPO))
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")

LIVE = REPO / "artifacts" / "oldviper" / "live-model"
CLIP_SOURCES = {
    "slide_loop": "viper/dmx/animation/slide_loop.dmx",
    "aim_weapon_slide": "tengu_v2/dmx/animation/slide_aim.dmx",
    "slide_getup": "tengu_v2/dmx/animation/slide_getup.dmx",
}


def _stock(name: str) -> Path:
    """Find the extracted DMX; S2V writes some files under a pak-named folder."""
    wanted = CLIP_SOURCES[name]
    matches = sorted(LIVE.rglob(Path(wanted).name))
    for match in matches:
        if match.as_posix().endswith(wanted):
            return match
    if matches:
        return matches[0]
    return LIVE / wanted


STOCK = {name: _stock(name) for name in CLIP_SOURCES}
# Bone -> the constant scale the old slide authored.
SCALE = {
    "slide_loop": {"leg_upper_L": 0.001, "leg_lower_L": 0.001, "leg_upper_R": 0.001,
                   "tail_0": 2.0, "tail_1": 0.75},
    "aim_weapon_slide": {},
    "slide_getup": {},
}


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(
            REPO
            / "artifacts"
            / "oldviper"
            / "port"
            / "content"
            / "citadel_addons"
            / "viper_oldvyper"
            / "models"
            / "heroes_staging"
            / "viper"
            / "dmx"
            / "animation"
        ),
    )
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "oldvyper-slide-scale.json"))
    return parser.parse_args(argv)


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
    raise RuntimeError("pulse-src-ops-missing: enable the PulseSrcOps Blender extension")


def _unshadow_forge() -> None:
    for entry in list(sys.path):
        try:
            candidate = Path(entry)
        except (TypeError, ValueError):
            continue
        if candidate.name == "hero_retarget_workbench":
            sys.path.remove(entry)
    for name in [name for name in sys.modules if name == "forge" or name.startswith("forge.")]:
        path = str(getattr(sys.modules[name], "__file__", "") or "")
        if "hero_retarget_workbench" in path:
            del sys.modules[name]
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))


def _load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_oldvyper_scale", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_oldvyper_scale"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _clear() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _import(path: Path):
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE")
    rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    rig = rigs[-1]
    created = [action for action in bpy.data.actions]
    action = created[-1] if created else None
    if action is not None:
        rig.animation_data_create()
        rig.animation_data.action = action
        if getattr(action, "slots", None):
            rig.animation_data.action_slot = action.slots[0]
    return rig, action


def _sample(rig, action, frames) -> dict:
    scene = bpy.context.scene
    out = {}
    rig.animation_data_create()
    rig.animation_data.action = action
    if getattr(action, "slots", None):
        rig.animation_data.action_slot = action.slots[0]
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        out[frame] = {bone.name: bone.matrix.copy() for bone in rig.pose.bones}
    return out


def _difference(a: dict, b: dict) -> dict:
    worst_turn = (0.0, "")
    worst_move = (0.0, "")
    for frame in a:
        for name, matrix in a[frame].items():
            other = b.get(frame, {}).get(name)
            if other is None:
                continue
            turn = math.degrees(matrix.to_quaternion().rotation_difference(other.to_quaternion()).angle)
            move = (matrix.translation - other.translation).length
            if turn > worst_turn[0]:
                worst_turn = (round(turn, 3), name)
            if move > worst_move[0]:
                worst_move = (round(move, 4), name)
    return {"worst_rotation_deg": worst_turn, "worst_translation": worst_move}


def main() -> int:
    args = _arguments()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"stock": {}, "round_trip": {}, "clips": []}
    report["pulse_src_ops"] = _enable_pulse()
    _unshadow_forge()
    _load_addon()
    clipops = sys.modules["dmf_oldvyper_scale.clipops"]

    for clip, path in STOCK.items():
        if not path.is_file():
            raise RuntimeError(f"stock-clip-missing: {path}")

    # Round trip the working clip unchanged through the same importer/exporter so
    # any later difference is the scale keys, not an axis or root change.
    _clear()
    rig, action = _import(STOCK["slide_loop"])
    scene = bpy.context.scene
    frames = [1, 5, 10, 15]
    frames = [f for f in frames if f <= int(round(action.frame_range[1]))] or [1]
    before = _sample(rig, action, frames)
    settings = scene.dmf
    settings.target_armature = rig
    entry = settings.clips.add()
    entry.name = "slide_loop.dmx"
    entry.label = "slide_loop"
    entry.kind = "dmx"
    entry.action = action.name
    entry.state = "IMPORTED"
    entry.ag = "AG2"
    round_path = clipops.write_action(settings, entry, out, target=out / "_roundtrip_slide_loop.dmx")
    _clear()
    rig2, action2 = _import(round_path)
    after = _sample(rig2, action2, frames)
    report["round_trip"] = {
        "file": str(round_path),
        "bytes": round_path.stat().st_size,
        **_difference(before, after),
    }

    for clip, path in STOCK.items():
        _clear()
        scene = bpy.context.scene
        rig, action = _import(path)
        scene.render.fps = 30
        start, end = (int(round(value)) for value in action.frame_range)
        values = SCALE[clip]
        keyed = {}
        for bone_name, value in values.items():
            bone = rig.pose.bones.get(bone_name)
            if bone is None:
                keyed[bone_name] = "missing"
                continue
            bone.scale = Vector((value, value, value))
            for frame in range(start, end + 1):
                bone.keyframe_insert("scale", frame=frame)
            keyed[bone_name] = value
        settings = scene.dmf
        settings.target_armature = rig
        entry = settings.clips.add()
        entry.name = f"{clip}.dmx"
        entry.label = clip
        entry.kind = "dmx"
        entry.action = action.name
        entry.state = "IMPORTED"
        entry.ag = "AG2"
        written = clipops.write_action(settings, entry, out, target=out / f"{clip}.dmx")
        report["clips"].append(
            {
                "clip": clip,
                "source": str(path),
                "written": str(written),
                "bytes": written.stat().st_size,
                "frames": end - start + 1,
                "scale": keyed,
            }
        )
        print(f"SCALE {clip} <- {path.name}: {written.stat().st_size} bytes, scale {keyed}")

    receipt = Path(args.report)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"SCALE OK {len(report['clips'])} clips; round trip {report['round_trip']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
