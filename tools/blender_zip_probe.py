"""Verify the built addon zip is self-contained and registers in Blender.

  blender -b --factory-startup --python tools/blender_zip_probe.py -- \
    --zip dist/hero_retarget_workbench-0.2.5.zip \
    --report artifacts/receipts/hero-retarget-workbench-zip.json

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
        package_root = temp / "hero_retarget_workbench"
        if not (package_root / "__init__.py").is_file():
            raise RuntimeError("zip does not contain hero_retarget_workbench/__init__.py")
        if not (package_root / "_vendor" / "blake3").is_dir():
            raise RuntimeError("zip does not carry the vendored blake3 package")

        for name in list(sys.modules):
            if name == "hero_retarget_workbench" or name.startswith("hero_retarget_workbench."):
                del sys.modules[name]
            if name == "blake3" or name.startswith("blake3."):
                del sys.modules[name]
        sys.path.insert(0, str(temp))
        import hero_retarget_workbench as dmf
        import blake3

        if package_root.resolve() not in Path(dmf.__file__).resolve().parents:
            raise RuntimeError(f"imported the checkout, not the zip: {dmf.__file__}")
        vendor_root = (package_root / "_vendor" / "blake3").resolve()
        if vendor_root not in Path(blake3.__file__).resolve().parents:
            raise RuntimeError(f"blake3 was not imported from the zip: {blake3.__file__}")
        if dmf.bl_info["version"] != (0, 2, 5):
            raise RuntimeError(f"unexpected version: {dmf.bl_info['version']}")

        dmf.register()
        if not hasattr(bpy.types.Scene, "dmf"):
            raise RuntimeError("register did not add Scene.dmf")
        settings = bpy.context.scene.dmf

        # Simulate the real machine: the old addon left a top-level ``forge``
        # module in sys.modules. The new addon must import its own bundle.
        import types

        stale_forge = types.ModuleType("forge")
        stale_forge.__file__ = "<stale deadlock_model_forge>"
        sys.modules["forge"] = stale_forge
        bundled = dmf.core.core(settings)
        if "hero_retarget_workbench.forge.paths" not in bundled["paths"].__name__:
            raise RuntimeError(f"core imported the stale forge module: {bundled['paths'].__name__}")

        panels = len(dmf.ui.CLASSES)
        workbench = len(dmf.workbench.CLASSES)
        operators = len(dmf.operators.CLASSES) + workbench
        if panels != 8:
            raise RuntimeError(f"expected 8 panel classes, found {panels}")
        if workbench != 24:
            raise RuntimeError(f"expected 24 workbench operators, found {workbench}")
        if operators != 41:
            raise RuntimeError(f"expected 41 operator classes in total, found {operators}")
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
        if not hasattr(bpy.ops.dmf, "detect_paths"):
            raise RuntimeError("path detection operator was not registered")

        expected_paths = {
            "deadlock_root": str(temp / "Deadlock"),
            "s2v_cli": str(temp / "Source2Viewer-CLI.exe"),
            "csdk_root": str(temp / "CSDK13"),
        }
        for name, value in expected_paths.items():
            setattr(settings, name, value)
        settings.project_root = str(temp / "workspace")
        saved_blend = temp / "path-config.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(saved_blend))
        bpy.ops.wm.open_mainfile(filepath=str(saved_blend))
        reloaded = bpy.context.scene.dmf
        for name, value in expected_paths.items():
            if getattr(reloaded, name) != value:
                raise RuntimeError(f"{name} did not survive the .blend save: {getattr(reloaded, name)!r}")
        if reloaded.project_root != str(temp / "workspace"):
            raise RuntimeError("workspace folder did not survive the .blend save")

        game_fixture = Path(expected_paths["deadlock_root"])
        (game_fixture / "game" / "citadel").mkdir(parents=True)
        (game_fixture / "game" / "citadel" / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
        (game_fixture / "game" / "citadel" / "pak01_dir.vpk").write_text("vpk", encoding="utf-8")
        (game_fixture / "game" / "citadel" / "steam.inf").write_text(
            "ClientVersion=6861\nVersionDate=Nov 09 2026\n", encoding="utf-8"
        )
        Path(expected_paths["s2v_cli"]).write_bytes(b"s2v")
        csdk_fixture = Path(expected_paths["csdk_root"])
        (csdk_fixture / "game" / "bin" / "win64").mkdir(parents=True)
        (csdk_fixture / "game" / "bin" / "win64" / "resourcecompiler.exe").write_bytes(b"compiler")
        (csdk_fixture / "game" / "citadel").mkdir(parents=True)
        (csdk_fixture / "game" / "citadel" / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")

        # The GUI accepts a double-click but does not run the addon's CLI
        # extraction command. It must be rejected, not silently used.
        gui = temp / "Source2Viewer.exe"
        gui.write_bytes(b"gui")
        reloaded.s2v_cli = str(gui)
        result = bpy.ops.dmf.detect_paths()
        if "FINISHED" not in result:
            raise RuntimeError(f"detect_paths did not finish for the GUI: {result}")
        if reloaded.status_kind != "WARN" or "Source2Viewer-CLI" not in reloaded.status:
            raise RuntimeError(f"the GUI was not rejected: {reloaded.status}")

        reloaded.s2v_cli = expected_paths["s2v_cli"]
        result = bpy.ops.dmf.detect_paths()
        if "FINISHED" not in result:
            raise RuntimeError(f"detect_paths did not finish: {result}")
        if reloaded.build != "6861 Nov 09 2026":
            raise RuntimeError(f"detect_paths did not read the configured build: {reloaded.build!r}")
        if reloaded.status_kind != "OK":
            raise RuntimeError(f"detect_paths did not find all configured tools: {reloaded.status}")

        settings = reloaded
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
            "path_config_saved": True,
            "path_detect_operator": True,
            "path_namespace_isolated": True,
            "s2v_gui_rejected": True,
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
