"""Add a tail from scratch to a hero that has none, through the addon's own pass.

The Shiv work was hand-carved: a skeleton was exported from a rig, a tail chain was
appended to clip DMX by a standalone tool, and every step was measured separately.
That path lost track of which convention (track count, root rest, joint order) the
shipped build depended on. This tool runs the feature the addon actually ships —
import a hero, import its clips, discover a tail source from another hero, append
its bones and key its motion into every imported action, then write the clips out —
so a port that has no history behind it can be compared with Shiv.

    blender -b --factory-startup --python-exit-code 1 \
        --python tools/tail_port_build.py -- \
        --extraction artifacts/ports/haze_tac9/new-live \
        --tail werewolf --clips aim_weapon_idle,item_run_center,item_stand_idle \
        --out artifacts/haze-tail/clips --report artifacts/receipts/tail-port-haze.json
"""

from __future__ import annotations
import os

import argparse
import addon_utils
import importlib.util
import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = ROOT / "blender"
PACKAGE = "dmf_tail_port"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", required=True)
    parser.add_argument("--tail", required=True, help="substring of the tail source label")
    parser.add_argument("--clips", default="", help="comma separated clip labels; empty means every clip")
    parser.add_argument(
        "--tail-skeletons",
        default="",
        help="comma separated skeleton DMX files to discover tails from (no live scan)",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--game-skeleton",
        default="",
        help="the hero's own animation skeleton DMX; author and compile on it plus the tail",
    )
    parser.add_argument(
        "--compile-addon",
        default="",
        help="CSDK13 content addon name; stages the hero plus the edited clip and compiles it",
    )
    return parser.parse_args(argv)


def unshadow_forge() -> dict:
    removed = []
    for entry in list(sys.path):
        try:
            candidate = Path(entry)
        except (TypeError, ValueError):
            continue
        if candidate.name == "hero_retarget_workbench" or (
            candidate / "hero_retarget_workbench" / "forge"
        ).is_dir():
            sys.path.remove(entry)
            removed.append(entry)
    dropped = []
    for name in [n for n in sys.modules if n == "forge" or n.startswith("forge.")]:
        if "hero_retarget_workbench" in str(getattr(sys.modules[name], "__file__", "") or ""):
            del sys.modules[name]
            dropped.append(name)
    if str(ROOT) in sys.path:
        sys.path.remove(str(ROOT))
    sys.path.insert(0, str(ROOT))
    return {"path_entries": removed, "modules": dropped}


