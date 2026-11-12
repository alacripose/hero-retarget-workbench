"""Build a self-contained Deadlock Model Forge Blender addon zip.

The addon resolves its bundled ``forge`` package when installed through
Blender's Add-ons installer. The archive contains one top-level
``deadlock_model_forge`` directory, which is the layout Blender expects.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import blake3

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "blender" / "deadlock_model_forge"
CORE = ROOT / "forge"
DEFAULT_OUT = ROOT / "dist"

REQUIRED = (
    "__init__.py",
    "core.py",
    "jobs.py",
    "operators.py",
    "properties.py",
    "proofing.py",
    "ui.py",
    "ui_lists.py",
    "weights.py",
    "workbench.py",
    "_vendor/blake3/__init__.py",
    "forge/__init__.py",
    "forge/axis.py",
    "forge/compile.py",
    "forge/hashes.py",
    "forge/live.py",
    "forge/names.py",
    "forge/paths.py",
    "forge/proof.py",
    "forge/stage.py",
    "forge/weights.py",
)


@dataclass(frozen=True)
class BuiltAddon:
    path: Path
    version: str
    file_count: int
    size: int
    sha256: str
    blake3: str


def addon_version() -> str:
    tree = ast.parse((ADDON / "__init__.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "bl_info" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        version = value.get("version")
        if isinstance(version, tuple) and len(version) == 3:
            return ".".join(str(part) for part in version)
    raise RuntimeError("bl_info.version is missing or malformed")


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f"missing addon source directory: {source}")
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _validate_source(staging: Path) -> list[Path]:
    files = sorted(path for path in staging.rglob("*") if path.is_file())
    relative = {path.relative_to(staging).as_posix() for path in files}
    missing = sorted(set(REQUIRED) - relative)
    if missing:
        raise RuntimeError("bundle is missing: " + ", ".join(missing))
    if any("__pycache__" in path.parts for path in files):
        raise RuntimeError("bundle contains __pycache__")
    vendor_extensions = [
        path
        for path in files
        if path.parent.name == "blake3" and path.suffix.lower() in (".pyd", ".so", ".dylib")
    ]
    if not vendor_extensions:
        raise RuntimeError("bundle is missing the vendored blake3 extension; the addon will not fall back to SHA-256")
    for path in files:
        if path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
    return files


def build_addon(out_dir: Path | None = None) -> BuiltAddon:
    version = addon_version()
    destination = Path(out_dir) if out_dir is not None else DEFAULT_OUT
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / f"deadlock_model_forge-{version}.zip"

    with tempfile.TemporaryDirectory(prefix="dmf-build-") as temporary:
        staging = Path(temporary) / "deadlock_model_forge"
        _copy_tree(ADDON, staging)
        _copy_tree(CORE, staging / "forge")
        files = _validate_source(staging)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(staging.parent).as_posix())

    archive_bytes = archive_path.read_bytes()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    return BuiltAddon(
        path=archive_path,
        version=version,
        file_count=len(files),
        size=archive_path.stat().st_size,
        sha256=digest,
        blake3=blake3.blake3(archive_bytes).hexdigest(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="directory for the zip")
    args = parser.parse_args()
    built = build_addon(args.out)
    print(built.path)
    print(f"version={built.version}")
    print(f"files={built.file_count}")
    print(f"bytes={built.size}")
    print(f"sha256={built.sha256}")
    print(f"blake3={built.blake3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
