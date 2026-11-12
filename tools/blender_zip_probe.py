"""Verify the built addon zip is self-contained and registers in Blender.

  blender -b --factory-startup --python tools/blender_zip_probe.py -- \
    --zip dist/deadlock_model_forge-0.2.3.zip \
    --report artifacts/receipts/deadlock-model-forge-zip.json

The probe deliberately imports from an extracted copy instead of the checkout,
so a missing vendored BLAKE3 extension or a missing module fails here.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def ui_icons(source: str, ui_module) -> set[str]:
    used = {match.group(1) for match in re.finditer(r'icon="([A-Z0-9_]+)"', source)}
    tree = ast.parse(source)
    positions = {"_section": 2, "_primary": 3, "_hint": 2, "_wrapped": 2, "_path_row": 5}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        index = positions.get(node.func.id)
        if index is None or len(node.args) <= index:
            continue
        value = node.args[index]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            used.add(value.value)
    for mapping in (ui_module._STATUS_ICONS, ui_module._CHECK_ICONS):
        used.update(mapping.values())
    return used


def main() -> int:
    args = parse_args()
    archive = Path(args.zip).resolve()
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        raise RuntimeError(f"missing addon zip: {archive}")

    temp = Path(tempfile.mkdtemp(prefix="dmf-zip-probe-"))
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            bundle.extractall(temp)
        package_root = temp / "deadlock_model_forge"
        if not (package_root / "__init__.py").is_file():
            raise RuntimeError("zip does not contain deadlock_model_forge/__init__.py")
        if not (package_root / "_vendor" / "blake3").is_dir():
            raise RuntimeError("zip does not carry the vendored blake3 package")

        for name in list(sys.modules):
            if name == "deadlock_model_forge" or name.startswith("deadlock_model_forge."):
                del sys.modules[name]
            if name == "blake3" or name.startswith("blake3."):
                del sys.modules[name]
        sys.path.insert(0, str(temp))
        import deadlock_model_forge as dmf
        import blake3

        if package_root.resolve() not in Path(dmf.__file__).resolve().parents:
            raise RuntimeError(f"imported the checkout, not the zip: {dmf.__file__}")
        vendor_root = (package_root / "_vendor" / "blake3").resolve()
        if vendor_root not in Path(blake3.__file__).resolve().parents:
            raise RuntimeError(f"blake3 was not imported from the zip: {blake3.__file__}")
        if dmf.bl_info["version"] != (0, 2, 3):
            raise RuntimeError(f"unexpected version: {dmf.bl_info['version']}")

        dmf.register()
        if not hasattr(bpy.types.Scene, "dmf"):
            raise RuntimeError("register did not add Scene.dmf")
        settings = bpy.context.scene.dmf
        panels = len(dmf.ui.CLASSES)
        workbench = len(dmf.workbench.CLASSES)
        operators = len(dmf.operators.CLASSES) + workbench
        if panels != 7:
            raise RuntimeError(f"expected 7 panel classes, found {panels}")
        if workbench != 24:
            raise RuntimeError(f"expected 24 workbench operators, found {workbench}")
        if operators != 40:
            raise RuntimeError(f"expected 40 operator classes in total, found {operators}")
        valid_icons = {
            item.identifier
            for item in bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items
        }
        used_icons = ui_icons((package_root / "ui.py").read_text(encoding="utf-8"), dmf.ui)
        used_icons.update(dmf.ui_lists._ICONS.values())
        invalid_icons = sorted(used_icons - valid_icons)
        if invalid_icons:
            raise RuntimeError(f"invalid Blender icons in ui.py: {invalid_icons}")
        if not hasattr(bpy.ops.dmf, "mint_proof"):
            raise RuntimeError("proof operator was not registered")
        settings.proof_presenter = "zip-probe"
        settings.proof_ticket = "TICKET-0002"
        dmf.unregister()
        if hasattr(bpy.types.Scene, "dmf"):
            raise RuntimeError("unregister left Scene.dmf behind")

        digest = blake3.blake3(archive.read_bytes()).hexdigest()
        report = {
            "result": "pass",
            "zip": str(archive),
            "zip_bytes": archive.stat().st_size,
            "zip_sha256": sha256(archive),
            "zip_blake3": "blake3:" + digest,
            "files": len(names),
            "version": ".".join(str(part) for part in dmf.bl_info["version"]),
            "panels": panels,
            "operators": operators,
            "workbench_operators": workbench,
            "icons_checked": len(used_icons),
            "blake3_module": str(Path(blake3.__file__).resolve()),
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as error:
        report = {
            "result": "fail",
            "zip": str(archive),
            "error": f"{type(error).__name__}: {error}",
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
        raise
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