def load_addon():
    package = ADDON_ROOT / "hero_retarget_workbench"
    spec = importlib.util.spec_from_file_location(
        PACKAGE, package / "__init__.py", submodule_search_locations=[str(package)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def disable_installed():
    disabled = []
    for name in list(bpy.context.preferences.addons.keys()):
        if name.endswith("hero_retarget_workbench"):
            try:
                bpy.ops.preferences.addon_disable(module=name)
                disabled.append(name)
            except RuntimeError:
                continue
    return disabled


def main() -> int:
    args = parse_args()
    extraction = Path(args.extraction).resolve()
    out = Path(args.out)
    report_path = Path(args.report)
    report: dict = {
        "probe": "tail-port",
        "extraction": str(extraction),
        "tail_source_query": args.tail,
        "checks": {},
        "errors": [],
    }

    report["disabled_installed"] = disable_installed()
    report["unshadowed"] = unshadow_forge()
    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    load_addon()
    tailops = sys.modules[f"{PACKAGE}.tailops"]
    clipops = sys.modules[f"{PACKAGE}.clipops"]
    settings = bpy.context.scene.dmf

    settings.extraction_dir = str(extraction)
    bodies = sorted(extraction.rglob("*body*.dmx"))
    if not bodies:
        bodies = sorted(extraction.rglob("*.dmx"))
    if not bodies:
        raise SystemExit(f"no body dmx under {extraction}")
    settings.body_dmx = str(bodies[0])
    bpy.ops.dmf.import_hero()
    hero = settings.target_armature
    game_rig = None
    if args.game_skeleton:
        # The body DMX carries only the bones the mesh is skinned to (120 here).  The
        # hero's own animation skeleton names more (weaponHand_L/R and friends), and a
        # skeleton built from the body rig makes the client drop every bone mask that
        # mentions them and crash after the hero loads.  Author the clips on the
        # game's skeleton, then append the tail to it.
        source2 = importlib.import_module(f"{PACKAGE}.source2")
        before = {obj.name for obj in bpy.context.scene.objects}
        source2.import_dmx(Path(args.game_skeleton), append="NEW_ARMATURE")
        new = [
            obj
            for obj in bpy.context.scene.objects
            if obj.name not in before and obj.type == "ARMATURE"
        ]
        if not new:
            raise SystemExit(f"game skeleton did not import: {args.game_skeleton}")
        game_rig = max(new, key=lambda obj: len(obj.data.bones))
        settings.target_armature = game_rig
    report["checks"]["game_skeleton"] = str(args.game_skeleton)
    report["checks"]["authored_on"] = game_rig.name if game_rig else (hero.name if hero else "")
    report["checks"]["hero"] = hero.name if hero else ""
    report["checks"]["body"] = settings.body_dmx
    report["checks"]["bones"] = len(hero.data.bones) if hero else 0
    if hero is None:
        report["errors"].append("hero did not import")
        write(report_path, report)
        return 1

    wanted = [name.strip().lower() for name in args.clips.split(",") if name.strip()]
    # The clip list holds both the editable DMX and the compiled document beside
    # it; only the DMX can be imported (the compiled one answers "Format of
    # <clip>.vnmclip not recognised").
    rows = [
        row
        for row in settings.clips
        if row.path.lower().endswith(".dmx") and (not wanted or row.label.lower() in wanted)
    ]
    if args.limit:
        rows = rows[: args.limit]
    imported = []
    for row in rows:
        clipops._import_one(settings, row)
        print(f"PORT import {row.label}: {row.state} {row.action!r}", flush=True)
        if row.state == "IMPORTED" and row.action:
            imported.append(row.label)
    report["checks"]["imported"] = imported
    if not imported:
        report["errors"].append("no clip imported")
        write(report_path, report)
        return 1

    live_files = [Path(part.strip()) for part in args.tail_skeletons.split(",") if part.strip()]
    tailops.discover(settings, live_files=live_files)
    options = [
        (index, option)
        for index, option in enumerate(settings.tail_options)
        if args.tail.lower() in option.label.lower() and option.count
    ]
    if not options:
        report["errors"].append(
            "no tail source matching "
            f"{args.tail!r}; saw {[option.label for option in settings.tail_options][:12]}"
        )
        write(report_path, report)
        return 1
    index, option = options[0]
    settings.tail_option_index = index
    report["checks"]["tail_source"] = option.label
    report["checks"]["tail_source_path"] = option.path
    report["checks"]["tail_source_bones"] = int(option.count)

    tailops.start_auto(settings, schedule=False)
    guard = 0
    while tailops._AUTO_QUEUE and guard < 200000:
        tailops._auto_tick()
        guard += 1
    report["checks"]["updated"] = getattr(tailops, "_AUTO_UPDATED", 0)
    report["checks"]["skipped"] = getattr(tailops, "_AUTO_SKIPPED", 0)
    report["checks"]["failed"] = getattr(tailops, "_AUTO_FAILED", 0)
    report["checks"]["tail_note"] = settings.tail_note

    rig = game_rig or hero
    hero_tail = [name for name in tailops._tail_names(settings.tail_armature) if rig.data.bones.get(name)]
    report["checks"]["hero_bones_after"] = len(rig.data.bones)
    report["checks"]["hero_tail_bones"] = hero_tail
    if len(hero_tail) < 5:
        report["errors"].append(f"hero carries only {len(hero_tail)} tail bones")

    out.mkdir(parents=True, exist_ok=True)
    written = []
    motion = {}
    for row in settings.clips:
        if row.label not in imported:
            continue
        action = bpy.data.actions.get(row.action or "")
        if action is None:
            report["errors"].append(f"{row.label}: action missing")
            continue
        bones = sorted(tailops._action_bones(action) & set(hero_tail))
        if not bones:
            report["errors"].append(f"{row.label}: no tail keys")
            continue
        start, end = (int(round(value)) for value in action.frame_range)
        data = rig.animation_data or rig.animation_data_create()
        data.action = action
        if hasattr(data, "action_slot") and getattr(action, "slots", None):
            data.action_slot = action.slots[0]
        samples = []
        for frame in (start, start + (end - start) // 2, end):
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            bone = rig.pose.bones.get(bones[0])
            samples.append(tuple(round(v, 6) for r in bone.matrix_basis for v in r) if bone else ())
        motion[row.label] = {"bones": len(bones), "moves": len(set(samples)) > 1, "frames": [start, end]}
        target = clipops.write_action(settings, row, out, target=out / f"{row.label}.dmx")
        written.append({"clip": row.label, "bytes": target.stat().st_size})
    report["checks"]["written"] = written
    report["checks"]["tail_motion"] = motion
    moving = [name for name, row in motion.items() if row["moves"]]
    report["checks"]["moving"] = moving
    if not moving:
        report["errors"].append("no written clip's tail moves")

    if args.compile_addon:
        try:
            stage_compile(
                report, args, settings, tailops, hero, extraction, out, imported
            )
        except Exception as error:  # a staging failure must not lose the port receipt
            import traceback

            report["errors"].append(f"compile: {type(error).__name__}: {error}")
            report["compile_traceback"] = traceback.format_exc()[-2000:]
    report["ok"] = not report["errors"]
    write(report_path, report)
    print(json.dumps(report["checks"], indent=2)[:4000], flush=True)
    return 0 if report["ok"] else 1


def stage_compile(report, args, settings, tailops, hero, extraction, out, imported) -> None:
    """Stage the hero with its tailed skeleton and compile the edited clip."""
    import shutil

    importlib.import_module(f"{PACKAGE}.core")
    from forge import animgraph

    core = sys.modules[f"{PACKAGE}.core"]
    checks = report["checks"]
    cdk = Path(os.path.expanduser("~/Downloads/Reduced_CSDK_13"))
    content_addon = cdk / "content" / "citadel_addons" / args.compile_addon
    rows = [row for row in settings.clips if row.label in imported and row.path]
    if not rows:
        report["errors"].append("compile: no imported row carries a path")
        return
    hero_root = Path(rows[0].path).parent.parent
    hero_dir = hero_root.relative_to(extraction)
    wanted = {(label or "").lower() for label in imported}
    docs = [doc for doc in animgraph.documents(hero_root, extraction) if doc.label.lower() in wanted]
    checks["compile_docs"] = [doc.label for doc in docs]
    if not docs:
        report["errors"].append("compile: no clip document matched the imported clips")
        return
    checks["hero_root"] = str(hero_root)
    body_mesh = max(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
        key=lambda obj: len(obj.data.vertices),
        default=None,
    )
    tail_names = tailops._tail_names(settings.tail_armature)
    skeleton = out / hero_dir / "dmx" / "mesh" / f"{hero_root.name}_tailbones.dmx"
    skeleton.parent.mkdir(parents=True, exist_ok=True)
    # The compiler's skeleton document must contain joints only.  Passing the body
    # mesh embeds a 14.9 MB geometry block that the compiler answers as
    # "Load error: dmx/mesh/<hero>_tailbones.dmx" and the clip then fails against
    # a skeleton that was never built.
    tailops.export_tail_skeleton(
        settings, skeleton, base_path=Path(args.game_skeleton) if args.game_skeleton else None
    )
    checks["skeleton"] = str(skeleton)
    originals = sorted(hero_root.glob("*.vnmskel"))
    if not originals:
        report["errors"].append("compile: the extraction has no .vnmskel document")
        return
    original = originals[0]
    prepared = animgraph.prepare_skeleton(
        original.read_text(encoding="utf-8", errors="replace"),
        skeleton.relative_to(out / hero_dir).as_posix(),
        tail_names,
    )
    skeleton_doc = out / original.relative_to(extraction)
    skeleton_doc.parent.mkdir(parents=True, exist_ok=True)
    skeleton_doc.write_text(prepared, encoding="utf-8")
    for source, base in (
        (hero_root / f"{hero_root.name}.vmdl", extraction),
        (skeleton, out),
        (skeleton_doc, out),
    ):
        if not source.is_file():
            report["errors"].append(f"compile: missing {source}")
            return
        target = content_addon / source.relative_to(base)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # The compiler resolves the skeleton document's m_sourceFilename from the content
    # addon root, so the DMX has to exist there as well as beside the hero.
    root_copy = content_addon / "dmx" / "mesh" / skeleton.name
    root_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(skeleton, root_copy)
    for doc in docs:
        edited = out / f"{doc.label}.dmx"
        if not edited.is_file():
            report["errors"].append(f"compile: the port wrote no {edited.name}")
            return
        for source, relative in (
            (doc.vnmclip, doc.vnmclip.relative_to(extraction)),
            (edited, doc.source.relative_to(extraction)),
        ):
            target = content_addon / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    staged = animgraph.documents(content_addon / hero_dir, content_addon)
    staged = [doc for doc in staged if doc.label.lower() in wanted]
    outcomes = animgraph.compile_documents(
        core.env(settings), content_addon, staged, log_dir=Path("logs") / "haze-tail"
    )
    failed = [row for row in outcomes if row.returncode]
    checks["compiled"] = len(outcomes) - len(failed)
    checks["compile_failed"] = [
        getattr(row, "label", None) or getattr(row, "document", None) or repr(row)
        for row in failed
    ]
    checks["content_addon"] = str(content_addon)
    if failed:
        report["errors"].append(f"compile: {len(failed)} document(s) failed")


def write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2)[:4000], flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
