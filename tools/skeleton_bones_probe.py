"""List the bones of a decompiled ``.vnmskel`` so two skeletons can be compared.

Source 2 resolves a bone mask by bone name against a skeleton resource, so a
mask that names a bone the skeleton does not carry is a load-time warning and
the bone is simply missing from that mask.  The name table in a compiled
``.vnmskel`` is not a bone list (it also carries component and attribute names),
so the only honest way to answer "does this skeleton have this bone" is to
import it and read the armature.

  blender -b --python tools/skeleton_bones_probe.py -- --a <skel> [--b <skel>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", default="")
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "skeleton-bones.json"))
    parser.add_argument("--watch", default="")
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


def _bones(path: Path) -> list[str]:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE")
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not rigs:
        return []
    rig = rigs[-1]
    return [bone.name for bone in rig.data.bones]


def main() -> int:
    args = _arguments()
    _enable_pulse()
    first = _bones(Path(args.a))
    report: dict[str, object] = {"a": {"path": args.a, "count": len(first), "bones": first}}
    watched = [name.strip() for name in args.watch.split(",") if name.strip()]
    if watched:
        report["watch"] = {name: name in first for name in watched}
    code = 0
    if args.b:
        second = _bones(Path(args.b))
        only_a = [name for name in first if name not in set(second)]
        only_b = [name for name in second if name not in set(first)]
        report["b"] = {"path": args.b, "count": len(second), "bones": second}
        report["only_a"] = only_a
        report["only_b"] = only_b
        if watched:
            report["watch_b"] = {name: name in set(second) for name in watched}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k not in ("a", "b")}, indent=2))
    print(f"SKEL-A {len(first)} bones")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:  # a probe that fails silently reads as a pass
        import traceback

        traceback.print_exc()
        raise SystemExit(1)
