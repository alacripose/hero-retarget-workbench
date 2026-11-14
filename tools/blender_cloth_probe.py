"""Headless probe for the cloth suite and the properties-editor page surface.

  blender -b --python tools/blender_cloth_probe.py -- \
    --extraction "C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/datafiles/hero_retarget_workbench/artifacts/extractions/shiv" \
    --report artifacts/receipts/cloth.json

The probe imports a real hero extraction through the addon's own
``dmf.import_hero`` and checks what the addon promises: every mesh DMX beside the
body lands on the hero armature (Shiv's hair and jacket included), each part is
weighted to that armature, the skeleton's numbered bones group into chains, and
the properties-editor surface shows one page at a time.

It needs PulseSrcOps, so it runs with the owner's preferences rather than
``--factory-startup``, and it loads the addon from this checkout with any
installed copy disabled and ``forge`` unshadowed.

Without an extraction it reports SKIP and exits 0: CI has no game install, and a
probe that fails there would only teach us that the game is missing.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
if str(REPO) in sys.path:
    sys.path.remove(str(REPO))
sys.path.insert(0, str(REPO))
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")
DEFAULT_EXTRACTION = (
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
    / "shiv"
)


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", default=str(DEFAULT_EXTRACTION))
    parser.add_argument("--slug", default="shiv")
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "cloth.json"))
    parser.add_argument("--log", default=str(REPO / "artifacts" / "receipts" / "cloth.log"))
    return parser.parse_args(argv)


def _disable_installed_addon() -> list[str]:
    disabled = []
    for module in list(bpy.context.preferences.addons.keys()):
        if module == "dmf_cloth_probe" or not module.endswith("hero_retarget_workbench"):
            continue
        try:
            bpy.ops.preferences.addon_disable(module=module)
            disabled.append(module)
        except RuntimeError:
            continue
    return disabled


def _enable_pulse() -> str:
    if hasattr(bpy.types.Scene, "vs") and hasattr(bpy.ops.import_scene, "kst_dmx"):
        return "already enabled"
    for module in PULSE_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except RuntimeError:
            continue
        if hasattr(bpy.ops.import_scene, "kst_dmx"):
            return module
    raise RuntimeError(
        "pulse-src-ops-missing: enable the PulseSrcOps Blender extension before running this probe"
    )


def _unshadow_forge() -> dict[str, object]:
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
    for name in [name for name in sys.modules if name == "forge" or name.startswith("forge.")]:
        path = str(getattr(sys.modules[name], "__file__", "") or "")
        if "hero_retarget_workbench" in path:
            del sys.modules[name]
            dropped.append(name)
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))
    return {"path_entries": removed, "modules": dropped}


def _load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_cloth_probe",
        PACKAGE / "__init__.py",
        submodule_search_locations=[str(PACKAGE)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_cloth_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _rig_of(obj):
    """The armature a part is skinned to, by modifier or by parent."""
    for modifier in getattr(obj, "modifiers", []):
        if modifier.type == "ARMATURE" and modifier.object is not None:
            return modifier.object
    parent = obj.parent
    while parent is not None:
        if parent.type == "ARMATURE":
            return parent
        parent = parent.parent
    return None



def _weighted(obj, group) -> list[int]:
    if group is None:
        return []
    index = group.index
    found = []
    for vertex in obj.data.vertices:
        for element in vertex.groups:
            if element.group == index and element.weight > 0:
                found.append(vertex.index)
                break
    return found


def _scan_log(path: Path, markers: tuple[str, ...]) -> list[str]:
    """Python tracebacks in this run's own log that point at this addon."""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    found = []
    for index, line in enumerate(lines):
        if "Traceback (most recent call last)" in line:
            block = chr(10).join(lines[index : index + 40])
            if any(marker in block for marker in markers):
                found.append(lines[index : index + 6])
    return found


