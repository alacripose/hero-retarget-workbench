"""Migrate an old addon package onto the current live hero model.

The live hero vmdl is the base because it is the current game's model. The old
addon supplies the cloth and physics sections that the game model does not have,
plus the custom render meshes and material assets. Section contents are copied
from the old modeldoc; this module never builds a cloth chain, physics joint, or
material from inferred fields.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import modeldoc
from .hashes import blake3_file
from .live import Hero, LiveError, extract, hero_vmdl_path
from .paths import Environment
from .stage import is_texture_asset, material_files


DEFAULT_SECTIONS = ("Softbody", "PhysicsJointList")


class MigrationError(ValueError):
    pass


@dataclass
class MigrationResult:
    output: Path
    root: Path
    vmdl: Path
    manifest: Path
    old_root: Path
    old_vmdl: Path
    new_root: Path
    new_vmdl: Path
    old_package: Path
    preserved_model: bool
    sections: dict[str, dict[str, str]] = field(default_factory=dict)
    model_files: list[str] = field(default_factory=list)
    new_model_files: list[str] = field(default_factory=list)
    material_count: int = 0
    material_texture_count: int = 0


def _digest(path: Path) -> str:
    import hashlib

    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _safe_relative(value: str) -> str:
    path = value.replace("\\", "/").strip("/")
    if not path or ".." in path.split("/") or path.startswith("/"):
        raise MigrationError(f"unsafe-relative-path: {value!r}")
    return path


def _copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise MigrationError(f"missing-input: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _log(env: Environment, command: list[str], log_path: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(env.game_dir.parent) if env.game_dir else None,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "$ " + " ".join(command) + "\n\n" + result.stdout + ("\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
    )
    return result


def extract_package(env: Environment, package: Path, destination: Path, *, timeout: int = 1800) -> Path:
    """Extract a VPK or return an existing addon directory.

    Source 2 Viewer's decompile mode emits source assets for compiled entries.
    A directory is already a source package and is used in place.
    """
    package = package.expanduser().resolve()
    if package.is_dir():
        return package
    if not package.is_file():
        raise MigrationError(f"old-package-missing: {package}")
    if env.s2v is None:
        raise MigrationError("source-2-viewer-missing: choose the Source 2 Viewer CLI in Setup")
    destination = destination.resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    command = [str(env.s2v), "-i", str(package)]
    if env.gameinfo is not None:
        command.extend(["--game", str(env.gameinfo)])
    command.extend(["-o", str(destination), "-d"])
    result = _log(env, command, destination / "s2v-extract.log", timeout)
    if result.returncode != 0:
        raise MigrationError(f"old-package-extract-failed: {package}; see {destination / 's2v-extract.log'}")
    return destination


def find_vmdl(root: Path, preferred_relative: str | None = None) -> Path:
    """Find one source vmdl, preferring the current live model's relative path."""
    if preferred_relative:
        candidate = root / _safe_relative(preferred_relative)
        if candidate.is_file():
            return candidate
    candidates = sorted(path for path in root.rglob("*.vmdl") if path.is_file())
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise MigrationError(f"old-vmdl-missing: {root}")
    names = ", ".join(path.relative_to(root).as_posix() for path in candidates[:12])
    raise MigrationError(f"old-vmdl-ambiguous: choose one of {names}")


def section_files(text: str, section: str, suffixes: tuple[str, ...]) -> list[str]:
    try:
        block = modeldoc.sections(text).get(section)
    except modeldoc.ModeldocError:
        return []
    if block is None:
        return []
    result: list[str] = []
    for match in re.finditer(r'\b(?:filename|source_filename|output_vsnap)\s*=\s*"([^"]+)"', block.text):
        value = match.group(1).replace("\\", "/")
        if value.lower().endswith(suffixes):
            result.append(_safe_relative(value))
    return list(dict.fromkeys(result))


def _render_paths(text: str) -> list[str]:
    return section_files(text, "RenderMeshList", (".dmx",))


def _physics_paths(text: str) -> list[str]:
    return section_files(text, "PhysicsShapeList", (".dmx", ".vnmskel"))


def _skeleton_paths(text: str) -> list[str]:
    return section_files(text, "NmSkeletonList", (".vnmskel",))


def _is_custom_model(old_root: Path, old_text: str, new_root: Path, new_text: str) -> bool:
    old_paths = _render_paths(old_text)
    new_paths = _render_paths(new_text)
    if not old_paths:
        return False
    if old_paths != new_paths:
        return True
    for relative in old_paths:
        old = old_root / relative
        new = new_root / relative
        if not old.is_file():
            raise MigrationError(f"old-model-missing: {relative}")
        if not new.is_file() or _digest(old) != _digest(new):
            return True
    return False


