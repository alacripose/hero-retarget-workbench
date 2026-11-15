"""Forward-port the old Vyper slide animation onto the live Viper skeleton.

The owner's old Vyper addon (``oldvyper.vpk``) carries its animation set inside
the modeldoc: 314 sequences, including ``slide_aim``, ``slide_forward`` and
``slide_getup``.  Those three are the pre-rewrite slide: ``slide_forward`` scales
``leg_upper_L``/``leg_lower_L``/``leg_upper_R`` to 0.0 and ``tail_0`` to 2.0 with
``tail_1`` at 0.75, so the legs disappear and the tail becomes the slider.  The
live game's AG2 clips replaced that with a legs-out slide.

This probe takes the old sequences through Source 2 Viewer's glTF animation
export, imports them beside the live Viper skeleton, retargets each bone by its
world-space delta (the two rigs do not share a rest pose or a joint order),
writes the result as animation DMX with the workbench's own exporter, and writes
one ``.vnmclip`` document per clip so CSDK13 can compile them.

  blender -b --python tools/oldvyper_slide_port.py -- --report artifacts/receipts/oldvyper-slide-port.json

It does not pack a VPK and it does not claim a compile; ``tools/project.py``
stages and compiles the documents it writes.
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
from mathutils import Euler, Matrix, Quaternion, Vector

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
if str(REPO) in sys.path:
    sys.path.remove(str(REPO))
sys.path.insert(0, str(REPO))
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")

# Old sequence -> the AG2 clip the live animgraph plays in that slot.
ROOT_MOTION = Euler((math.pi / 2, 0.0, math.pi / 2), "XYZ").to_matrix().to_4x4()

CLIP_MAP = {
    "slide_forward": "slide_loop",
    "slide_aim": "aim_weapon_slide",
    "slide_getup": "slide_getup",
}


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", default=str(REPO / "artifacts" / "oldviper" / "gltf-full" / "viper.glb"))
    parser.add_argument(
        "--skeleton-dmx",
        default=str(
            REPO
            / "artifacts"
            / "tail-skeletons"
            / "models"
            / "heroes_staging"
            / "viper"
            / "dmx"
            / "mesh"
            / "viper_skel.dmx"
        ),
    )
    parser.add_argument(
        "--out",
        default=str(REPO / "artifacts" / "oldviper" / "port" / "content" / "citadel_addons" / "viper_oldvyper" / "models" / "heroes_staging" / "viper"),
    )
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "oldvyper-slide-port.json"))
    parser.add_argument("--standup", type=float, default=0.0, help="extra roll about the live side axis, degrees")
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
        "dmf_oldvyper_probe", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_oldvyper_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _armatures() -> list:
    return [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]


def _rigid(matrix: Matrix) -> Matrix:
    """Rotation and translation only; a zero-scaled leg has no invertible matrix.

    The old slide hides the legs by scaling their bones to 0.0, so the pose
    matrix itself is singular.  The scale is carried separately on the target
    pose bone, which is also what an animation DMX stores.
    """
    return Matrix.Translation(matrix.translation) @ matrix.to_quaternion().to_matrix().to_4x4()


def _frame_fix(source, target, matched: list[str]) -> tuple[Quaternion, float]:
    """Rotation and scale from the old glTF frame into the live Source 2 frame.

    Source 2 Viewer's glTF export leaves the old rig in glTF axes: its bones
    point along +X where the DMX rig's bones point along +Y, the whole rig sits a
    quarter turn from the live one, and its units are roughly 39x smaller.  A
    world delta copied between the two frames lands the character on its back
    with one side inverted, which is exactly the break this probe exists to fix.
    """
    rotation = Quaternion()
    for name in ("spine_2", "spine_1", "spine_0", "pelvis"):
        old_bone = source.data.bones.get(name)
        new_bone = target.data.bones.get(name)
        if old_bone is not None and new_bone is not None:
            rotation = (
                new_bone.matrix_local.to_quaternion()
                @ old_bone.matrix_local.to_quaternion().inverted()
            )
            break
    # Bone lengths are not comparable: the glTF exporter spaces its joints at
    # roughly 2.6x while the rig itself is 39x.  Pelvis-to-bone distances are the
    # rig's own scale, so measure those and take the median.
    old_pelvis = source.data.bones["pelvis"].head_local
    new_pelvis = target.data.bones["pelvis"].head_local
    ratios = sorted(
        (target.data.bones[name].head_local - new_pelvis).length
        / (source.data.bones[name].head_local - old_pelvis).length
        for name in matched
        if name != "pelvis"
        and (source.data.bones[name].head_local - old_pelvis).length > 1e-5
    )
    scale = ratios[len(ratios) // 2] if ratios else 1.0
    return rotation, scale


def _basis(delta: Matrix, rest: Matrix, parent_delta: Matrix | None, parent_rest: Matrix | None) -> Matrix:
    """Local pose basis that puts a bone at ``delta @ rest`` in armature space."""
    target = delta @ rest
    if parent_rest is None:
        return rest.inverted() @ target
    parent_target = (parent_delta @ parent_rest) if parent_delta is not None else parent_rest
    return (parent_rest.inverted() @ rest).inverted() @ parent_target.inverted() @ target


def _retarget(
    source,
    target,
    clip_name: str,
    fps: int,
    rotation: Quaternion,
    scale: float,
    standup: Matrix,
    standup_degrees: float,
) -> dict:
    """Copy one source action onto the target rig as a new action."""
    old_action = bpy.data.actions.get(clip_name)
    if old_action is None:
        candidates = [a for a in bpy.data.actions if clip_name in a.name]
        if not candidates:
            raise RuntimeError(f"glb-action-missing: {clip_name}")
        old_action = candidates[0]
    start, end = old_action.frame_range
    first = int(round(start))
    last = max(first + 1, int(round(end)))

    source.animation_data_create()
    source.animation_data.action = old_action
    if getattr(old_action, "slots", None):
        source.animation_data.action_slot = old_action.slots[0]

    old_bones = {bone.name: bone for bone in source.data.bones}
    new_bones = {bone.name: bone for bone in target.data.bones}
    # IK targets and socket helpers are authored per rig; the old ones cannot
    # drive the live IK setup, and copying them tears the legs and arms apart.
    skip = ("iktarget", "muzzle")
    matched = [
        name
        for name in old_bones
        if name in new_bones and not any(token in name.lower() for token in skip)
    ]
    action = bpy.data.actions.new(f"{target.name}_{clip_name}")
    target.animation_data_create()
    target.animation_data.action = action
    if getattr(action, "slots", None) is not None and len(action.slots) == 0:
        action.slots.new(id_type="OBJECT", name=target.name)
    if getattr(action, "slots", None):
        target.animation_data.action_slot = action.slots[0]

    scales: dict[str, tuple[float, float]] = {}
    worst: tuple[float, str] = (0.0, "")
    inverse = rotation.inverted()

    # Owner report on the two attempts so far: with the constant folded in she
    # faced forward but lay on the floor; dividing the root out of the body put
    # her at an angle to forward. Facing was right, so the remaining error is a
    # roll about the live rig's side axis, not another yaw. `standup` rotates the
    # body about the pelvis in the live frame before the clip is written.
    bpy.context.scene.frame_set(first)
    bpy.context.view_layer.update()
    base_pose = {name: source.pose.bones[name].matrix.copy() for name in matched}

    def to_live(delta: Matrix) -> Matrix:
        """A delta expressed in the old frame, expressed in the live frame."""
        turn = rotation @ delta.to_quaternion() @ inverse
        return Matrix.Translation(rotation @ (delta.translation * scale)) @ turn.to_matrix().to_4x4()

    for frame in range(first, last + 1):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        frame_deltas: dict[str, Matrix] = {}
        for name in matched:
            sample = source.pose.bones[name]
            sample.rotation_mode = "QUATERNION"
            frame_deltas[name] = to_live(_rigid(sample.matrix @ _rigid(base_pose[name]).inverted()))
            value = min(sample.scale)
            low, high = scales.get(name, (value, value))
            scales[name] = (min(low, value), max(high, value))
        if "pelvis" in frame_deltas:
            frame_deltas["pelvis"] = standup @ frame_deltas["pelvis"]
        for name in matched:
            bone = new_bones[name]
            parent = bone.parent
            parent_delta = frame_deltas.get(parent.name) if parent is not None else None
            parent_rest = parent.matrix_local if parent is not None else None
            basis = _basis(frame_deltas[name], bone.matrix_local, parent_delta, parent_rest)
            pose_bone = target.pose.bones[name]
            pose_bone.rotation_mode = "QUATERNION"
            location, turn, _scale = basis.decompose()
            pose_bone.location = location
            pose_bone.rotation_quaternion = turn
            angle = math.degrees(min(turn.angle, 2.0 * math.pi - turn.angle))
            if angle > worst[0]:
                worst = (round(angle, 1), name)
            # The exporter inverts each bone's pose matrix, so the literal 0.0
            # scale the old clip uses to hide the legs has to become the smallest
            # scale that still inverts.
            pose_bone.scale = Vector(tuple(max(1e-3, component) for component in source.pose.bones[name].scale))
            pose_bone.keyframe_insert("location", frame=frame - first + 1)
            pose_bone.keyframe_insert("rotation_quaternion", frame=frame - first + 1)
            pose_bone.keyframe_insert("scale", frame=frame - first + 1)

    action.use_fake_user = True
    return {
        "clip": clip_name,
        "action": action.name,
        "frames": last - first + 1,
        "frame_rotation_deg": round(math.degrees(rotation.angle), 2),
        "frame_scale": round(scale, 4),
        "standup_deg": standup_degrees,
        "worst_local_rotation": worst,
        "root_motion": "constant folded into pelvis (facing-forward variant)",
        "matched_bones": len(matched),
        "unmatched": sorted(name for name in old_bones if name not in new_bones),
        "scaled_bones": {
            name: [round(low, 4), round(high, 4)]
            for name, (low, high) in sorted(scales.items())
            if abs(low - 1.0) > 1e-4 or abs(high - 1.0) > 1e-4
        },
    }

    action.use_fake_user = True
    return {
        "clip": clip_name,
        "action": action.name,
        "frames": last - first + 1,
        "frame_rotation_deg": round(math.degrees(rotation.angle), 2),
        "frame_scale": round(scale, 4),
        "worst_local_rotation": worst,
        "root_motion": "source root divided out of the body, written on the root joint",
        "matched_bones": len(matched),
        "unmatched": sorted(name for name in old_bones if name not in new_bones),
        "scaled_bones": {
            name: [round(low, 4), round(high, 4)]
            for name, (low, high) in sorted(scales.items())
            if abs(low - 1.0) > 1e-4 or abs(high - 1.0) > 1e-4
        },
    }


def main() -> int:
    args = _arguments()
    report: dict[str, object] = {"source": {}, "clips": [], "written": [], "documents": []}
    report["pulse_src_ops"] = _enable_pulse()
    _unshadow_forge()
    addon = _load_addon()
    clipops = sys.modules["dmf_oldvyper_probe.clipops"]
    forge_clips = sys.modules.get("forge.clips")
    if forge_clips is None or not Path(forge_clips.__file__).resolve().is_relative_to(REPO):
        raise RuntimeError(f"forge-shadowed: {getattr(forge_clips, '__file__', None)}")

    skeleton_dmx = Path(args.skeleton_dmx)
    glb = Path(args.glb)
    for path in (skeleton_dmx, glb):
        if not path.is_file():
            raise RuntimeError(f"port-input-missing: {path}")

    _clear_scene()
    scene = bpy.context.scene
    scene.render.fps = 30
    bpy.ops.import_scene.kst_dmx(filepath=str(skeleton_dmx), append="NEW_ARMATURE")
    rigs = _armatures()
    if not rigs:
        raise RuntimeError("live-rig-not-imported")
    target = rigs[-1]
    target.name = "viper"

    bpy.ops.import_scene.gltf(filepath=str(glb))
    old_rigs = [obj for obj in _armatures() if obj is not target]
    if not old_rigs:
        raise RuntimeError("glb-rig-not-imported")
    source = old_rigs[0]
    report["source"] = {
        "glb": str(glb),
        "bones": len(source.data.bones),
        "actions": sorted(a.name for a in bpy.data.actions),
        "live_bones": len(target.data.bones),
    }

    out = Path(args.out)
    destination = out / "dmx" / "animation"
    destination.mkdir(parents=True, exist_ok=True)
    settings = scene.dmf
    settings.target_armature = target

    matched = [
        bone.name
        for bone in source.data.bones
        if bone.name in target.data.bones
        and not any(token in bone.name.lower() for token in ("iktarget", "root_motion", "muzzle"))
    ]
    rotation, scale = _frame_fix(source, target, matched)
    report["frame_fix"] = {
        "rotation_deg": round(math.degrees(rotation.angle), 2),
        "axis": tuple(round(v, 3) for v in rotation.axis),
        "scale": round(scale, 4),
    }

    standup = Matrix.Rotation(math.radians(args.standup), 4, "Y") @ ROOT_MOTION
    report["standup"] = {"degrees": args.standup, "axis": "Y", "base": "root_motion X+Z 1.5708"}

    for old_clip, new_clip in CLIP_MAP.items():
        summary = _retarget(
            source, target, old_clip, scene.render.fps, rotation, scale, standup, args.standup
        )
        entry = settings.clips.add()
        entry.name = f"{new_clip}.dmx"
        entry.label = new_clip
        entry.kind = "dmx"
        entry.action = summary["action"]
        entry.state = "IMPORTED"
        entry.ag = "AG2"
        entry.path = str(destination / f"{new_clip}.dmx")
        written = clipops.write_action(settings, entry, out, target=destination / f"{new_clip}.dmx")
        summary["written"] = str(written)
        summary["bytes"] = written.stat().st_size if written.is_file() else 0
        summary["new_clip"] = new_clip
        report["clips"].append(summary)
        report["written"].append(str(written))
        print(f"PORT {old_clip} -> {new_clip}: {summary['bytes']} bytes, {summary['frames']} frames, "
              f"{summary['matched_bones']} bones, scale {summary['scaled_bones']}")

    receipt = Path(args.report)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PORT OK {len(report['clips'])} clips -> {destination}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
