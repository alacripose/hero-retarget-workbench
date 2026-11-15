"""Diff two animation DMX files at the track level, not at the byte level.

A byte diff cannot tell a tail sample apart from a body change: the merged Shiv
DMX files are the same size and differ in ~31 KB of low-order float bytes spread
over thousands of one-byte runs.  This imports each clip on its own clean scene
and compares every fcurve by ``(bone, property, axis)``, so a difference is
reported as a bone name with a number.

  blender -b --python tools/dmx_track_diff_probe.py -- \
      --a <clip.dmx> --b <other.dmx> --report <json> [--tolerance 1e-5]
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from action_curves import action_fcurves  # noqa: E402
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--tolerance", type=float, default=1e-5)
    parser.add_argument(
        "--watch",
        default="",
        help="comma separated bone names whose per-frame values are copied into the report, e.g. pelvis,tail_0",
    )
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "dmx-track-diff.json"))
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


def _bone_of(curve) -> str:
    path = curve.data_path
    if 'pose.bones["' in path:
        return path.split('pose.bones["', 1)[1].split('"]', 1)[0]
    if curve.group is not None:
        return curve.group.name
    return path


def _dump(path: Path) -> dict:
    _clear()
    bpy.context.scene.render.fps = 30
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE")
    actions = list(bpy.data.actions)
    if not actions:
        raise RuntimeError(f"no action in {path}")
    action = actions[-1]
    tracks: dict[str, dict] = {}
    for curve in action_fcurves(action):
        key = f'{_bone_of(curve)}|{curve.data_path.rsplit(".", 1)[-1]}|{curve.array_index}'
        tracks[key] = {
            str(round(point.co[0], 4)): round(float(point.co[1]), 7) for point in curve.keyframe_points
        }
    return {"path": str(path), "action": action.name, "frames": list(action.frame_range), "tracks": tracks}


def main() -> int:
    args = _arguments()
    _enable_pulse()
    a = _dump(Path(args.a))
    b = _dump(Path(args.b))
    keys = sorted(set(a["tracks"]) | set(b["tracks"]))
    tolerance = float(args.tolerance)
    differing: dict[str, dict] = {}
    for key in keys:
        ta = a["tracks"].get(key)
        tb = b["tracks"].get(key)
        if ta is None or tb is None:
            bone, prop, axis = key.split("|")
            differing.setdefault(bone, {"only_in": set(), "max_delta": None})["only_in"].add(
                f"{prop}[{axis}] in {'b' if ta is None else 'a'}"
            )
            continue
        worst = 0.0
        worst_frame = None
        for frame, value in ta.items():
            other = tb.get(frame)
            if other is None:
                continue
            delta = abs(value - other)
            if delta > worst:
                worst, worst_frame = delta, frame
        if worst > tolerance:
            bone, prop, axis = key.split("|")
            row = differing.setdefault(
                bone, {"only_in": set(), "max_delta": 0.0, "channels": [], "worst_frame": None, "max_delta_total": 0.0}
            )
            row["channels"].append(f"{prop}[{axis}]")
            row["max_delta_total"] = max(row.get("max_delta_total") or 0.0, worst)
            if row["max_delta"] is None or worst > (row["max_delta"] or 0.0):
                row["max_delta"] = worst
                row["worst_frame"] = worst_frame
    for row in differing.values():
        row["only_in"] = sorted(row["only_in"])
        row["channels"] = sorted(row.get("channels") or [])
    bones = sorted(differing)
    report = {
        "a": {"path": a["path"], "action": a["action"], "frames": a["frames"], "tracks": len(a["tracks"])},
        "b": {"path": b["path"], "action": b["action"], "frames": b["frames"], "tracks": len(b["tracks"])},
        "tolerance": tolerance,
        "bones_with_differences": bones,
        "bones_total": len({key.split("|")[0] for key in keys}),
        "differences": differing,
    }
    watched = [name.strip() for name in args.watch.split(",") if name.strip()]
    if watched:
        series: dict[str, dict] = {}
        for bone in watched:
            for key in keys:
                if not key.startswith(f"{bone}|"):
                    continue
                series.setdefault(bone, {})[key] = {
                    "a": a["tracks"].get(key),
                    "b": b["tracks"].get(key),
                }
        report["watched"] = series
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, default=sorted) + "\n", encoding="utf-8")
    print(f"TRACKDIFF bones_total={report['bones_total']} differing={len(bones)}", flush=True)
    for bone in bones:
        row = differing[bone]
        print(
            f"  {bone}: max {row.get('max_delta')} at frame {row.get('worst_frame')} "
            f"channels={row.get('channels')} only_in={row.get('only_in')}",
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