def _copy_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() == ".log":
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _copy_materials(root: Path, destination: Path) -> tuple[int, int]:
    count = 0
    textures = 0
    for item in material_files(root):
        relative = _safe_relative(item.relative)
        _copy(item.source, destination / relative)
        count += 1
        textures += int(is_texture_asset(item.source))
    return count, textures


def _manifest_vmdl(root: Path, relative: str) -> dict:
    path = root / relative
    return {
        "vmdl": relative,
        "vmdl_sha256": _digest(path),
        "vmdl_blake3": blake3_file(path),
        "vmdl_modified": True,
        "migration_schema": "hero-addon-migration/2f6c1c2a7f4b7f2e",
    }


def migrate_trees(
    *,
    old_root: Path,
    old_vmdl: Path,
    new_root: Path,
    new_vmdl: Path,
    output: Path,
    addon_name: str,
    vmdl_relative: str | None = None,
    preserve_model: str = "auto",
    preserve_materials: bool = True,
    sections: tuple[str, ...] | list[str] = DEFAULT_SECTIONS,
    force: bool = False,
    old_package: Path | None = None,
) -> MigrationResult:
    """Merge an old addon tree onto a live extraction tree.

    ``preserve_model`` is ``auto`` (keep old meshes when they differ from live),
    ``old`` (always keep), or ``live`` (always use the live meshes). Cloth and
    physics sections default to the old addon's exact blocks.
    """
    old_root = old_root.resolve()
    new_root = new_root.resolve()
    old_vmdl = old_vmdl.resolve()
    new_vmdl = new_vmdl.resolve()
    if not old_root.is_dir() or not new_root.is_dir():
        raise MigrationError("migration-roots-missing")
    if not old_vmdl.is_file() or not new_vmdl.is_file():
        raise MigrationError("migration-vmdl-missing")
    if preserve_model not in ("auto", "old", "live"):
        raise MigrationError(f"model-policy-invalid: {preserve_model}")
    relative = _safe_relative(
        vmdl_relative
        or new_vmdl.relative_to(new_root).as_posix()
    )
    addon = _safe_relative(addon_name)
    output = output.resolve()
    root = output / "content" / "citadel_addons" / addon
    if root.exists() and not force:
        raise MigrationError(f"output-exists: {root}; pass force to replace it")
    if force and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    old_text = old_vmdl.read_text(encoding="utf-8", errors="replace")
    new_text = new_vmdl.read_text(encoding="utf-8", errors="replace")
    old_render = _render_paths(old_text)
    new_render = _render_paths(new_text)
    custom = False if preserve_model == "live" else _is_custom_model(old_root, old_text, new_root, new_text)
    keep_model = preserve_model == "old" or (preserve_model == "auto" and custom)
    if preserve_model == "old" and not old_render:
        raise MigrationError("old-model-list-missing")
    if keep_model:
        missing = [relative_path for relative_path in old_render if not (old_root / relative_path).is_file()]
        if missing:
            raise MigrationError(f"old-model-missing: {', '.join(missing[:8])}")

    requested = list(dict.fromkeys(sections))
    if keep_model:
        if old_render != new_render:
            requested.append("RenderMeshList")
        old_material_group = modeldoc.sections(old_text).get("MaterialGroupList")
        new_material_group = modeldoc.sections(new_text).get("MaterialGroupList")
        if (
            old_material_group is not None
            and new_material_group is not None
            and old_material_group.text != new_material_group.text
        ):
            requested.append("MaterialGroupList")
    requested = list(dict.fromkeys(requested))

    merged = modeldoc.merge(new_text, old_text, requested)

    # The live tree supplies the current animation set, skeleton and default
    # materials. The old addon overlays only the assets it owns.
    _copy_tree(new_root, root)
    old_material_count = 0
    old_texture_count = 0
    if preserve_materials:
        old_material_count, old_texture_count = _copy_materials(old_root, root)

    model_files: list[str] = []
    if keep_model:
        for relative_path in old_render:
            _copy(old_root / relative_path, root / relative_path)
            model_files.append(relative_path)
        # Physics hull and skeleton files are referenced by the old vmdl; keep
        # them beside the preserved meshes even when the live equivalents exist.
        for relative_path in dict.fromkeys(
            _physics_paths(old_text) + _skeleton_paths(old_text)
        ):
            source = old_root / relative_path
            if source.is_file():
                _copy(source, root / relative_path)
                model_files.append(relative_path)

    vmdl_out = root / relative
    vmdl_out.parent.mkdir(parents=True, exist_ok=True)
    vmdl_out.write_text(merged.text, encoding="utf-8", newline="\n")

    output_sections = modeldoc.sections(vmdl_out.read_text(encoding="utf-8"))
    cloth_chains = vmdl_out.read_text(encoding="utf-8").count('_class = "ClothChain"')
    cloth_hinges = vmdl_out.read_text(encoding="utf-8").count('_class = "ClothChainHinge"')
    manifest_data = _manifest_vmdl(root, relative)
    manifest_data.update(
        {
            "addon": addon,
            "old_package": str((old_package or old_root).resolve()),
            "old_vmdl": old_vmdl.relative_to(old_root).as_posix(),
            "old_vmdl_sha256": _digest(old_vmdl),
            "new_vmdl": new_vmdl.relative_to(new_root).as_posix(),
            "new_vmdl_sha256": _digest(new_vmdl),
            "model_policy": preserve_model,
            "custom_model": custom,
            "preserved_model": keep_model,
            "model_files": model_files,
            "new_model_files": new_render,
            "materials": old_material_count,
            "material_textures": old_texture_count,
            "material_policy": "old-assets-overlay-live" if preserve_materials else "live-only",
            "sections": merged.actions,
            "cloth_chains": cloth_chains,
            "cloth_hinges": cloth_hinges,
            "missing_sections": [
                name for name, action in merged.actions.items() if action["action"] == "absent"
            ],
        }
    )
    manifest = root / "stage.json"
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
    return MigrationResult(
        output=output,
        root=root,
        vmdl=vmdl_out,
        manifest=manifest,
        old_root=old_root,
        old_vmdl=old_vmdl,
        new_root=new_root,
        new_vmdl=new_vmdl,
        old_package=(old_package or old_root).resolve(),
        preserved_model=keep_model,
        sections=merged.actions,
        model_files=model_files,
        new_model_files=new_render,
        material_count=old_material_count,
        material_texture_count=old_texture_count,
    )


