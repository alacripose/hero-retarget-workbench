"""Render clip poses from four sides, one figure per image, shared camera scale.

Numbers cannot show a tail hanging off the body, a mesh collapsing at a joint or
arms sitting visibly off-pose, so this renders them.  Two traps shaped the shape
of this probe:

* Two rigs in one scene get their bones merged by the DMX importer's "Bone Append
  Mode: Validate", so each side is rendered on its own.
* The importer applies its own root-motion axis fixup per file, so the same rig
  can end up facing a different way for the shipped clip than for the game's.
  Rather than guess a facing, every side is rendered from four cardinal
  directions with one fixed orthographic scale, and the tiling script puts the
  matching views next to each other.

  blender -b --python tools/pose_compare_probe.py -- --mesh <mesh.dmx> \
      --pose idle:40:<ours.dmx>:<game.dmx> [--pose ...] [--rest] \
      --outdir artifacts/visual/<run> [--ortho 150] [--report <json>]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

REPO = Path(__file__).resolve().parents[1]
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")
VIEWS = (0, 90, 180, 270)


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--pose", action="append", default=[], help="label:frame:ours.dmx:game.dmx")
    parser.add_argument("--rest", action="store_true")
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--resolution", default="640x760")
    parser.add_argument("--ortho", type=float, default=150.0)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "pose-compare.json"))
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


def _clear() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _import_rig(path: Path):
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE")
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not rigs:
        raise RuntimeError(f"no armature in {path}")
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    return rigs[-1], meshes


def _append_action(path: Path, rig):
    rig.animation_data_create()
    rig.animation_data.action = None
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    before_actions = {action.name for action in bpy.data.actions}
    before_objects = set(bpy.context.scene.objects)
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before_actions]
    for obj in [obj for obj in bpy.context.scene.objects if obj not in before_objects]:
        bpy.data.objects.remove(obj, do_unlink=True)
    if not created:
        raise RuntimeError(f"no action from {path}")
    action = created[-1]
    rig.animation_data.action = action
    if getattr(action, "slots", None):
        rig.animation_data.action_slot = action.slots[0]
    return action


def _bounds(meshes):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        matrix = evaluated.matrix_world
        for vertex in mesh.vertices:
            world = matrix @ vertex.co
            lo = Vector((min(lo[i], world[i]) for i in range(3)))
            hi = Vector((max(hi[i], world[i]) for i in range(3)))
        evaluated.to_mesh_clear()
    return lo, hi


def _camera(centre: Vector, ortho: float, yaw_degrees: int):
    camera_data = bpy.data.cameras.new(f"cam{yaw_degrees}")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = ortho
    camera = bpy.data.objects.new(f"cam{yaw_degrees}", camera_data)
    distance = max(ortho * 3.0, 200.0)
    angle = math.radians(yaw_degrees)
    camera.location = (
        centre.x + math.sin(angle) * distance,
        centre.y - math.cos(angle) * distance,
        centre.z,
    )
    camera.rotation_euler = (math.pi / 2.0, 0.0, angle)
    bpy.context.scene.collection.objects.link(camera)
    return camera


def main() -> int:
    args = _arguments()
    _enable_pulse()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    width, height = (int(value) for value in args.resolution.split("x"))

    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "SINGLE"
    shading.show_shadows = True
    shading.show_cavity = True

    report: dict[str, object] = {"mesh": str(args.mesh), "ortho": args.ortho, "renders": [], "failed": []}
    report_path = Path(args.report)

    def write_report() -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def shoot(label: str, side: str, frame: int, clip: str) -> None:
        _clear()
        rig, meshes = _import_rig(Path(args.mesh))
        action = None
        if clip:
            action = _append_action(Path(clip), rig)
            scene.frame_set(frame)
        bpy.context.view_layer.update()
        lo, hi = _bounds(meshes)
        centre = Vector(((lo.x + hi.x) * 0.5, (lo.y + hi.y) * 0.5, (lo.z + hi.z) * 0.5))
        views = []
        for yaw in VIEWS:
            camera = _camera(centre, args.ortho, yaw)
            scene.camera = camera
            png = outdir / f"{label}-{side}-{yaw:03d}.png"
            scene.render.filepath = str(png)
            bpy.ops.render.render(write_still=True)
            views.append({"yaw": yaw, "png": str(png), "bytes": png.stat().st_size})
        report["renders"].append(
            {
                "label": label,
                "side": side,
                "frame": frame,
                "clip": clip,
                "action": action.name if action else None,
                "bounds": {"lo": [round(v, 2) for v in lo], "hi": [round(v, 2) for v in hi]},
                "views": views,
            }
        )
        print(
            f"POSE-RENDER {label}-{side} frame {frame} z[{lo.z:.1f},{hi.z:.1f}] "
            f"x[{lo.x:.1f},{hi.x:.1f}] y[{lo.y:.1f},{hi.y:.1f}]",
            flush=True,
        )

    if args.rest:
        try:
            shoot("rest", "shipped", 0, "")
        except Exception as error:
            report["failed"].append({"label": "rest", "why": f"{type(error).__name__}: {error}"})
            print(f"POSE-RENDER FAIL rest: {error}", flush=True)
        write_report()

    for pose in args.pose:
        label, frame_text, ours, game = (part.strip() for part in pose.split(":", 3))
        for side, clip in (("shipped", ours), ("game", game)):
            try:
                shoot(label, side, int(float(frame_text)), clip)
            except Exception as error:
                report["failed"].append({"label": label, "side": side, "why": f"{type(error).__name__}: {error}"})
                print(f"POSE-RENDER FAIL {label}-{side}: {error}", flush=True)
            write_report()
    print(f"POSE-RENDER done {len(report['renders'])} figures, {len(report['failed'])} failed", flush=True)
    return 0 if report["renders"] and not report["failed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