def _page_polls(context, panels) -> dict[str, dict[str, bool]]:
    settings = context.scene.dmf
    probe = {}
    for page in ("CLOTH", "SKELETON", "HANDOFF"):
        settings.props_page = page
        probe[page] = {}
        for name, cls in panels.items():
            poll = getattr(cls, "poll", None)
            probe[page][name] = bool(poll(context)) if callable(poll) else True
    settings.props_page = "CLOTH"
    return probe


def main() -> int:
    args = _arguments()
    extraction = Path(args.extraction)
    report: dict[str, object] = {
        "extraction": str(extraction),
        "checks": {},
        "receipt": str(args.report),
    }
    failed: list[str] = []

    def check(name: str, ok: bool, observed: object) -> None:
        report["checks"][name] = {"pass": bool(ok), "observed": observed}
        print(f"CLOTH {'PASS' if ok else 'FAIL'} {name}: {observed}")
        if not ok:
            failed.append(name)

    body_dmx = None
    for candidate in sorted(extraction.rglob(f"{args.slug}_body.dmx")):
        body_dmx = candidate
        break
    if body_dmx is None:
        report["skipped"] = f"no {args.slug}_body.dmx under {extraction}"
        print(f"CLOTH SKIP extraction not found: {extraction}")
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    report["disabled_installed_addons"] = _disable_installed_addon()
    report["pulse_src_ops"] = _enable_pulse()
    report["unshadowed"] = _unshadow_forge()
    _load_addon()
    forge_cloth = sys.modules.get("forge.cloth")
    report["forge_cloth"] = getattr(forge_cloth, "__file__", "")
    if forge_cloth is None or not Path(report["forge_cloth"]).resolve().is_relative_to(REPO):
        raise RuntimeError(f"forge-shadowed: forge.cloth came from {report['forge_cloth']}")
    cloth_ops = sys.modules["dmf_cloth_probe.cloth_ops"]
    from forge import cloth as clothscan

    ui_props = sys.modules["dmf_cloth_probe.ui_props"]
    ui_space = sys.modules["dmf_cloth_probe.ui_space"]

    _clear_scene()
    context = bpy.context
    settings = context.scene.dmf
    # ``hero_slug`` is an enum built by live detection; a probe has no live build,
    # so it leaves that alone and only points the import at the extraction.
    settings.body_dmx = str(body_dmx)
    settings.custom_collection = None

    outcome = bpy.ops.dmf.import_hero()
    parts = [row.object for row in settings.hero_parts if row.object is not None]
    names = sorted(obj.name for obj in parts)
    check("hero-parts", len(parts) >= 4, names)

    lowered = " ".join(names).lower()
    check("hair-imported", "hair" in lowered, [name for name in names if "hair" in name.lower()])
    check("jacket-imported", "jacket" in lowered, [name for name in names if "jacket" in name.lower()])

    rigs = {obj.name: _rig_of(obj) for obj in parts}
    unrigged = [name for name, rig in rigs.items() if rig is None or rig != armature]
    check("parts-on-hero-rig", not unrigged, {"unrigged": unrigged, "parts": len(parts)})

    vertices = {obj.name: len(obj.data.vertices) for obj in parts}
    body_vertices = len(settings.target_body.data.vertices) if settings.target_body else 0
    check(
        "part-geometry",
        all(count > 0 for count in vertices.values()) and sum(vertices.values()) > body_vertices,
        {"body": body_vertices, "parts": vertices, "total": sum(vertices.values())},
    )

    # No rescan here: the import already scanned the chains and built their
    # cloth, and rescanning would clear the built rows this probe checks.
    rows = list(settings.cloth_chains)
    chains = len(rows)
    cloth_like = [row.name for row in rows if row.count >= 2 and any(
        word in row.name.lower()
        for word in ("hair", "jacket", "coat", "cape", "skirt", "robe", "cloth", "sleeve", "scarf", "ribbon", "tail", "tassel", "hem", "veil", "apron", "belt", "strap")
    )]
    check("cloth-chains", chains >= 1, {"chains": chains, "cloth_like": cloth_like[:8]})
    check("cloth-chain-sample", bool(cloth_like) or chains > 0, [f"{row.name}:{row.count}" for row in rows[:8]])
    check(
        "chain-rows-record-bones",
        all(row.root and row.count >= 2 for row in rows) if rows else False,
        {"rows": len(rows), "first": rows[0].bones[:60] if rows else ""},
    )

    # The import itself must leave the cloth parts cloth-capable: these checks
    # run on the state a plain dmf.import_hero produces, with no manual build.
    cloth_rows = [row for row in settings.cloth_chains if clothscan.is_cloth(row.name)]
    built_rows = [row for row in cloth_rows if row.target_mesh is not None]
    report["cloth_rows"] = [
        {
            "chain": row.name,
            "mesh": getattr(row.target_mesh, "name", ""),
            "pin": row.pin_group,
            "modifier": row.cloth_modifier,
        }
        for row in built_rows
    ]
    built_chains = {row.name for row in built_rows}
    off_cloth = [row.name for row in built_rows if not clothscan.is_cloth(row.target_mesh.name)]
    check(
        "import-builds-cloth",
        bool(cloth_rows) and {"coat", "hair"} <= built_chains and not off_cloth,
        {"rows": report["cloth_rows"], "off_cloth": off_cloth, "skipped": settings.cloth_build_skipped},
    )

    part_rows = {}
    for row in built_rows:
        if row.target_mesh is not None:
            part_rows.setdefault(row.target_mesh.name, []).append(row)
    part_names = sorted(part_rows)
    check(
        "cloth-parts-covered",
        any("hair" in name.lower() for name in part_names)
        and any("jacket" in name.lower() for name in part_names),
        {name: [row.name for row in part_rows[name]] for name in part_names},
    )

    problems = []
    observed = {}
    for row in built_rows:
        obj = row.target_mesh
        if obj is None:
            problems.append(f"{row.name}: no mesh")
            continue
        pin = obj.vertex_groups.get(row.pin_group)
        pinned = len(_weighted(obj, pin)) if pin is not None else 0
        modifier = obj.modifiers.get(row.cloth_modifier)
        chain = row.chain_object
        chain_bones = list(chain.data.bones) if chain is not None and chain.type == "ARMATURE" else []
        order = [mod.type for mod in obj.modifiers]
        ordered = all(
            bone.parent is not None and bone.parent.name == chain_bones[index - 1].name
            for index, bone in enumerate(chain_bones)
            if index
        )
        observed[row.name] = {
            "mesh": obj.name,
            "pinned": pinned,
            "modifier": getattr(modifier, "name", ""),
            "order": order,
            "chain": getattr(chain, "name", ""),
            "chain_bones": [bone.name for bone in chain_bones],
            "modifier_pin": getattr(modifier.settings, "vertex_group_mass", ""),
        }
        if pinned <= 0:
            problems.append(f"{row.name}: pin group empty")
        if modifier is None or modifier.type != "CLOTH":
            problems.append(f"{row.name}: no cloth modifier")
        elif modifier.settings.vertex_group_mass not in obj.vertex_groups:
            problems.append(f"{row.name}: modifier pin group missing")
        else:
            shared = obj.vertex_groups[modifier.settings.vertex_group_mass]
            holds_chain = set(_weighted(obj, shared)) >= set(_weighted(obj, pin))
            if not holds_chain:
                problems.append(f"{row.name}: modifier pin does not hold this chain")
        if order[-2:] != ["ARMATURE", "CLOTH"]:
            problems.append(f"{row.name}: order {order}")
        if not chain_bones or not ordered:
            problems.append(f"{row.name}: chain bones not ordered")
    report["cloth_builds"] = observed
    check("import-cloth-setup", not problems, problems or observed)

    hair_rows = [row for row in built_rows if "hair" in (row.target_mesh.name if row.target_mesh else "").lower()]
    jacket_rows = [
        row for row in built_rows if "jacket" in (row.target_mesh.name if row.target_mesh else "").lower()
    ]
    check(
        "hair-cloth-built",
        bool(hair_rows) and len(hair_rows[0].target_mesh.data.vertices) > 0,
        {"mesh": hair_rows[0].target_mesh.name, "vertices": len(hair_rows[0].target_mesh.data.vertices), "chains": [r.name for r in hair_rows]} if hair_rows else "",
    )
    check(
        "jacket-cloth-built",
        bool(jacket_rows) and len(jacket_rows[0].target_mesh.data.vertices) > 0,
        {"mesh": jacket_rows[0].target_mesh.name, "vertices": len(jacket_rows[0].target_mesh.data.vertices), "chains": [r.name for r in jacket_rows]} if jacket_rows else "",
    )

    # Step real frames: structural setup is not simulation. The hero gets one
    # keyed spine rotation so pinned vertices have to follow a moving bone while
    # the free cloth solves under gravity.
    import math

    def _eval_coords(obj, depsgraph):
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        coords = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
        evaluated.to_mesh_clear()
        return coords

    scene = bpy.context.scene
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 12
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="POSE")
    pose_bone = None
    for candidate in ("spine_1", "spine_0", "pelvis", "root"):
        pose_bone = armature.pose.bones.get(candidate)
        if pose_bone is not None:
            break
    if pose_bone is not None:
        pose_bone.rotation_mode = "XYZ"
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
        pose_bone.keyframe_insert("rotation_euler", frame=scene.frame_start)
        pose_bone.rotation_euler = (0.2, 0.0, 0.3)
        pose_bone.keyframe_insert("rotation_euler", frame=scene.frame_end)
    bpy.ops.object.mode_set(mode="OBJECT")
    report["simulation"] = {"fps": scene.render.fps, "frames": [scene.frame_start, scene.frame_end],
                            "posed_bone": pose_bone.name if pose_bone else ""}

    cloth_meshes: dict[str, list] = {}
    for row in built_rows:
        cloth_meshes.setdefault(row.target_mesh.name, []).append(row)
    simulated: dict[str, dict] = {}
    for mesh_name, rows in cloth_meshes.items():
        obj = bpy.data.objects.get(mesh_name)
        modifier = next((mod for mod in obj.modifiers if mod.type == "CLOTH"), None) if obj else None
        pin_group = obj.vertex_groups.get(modifier.settings.vertex_group_mass) if modifier else None
        pinned = set(_weighted(obj, pin_group)) if pin_group is not None else set()
        diagonal = float(obj.dimensions.length) if obj is not None else 0.0
        scene.frame_set(scene.frame_start)
        bpy.context.view_layer.update()
        base = _eval_coords(obj, bpy.context.evaluated_depsgraph_get())
        pin_bone_name = rows[0].pin_bone
        pin_bone = armature.pose.bones.get(pin_bone_name)
        base_head = (armature.matrix_world @ pin_bone.head).copy() if pin_bone else None
        for frame in range(scene.frame_start + 1, scene.frame_end + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
        final = _eval_coords(obj, bpy.context.evaluated_depsgraph_get())
        head = (armature.matrix_world @ pin_bone.head).copy() if pin_bone else None
        drift = 0.0
        if pinned and base_head is not None:
            drift = max(((final[index] - head) - (base[index] - base_head)).length for index in pinned)
        free = [index for index in range(len(base)) if index not in pinned]
        displacement = max((final[index] - base[index]).length for index in free) if free else 0.0
        finite = all(math.isfinite(component) for vector in final for component in vector)
        simulated[mesh_name] = {
            "chain": rows[0].name,
            "vertices": len(base),
            "pinned": len(pinned),
            "pin_bone": pin_bone_name,
            "pin_drift_max": round(drift, 6),
            "free_displacement_max": round(displacement, 6),
            "mesh_diagonal": round(diagonal, 4),
            "finite": finite,
            "modifier_order": [mod.type for mod in obj.modifiers],
            "cloth_modifier": modifier.name if modifier else "",
        }
    report["simulation"]["meshes"] = simulated
    check("cloth-simulates", bool(simulated) and all(v["free_displacement_max"] > 1e-4 and v["finite"] for v in simulated.values()), simulated)
    check("cloth-pins-hold", bool(simulated) and all(v["pin_drift_max"] <= 0.02 for v in simulated.values()), {name: value["pin_drift_max"] for name, value in simulated.items()})
    check("cloth-stays-bounded", bool(simulated) and all(v["free_displacement_max"] <= 2.5 for v in simulated.values()), {name: value["free_displacement_max"] for name, value in simulated.items()})
    check("cloth-order-after-sim", bool(simulated) and all(v["modifier_order"][-2:] == ["ARMATURE", "CLOTH"] for v in simulated.values()), {name: value["modifier_order"] for name, value in simulated.items()})

    addon_module = sys.modules["dmf_cloth_probe"]
    surface = getattr(addon_module, "SURFACE", "properties")
    prefix = "space" if surface == "editor" else "props"
    report["surface"] = surface
    report["import_status"] = settings.status
    report["cloth_skipped"] = settings.cloth_build_skipped
    print(f"CLOTH import status: {settings.status}", flush=True)
    panels = {
        "cloth": getattr(bpy.types, f"DMF_PT_{prefix}_cloth", None),
        "skeleton": getattr(bpy.types, f"DMF_PT_{prefix}_skeleton", None),
        "handoff": getattr(bpy.types, f"DMF_PT_{prefix}_handoff", None),
        "root": getattr(bpy.types, f"DMF_PT_{prefix}_main", None),
    }
    check("page-surface", all(panels.values()), {"surface": surface, "panels": sorted(name for name, cls in panels.items() if cls)})
    polls = _page_polls(context, {k: v for k, v in panels.items() if v is not None})
    report["page_polls"] = polls
    check(
        "surface-matches-build",
        surface == ("editor" if ui_space.custom_space_supported() else "properties"),
        {"surface": surface, "custom_space_supported": ui_space.custom_space_supported()},
    )
    check(
        "page-switches",
        polls["CLOTH"]["cloth"] and not polls["CLOTH"]["skeleton"]
        and polls["SKELETON"]["skeleton"] and not polls["SKELETON"]["cloth"]
        and polls["HANDOFF"]["handoff"] and not polls["HANDOFF"]["cloth"],
        polls,
    )
    mirror_prefix = f"DMF_PT_{prefix}_"
    mirror_ids = sorted(
        name
        for name in dir(bpy.types)
        if name.startswith(mirror_prefix) and name != f"DMF_PT_{prefix}_main"
    )
    check("page-twins", len(mirror_ids) == len(ui_props.PAGE_BY_ID), {"twins": len(mirror_ids), "mapped": len(ui_props.PAGE_BY_ID)})
    sidebar_ids = sorted(
        name
        for name in dir(bpy.types)
        if name.startswith("DMF_PT_")
        and not name.startswith(mirror_prefix)
        and name != "DMF_PT_main"
        and not name.startswith("DMF_PT_props_")
        and not name.startswith("DMF_PT_space_")
    )
    check("sidebar-still-registered", len(sidebar_ids) >= len(ui_props.PAGE_BY_ID), {"sidebar": len(sidebar_ids)})

    report["hero"] = {
        "armature": armature.name if armature else "",
        "bones": bones,
        "parts": vertices,
        "chains": chains,
    }
    log_path = Path(args.log)
    addon_tracebacks = _scan_log(log_path, ("hero_retarget_workbench", "dmf_cloth_probe"))
    report["log"] = {"path": str(log_path), "scanned": log_path.is_file(), "addon_tracebacks": addon_tracebacks}
    check("log-without-addon-exceptions", not addon_tracebacks, addon_tracebacks or "clean")
    report["failed"] = failed
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"CLOTH {'PASS' if not failed else 'FAIL'} {len(report['checks']) - len(failed)}/{len(report['checks'])} checks")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