def update_from_package(
    env: Environment,
    package: Path,
    output: Path,
    addon_name: str,
    *,
    hero: Hero | None = None,
    new_extraction: Path | None = None,
    new_vmdl: Path | None = None,
    preserve_model: str = "auto",
    preserve_materials: bool = True,
    sections: tuple[str, ...] | list[str] = DEFAULT_SECTIONS,
    force: bool = False,
    timeout: int = 1800,
) -> MigrationResult:
    """Extract the old package and a live hero, then migrate the trees."""
    output = output.resolve()
    if output.exists() and not force:
        raise MigrationError(f"output-exists: {output}; pass force to replace it")
    output.mkdir(parents=True, exist_ok=True)
    old_root = extract_package(env, package, output / "old-package", timeout=timeout)
    preferred = hero_vmdl_path(hero.model_path) if hero is not None else None
    if new_extraction is None:
        if hero is None:
            raise MigrationError("new-extraction-or-hero-required")
        extraction_path = output / "new-live"
        if force and extraction_path.exists():
            shutil.rmtree(extraction_path)
        try:
            extraction = extract(env, hero, extraction_path, force=force)
        except LiveError as error:
            raise MigrationError(str(error)) from error
        if extraction.vmdl is None:
            raise MigrationError(f"new-vmdl-missing: {extraction.root}")
        new_root = extraction.root
        new_vmdl_path = extraction.vmdl
    else:
        new_root = Path(new_extraction).resolve()
        if new_vmdl is None:
            new_vmdl_path = find_vmdl(new_root, preferred)
        else:
            candidate = Path(new_vmdl)
            new_vmdl_path = (candidate if candidate.is_absolute() else new_root / candidate).resolve()
            if not new_vmdl_path.is_file():
                raise MigrationError(f"new-vmdl-missing: {new_vmdl_path}")
    if preferred is None:
        try:
            preferred = new_vmdl_path.relative_to(new_root).as_posix()
        except ValueError:
            preferred = None
    old_vmdl_path = find_vmdl(old_root, preferred)
    return migrate_trees(
        old_root=old_root,
        old_vmdl=old_vmdl_path,
        new_root=new_root,
        new_vmdl=new_vmdl_path,
        output=output,
        addon_name=addon_name,
        vmdl_relative=new_vmdl_path.relative_to(new_root).as_posix(),
        preserve_model=preserve_model,
        preserve_materials=preserve_materials,
        sections=sections,
        force=force,
        old_package=package,
    )
