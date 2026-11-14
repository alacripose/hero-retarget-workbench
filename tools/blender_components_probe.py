"""Exercise the Components page scan on hero and non-hero extractions.

  blender --factory-startup --python tools/blender_components_probe.py -- \
    --report artifacts/receipts/components.json

The probe uses a non-hero NPC extraction beside a stale hero extraction.  It
checks that the scan follows the imported body and its vmdl, lists the model's
render meshes, leaves the primary body unselected, and still finds components on
a WIP hero with generic part names.  It does not stage or compile anything.
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
DEFAULT_EXTRACTIONS = (
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
RESULT: dict = {"checks": {}, "failed": []}


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--extractions", default=str(DEFAULT_EXTRACTIONS))
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "components.json"))
    return parser.parse_args(argv)


def disable_installed() -> list[str]:
    disabled = []
    for module in list(bpy.context.preferences.addons.keys()):
        if module.endswith("hero_retarget_workbench"):
            try:
                bpy.ops.preferences.addon_disable(module=module)
                disabled.append(module)
            except RuntimeError:
                continue
    return disabled


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
    for name in [name for name in sys.modules if name == "forge" or name.startswith("forge.")]:
        if "hero_retarget_workbench" in str(getattr(sys.modules[name], "__file__", "") or ""):
            del sys.modules[name]
            dropped.append(name)
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))
    return {"path_entries": removed, "modules": dropped}


def load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_components_probe",
        PACKAGE / "__init__.py",
        submodule_search_locations=[str(PACKAGE)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_components_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def check(name: str, ok: bool, observed) -> None:
    RESULT["checks"][name] = {"pass": bool(ok), "observed": observed}
    if not ok:
        RESULT["failed"].append(name)
    print(f"COMPONENTS {'PASS' if ok else 'FAIL'} {name}: {observed}", flush=True)


def finish() -> None:
    code = 0 if not RESULT["failed"] else 1
    RESULT["summary"] = (
        f"{sum(1 for item in RESULT['checks'].values() if item['pass'])}/{len(RESULT['checks'])} checks"
    )
    target = Path(RESULT["report"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(RESULT, indent=2), encoding="utf-8")
    print(f"COMPONENTS FINISH {RESULT['summary']} {target}", flush=True)
    raise SystemExit(code)


def main() -> int:
    args = arguments()
    RESULT["report"] = str(Path(args.report).resolve())
    extractions = Path(args.extractions)
    midboss = extractions / "npc__midboss__midboss__midboss"
    midboss_body = next(iter(sorted(midboss.rglob("midboss_unnamed_1.dmx"))), None)
    midboss_vmdl = next(iter(sorted(midboss.rglob("midboss.vmdl"))), None)
    familiar = extractions / "familiar"
    familiar_body = next(iter(sorted(familiar.rglob("*body8.dmx"))), None)
    familiar_vmdl = next(iter(sorted(familiar.rglob("familiar_wip.vmdl"))), None)
    shiv = extractions / "shiv"
    shiv_vmdl = next(iter(sorted(shiv.rglob("shiv.vmdl"))), None)
    if not all((midboss_body, midboss_vmdl, familiar_body, familiar_vmdl, shiv_vmdl)):
        RESULT["skipped"] = str(extractions)
        finish()
    RESULT.update(
        {
            "extractions": str(extractions),
            "midboss_body": str(midboss_body),
            "familiar_body": str(familiar_body),
        }
    )
    RESULT["disabled_installed_addons"] = disable_installed()
    RESULT["unshadowed"] = unshadow_forge()
    load_addon()
    settings = bpy.context.scene.dmf

    # The page still holds the previous Shiv extraction and vmdl.  The imported
    # NPC body must win, or the scan reports the old hero's guns.
    settings.extraction_dir = str(shiv)
    settings.vmdl = str(shiv_vmdl)
    settings.body_dmx = str(midboss_body)
    result = bpy.ops.dmf.scan_components()
    rows = list(settings.components)
    check("midboss-scan-finishes", result == {"FINISHED"}, str(result))
    check("midboss-uses-body-vmdl", len(rows) == 1, [(row.name, row.relative) for row in rows])
    check("midboss-primary-unselected", bool(rows) and not rows[0].selected, rows[0].selected if rows else None)
    check("midboss-note", "no separate components" in settings.component_note, settings.component_note)

    settings.extraction_dir = str(familiar)
    settings.vmdl = str(familiar_vmdl)
    settings.body_dmx = str(familiar_body)
    result = bpy.ops.dmf.scan_components()
    rows = list(settings.components)
    selected = [row.name for row in rows if row.selected]
    primary = [row.name for row in rows if not row.selected and row.kind == "dmx"]
    check("familiar-scan-finishes", result == {"FINISHED"}, str(result))
    check("familiar-components-found", len(selected) >= 5, selected)
    check("familiar-body-unselected", "familiar_wip_8inf_body8.dmx" in primary, primary)
    check("familiar-generic-part", "familiar_wip_weapon2.dmx" in selected, selected)
    check("familiar-note", "components" in settings.component_note, settings.component_note)
    finish()


if __name__ == "__main__":
    raise SystemExit(main())
