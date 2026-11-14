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


def _page_polls(context, panels) -> dict[str, dict[str, bool]]:
    settings = context.scene.dmf
    probe = {}
    for page in ("CLOTH", "SKELETON", "HANDOFF"):
        settings.props_page = page
        probe[page] = {name: bool(cls.poll(context)) for name, cls in panels.items()}
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
    ui_props = sys.modules["dmf_cloth_probe.ui_props"]

    _clear_scene()
    context = bpy.context
    settings = context.scene.dmf
    # ``hero_slug`` is an enum built by live detection; a probe has no live build,
    # so it leaves that alone and only points the import at the extraction.
    settings.body_dmx = str(body_dmx)
    settings.custom_collection = None

    outcome = bpy.ops.dmf.import_hero()
    armature = settings.target_armature
    check("hero-import", outcome == {"FINISHED"} and armature is not None, str(outcome))
    bones = len(armature.data.bones) if armature is not None else 0
    check("hero-bones", bones > 100, bones)

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

    chains = cloth_ops.scan_chains(settings)
    rows = list(settings.cloth_chains)
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

    panels = {
        "cloth": getattr(bpy.types, "DMF_PT_props_cloth", None),
        "skeleton": getattr(bpy.types, "DMF_PT_props_skeleton", None),
        "handoff": getattr(bpy.types, "DMF_PT_props_handoff", None),
        "root": getattr(bpy.types, "DMF_PT_props_main", None),
    }
    check("props-surface", all(panels.values()), sorted(name for name, cls in panels.items() if cls))
    polls = _page_polls(context, {k: v for k, v in panels.items() if v is not None})
    report["page_polls"] = polls
    check(
        "page-switches",
        polls["CLOTH"]["cloth"] and not polls["CLOTH"]["skeleton"]
        and polls["SKELETON"]["skeleton"] and not polls["SKELETON"]["cloth"]
        and polls["HANDOFF"]["handoff"] and not polls["HANDOFF"]["cloth"],
        polls,
    )
    mirror_ids = sorted(
        name for name in dir(bpy.types) if name.startswith("DMF_PT_props_") and name != "DMF_PT_props_main"
    )
    check("props-mirrors", len(mirror_ids) == len(ui_props.PAGE_BY_ID), {"mirrors": len(mirror_ids), "mapped": len(ui_props.PAGE_BY_ID)})
    sidebar_ids = sorted(name for name in dir(bpy.types) if name.startswith("DMF_PT_") and not name.startswith("DMF_PT_props_"))
    check("sidebar-still-registered", len(sidebar_ids) >= len(ui_props.PAGE_BY_ID), {"sidebar": len(sidebar_ids)})

    report["hero"] = {
        "armature": armature.name if armature else "",
        "bones": bones,
        "parts": vertices,
        "chains": chains,
    }
    report["failed"] = failed
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"CLOTH {'PASS' if not failed else 'FAIL'} {len(report['checks']) - len(failed)}/{len(report['checks'])} checks")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
