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
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import modeldoc
from .hashes import blake3_file
from .live import Hero, LiveError, extract, hero_vmdl_path
from .paths import Environment
from .stage import is_texture_asset, material_files


# Section names are discovered from each old model. ``Softbody`` and
# ``PhysicsJointList`` are current examples, not a closed list.


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
        if candidate.is_file() and candidate.suffix.lower() == ".vmdl":
            return candidate
    candidates = sorted(path for path in root.rglob("*.vmdl") if path.is_file())
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise MigrationError(f"old-vmdl-missing: {root}")
    names = ", ".join(path.relative_to(root).as_posix() for path in candidates[:12])
    raise MigrationError(f"old-vmdl-ambiguous: choose one of {names}")


def find_compiled_model(
    root: Path,
    preferred_relative: str | None = None,
    hero: str = "",
) -> Path:
    """Find one compiled model in an addon that carries no source vmdl.

    Older packages were often shipped after ``resourcecompiler`` ran, so the
    only model left is ``*.vmdl_c``. The same preferred-path and hero rules used
    for source models are applied here; a compiled model is not selected by its
    file extension alone when several exist.
    """
    root = Path(root).resolve()
    candidates = sorted(path for path in root.rglob("*.vmdl_c") if path.is_file())
    if not candidates:
        raise MigrationError(f"old-vmdl-missing: {root}")
    preferred = (preferred_relative or "").replace("\\", "/").strip("/")
    if preferred:
        variants = [preferred]
        if preferred.lower().endswith(".vmdl"):
            variants.append(preferred + "_c")
        elif preferred.lower().endswith(".vmdl_c"):
            variants.append(preferred[: -len("_c")])
        for variant in variants:
            try:
                candidate = root / _safe_relative(variant)
            except MigrationError:
                continue
            if candidate in candidates:
                return candidate
    slug = (hero or "").split(",")[0].strip().lower()
    if slug:
        near_hero = [
            path
            for path in candidates
            if f"/{slug}/" in path.as_posix().lower()
            or f"/{slug}_" in path.as_posix().lower()
        ]
        if len(near_hero) == 1:
            return near_hero[0]
        if near_hero:
            candidates = near_hero
    if len(candidates) == 1:
        return candidates[0]
    names = ", ".join(path.relative_to(root).as_posix() for path in candidates[:12])
    raise MigrationError(f"old-vmdl-ambiguous: choose one of {names}")


def _match_value(match, key: str, default=""):
    if isinstance(match, dict):
        return match.get(key, default)
    return getattr(match, key, default)


def _matching_install(matches, root: Path, compiled: Path) -> dict:
    """The install-side copy of a compiled model, when hashes identified one."""
    relative = compiled.relative_to(root).as_posix()
    for match in matches or ():
        value = str(_match_value(match, "relative", "")).replace("\\", "/")
        if value not in (relative, compiled.name):
            continue
        return {
            "install": str(_match_value(match, "install", "")),
            "label": str(_match_value(match, "label", "")),
            "build": str(_match_value(match, "build", "")),
            "kind": str(_match_value(match, "kind", "")),
            "container": str(_match_value(match, "container", "")),
            "entry": str(_match_value(match, "entry", relative)),
            "gameinfo": str(_match_value(match, "gameinfo", "")),
            "crc32": _match_value(match, "crc32", None),
        }
    return {}


def extract_compiled_model(
    env: Environment,
    compiled: Path,
    destination: Path,
    *,
    container: Path | None = None,
    entry: str = "",
    relative: str = "",
    gameinfo: Path | None = None,
    timeout: int = 900,
) -> Path:
    """Ask Source 2 Viewer to decompile a compiled model, from a VPK or a file.

    The compiled bytes are never parsed here. S2V prints the modeldoc and writes
    the source vmdl; a VPK match also supplies the game context the model was
    built against.
    """
    if env.s2v is None:
        raise MigrationError("source-2-viewer-missing: choose the Source 2 Viewer CLI in Setup")
    compiled = Path(compiled).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    chosen_gameinfo = gameinfo or env.gameinfo
    staging: Path | None = None
    if container is not None and entry:
        command = [str(env.s2v), "-i", str(container)]
        if chosen_gameinfo is not None:
            command += ["--game", str(chosen_gameinfo)]
        command += ["-f", entry, "-o", str(destination), "-d"]
    else:
        # A single input file is dumped at the output root. A mod's source vmdl
        # names files below ``models/...``, so stage the compiled file at its
        # original relative path and scan that tree recursively. The first try
        # produced a valid vmdl whose render meshes pointed at paths S2V had not
        # written, which is the old-model-missing failure.
        keep = _safe_relative(relative or compiled.name)
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-input-", dir=destination.parent))
        staged = staging / keep
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(compiled, staged)
        command = [str(env.s2v), "-i", str(staging)]
        if chosen_gameinfo is not None:
            command += ["--game", str(chosen_gameinfo)]
        command += ["-o", str(destination), "-d", "--recursive"]
    try:
        result = _log(env, command, destination / "s2v-compiled.log", timeout)
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    if result.returncode != 0:
        raise MigrationError(
            f"old-vmdl-decompile-failed: {compiled}; see {destination / 's2v-compiled.log'}"
        )
    candidates = sorted(destination.rglob("*.vmdl"))
    if not candidates:
        raise MigrationError(f"old-vmdl-decompile-empty: {compiled}")
    target = compiled.stem.lower()
    for candidate in candidates:
        if candidate.stem.lower() == target:
            return candidate
    return candidates[0]


def resolve_old_model(
    env: Environment,
    old_root: Path,
    *,
    preferred: str | None = None,
    hero: str = "",
    matches=(),
    destination: Path | None = None,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Resolve a source vmdl, decompiling a compiled-only package when needed.

    A source model wins when one exists. Otherwise the compiled model is matched
    to an installed build by its content hash; that build's VPK supplies the
    extraction context. If no installed copy matches, the mod's own compiled
    file is the input, so a package made without sources still ports.
    """
    old_root = Path(old_root).resolve()
    preferred_text = (preferred or "").replace("\\", "/").strip("/")
    prefer_compiled = preferred_text.lower().endswith(".vmdl_c")
    if preferred_text and not prefer_compiled:
        candidate = old_root / preferred_text
        prefer_compiled = candidate.is_file() and candidate.suffix.lower() == ".vmdl_c"
    if prefer_compiled and not (old_root / preferred_text).is_file():
        # A VPK package is decompiled before this point. S2V writes the source
        # vmdl, not the compiled entry, so an explicit compiled-path request
        # must fall through to its source counterpart instead of reporting the
        # package as missing.
        source_relative = preferred_text[:-2] if preferred_text.lower().endswith("_c") else ""
        source_candidate = old_root / source_relative if source_relative else None
        if source_candidate is not None and source_candidate.is_file():
            return source_candidate, {
                "kind": "source",
                "path": source_candidate.relative_to(old_root).as_posix(),
            }
    if not prefer_compiled:
        try:
            source = find_vmdl(old_root, preferred)
            return source, {"kind": "source", "path": source.relative_to(old_root).as_posix()}
        except MigrationError as source_error:
            if "ambiguous" in str(source_error):
                raise
    compiled = find_compiled_model(old_root, preferred, hero)
    match = _matching_install(matches, old_root, compiled)
    container = Path(match["container"]) if match.get("container") and match.get("kind") == "vpk" else None
    entry = match.get("entry", "") if container is not None else ""
    gameinfo = Path(match["gameinfo"]) if match.get("gameinfo") else None
    target = Path(destination) if destination is not None else old_root / ".decompiled-old"
    path = extract_compiled_model(
        env,
        compiled,
        target,
        container=container,
        entry=entry,
        relative=compiled.relative_to(old_root).as_posix(),
        gameinfo=gameinfo,
        timeout=timeout,
    )
    source_info = {
        "kind": "compiled",
        "path": compiled.relative_to(old_root).as_posix(),
        "sha256": _digest(compiled),
        "assets_root": str(target),
        "container": str(container or compiled),
        "entry": entry,
        "install": match.get("install", ""),
        "install_build": match.get("build", ""),
        "matched": bool(match),
    }
    return path, source_info


def section_files(text: str, section: str, suffixes: tuple[str, ...]) -> list[str]:
    try:
        block = modeldoc.sections(text).get(section)
    except modeldoc.ModeldocError:
        return []
    if block is None:
        return []
    result: list[str] = []
    # Different modeldoc writers use different keys for the same path
    # (filename, source_filename, output_vsnap, or a newer key). Match the
    # quoted path by suffix instead of pinning the migration to one writer.
    for match in re.finditer(r'"([^"]+\.[A-Za-z0-9_]+)"', block.text):
        value = match.group(1).replace("\\", "/")
        if value.lower().endswith(suffixes):
            result.append(_safe_relative(value))
    return list(dict.fromkeys(result))


def referenced_files(text: str) -> list[str]:
    """Every file path a modeldoc names in one of its top-level sections."""
    suffixes = (
        ".dmx",
        ".vmdl",
        ".vmdl_c",
        ".vmat",
        ".vmat_c",
        ".vtex",
        ".vtex_c",
        ".vnmclip",
        ".vnmclip_c",
        ".vnmskel",
        ".vnmskel_c",
    )
    values: list[str] = []
    try:
        blocks = modeldoc.sections(text).values()
    except modeldoc.ModeldocError:
        return values
    for block in blocks:
        for match in re.finditer(r'"([^"]+\.[A-Za-z0-9_]+)"', block.text):
            value = match.group(1).replace("\\", "/")
            if not value.lower().endswith(suffixes):
                continue
            try:
                values.append(_safe_relative(value))
            except MigrationError:
                continue
    return list(dict.fromkeys(values))


def model_file_diff(
    old_root: Path,
    old_text: str,
    new_root: Path,
    new_text: str,
    old_assets: Path | None = None,
) -> list[dict]:
    """Files named by the old and new models that are not byte-identical."""
    old_files = set(referenced_files(old_text))
    new_files = set(referenced_files(new_text))
    rows: list[dict] = []
    for relative in sorted(old_files | new_files, key=str.lower):
        old_path = _old_asset(old_root, old_assets, relative)
        new_path = Path(new_root) / relative
        old_exists = old_path is not None
        new_exists = new_path.is_file()
        if not old_exists and not new_exists:
            state = "missing"
        elif old_exists and not new_exists:
            state = "old-only"
        elif new_exists and not old_exists:
            state = "new-only"
        elif old_path is not None:
            state = "same" if _digest(old_path) == _digest(new_path) else "changed"
        if state == "same":
            continue
        rows.append(
            {
                "path": relative,
                "state": state,
                "old_exists": old_exists,
                "new_exists": new_exists,
                "old_size": old_path.stat().st_size if old_path is not None else 0,
                "new_size": new_path.stat().st_size if new_exists else 0,
            }
        )
    return rows


def model_node_diff(old_text: str, new_text: str) -> list[dict]:
    """Top-level modeldoc nodes, with the ones the old model owns selected."""
    try:
        old_sections = modeldoc.sections(old_text)
    except modeldoc.ModeldocError:
        return []
    try:
        new_sections = modeldoc.sections(new_text)
    except modeldoc.ModeldocError:
        new_sections = {}
    keep = set(modeldoc.cloth_physics_sections(old_text))
    rows: list[dict] = []
    for name in sorted(old_sections):
        old_block = old_sections[name]
        new_block = new_sections.get(name)
        changed = new_block is None or old_block.text != new_block.text
        selected = name in keep or (
            changed and name in ("RenderMeshList", "MaterialGroupList")
        )
        rows.append(
            {
                "name": name,
                "selected": selected,
                "changed": changed,
                "old_lines": len(old_block.text.splitlines()),
                "new_lines": len(new_block.text.splitlines()) if new_block else 0,
            }
        )
    return rows


def analyze_package(
    env: Environment,
    package: Path,
    output: Path,
    *,
    hero: Hero | None = None,
    old_vmdl: Path | None = None,
    old_matches=(),
    new_extraction: Path | None = None,
    new_vmdl: Path | None = None,
    timeout: int = 1800,
) -> dict:
    """Resolve both models and return the selectable nodes and file diff.

    This is the preview the Mods page shows before a port. It does not write an
    addon; it only reads both modeldocs and the files they name.
    """
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    old_root = extract_package(env, Path(package), output / "old-package", timeout=timeout)
    preferred = hero_vmdl_path(hero.model_path) if hero is not None else None
    old_source: dict = {"kind": "source"}
    if old_vmdl is None:
        old_path, old_source = resolve_old_model(
            env,
            old_root,
            preferred=preferred,
            hero=hero.slug if hero is not None else "",
            matches=old_matches,
            destination=output / "old-decompiled",
            timeout=timeout,
        )
    else:
        old_path = Path(old_vmdl)
        if not old_path.is_absolute():
            old_path = old_root / old_path
        if old_path.suffix.lower() == ".vmdl_c":
            old_path, old_source = resolve_old_model(
                env,
                old_root,
                preferred=(
                    old_path.relative_to(old_root).as_posix()
                    if old_path.is_relative_to(old_root)
                    else old_path.name
                ),
                hero=hero.slug if hero is not None else "",
                matches=old_matches,
                destination=output / "old-decompiled",
                timeout=timeout,
            )
        if not old_path.is_file():
            old_path, old_source = resolve_old_model(
                env,
                old_root,
                preferred=(
                    old_path.relative_to(old_root).as_posix()
                    if old_path.is_relative_to(old_root)
                    else old_path.name
                ),
                hero=hero.slug if hero is not None else "",
                matches=old_matches,
                destination=output / "old-decompiled",
                timeout=timeout,
            )
    if new_extraction is None:
        if hero is None:
            raise MigrationError("new-extraction-or-hero-required")
        extraction = extract(env, hero, output / "new-live", force=True)
        if extraction.vmdl is None:
            raise MigrationError(f"new-vmdl-missing: {extraction.root}")
        new_root = extraction.root
        new_path = extraction.vmdl
    else:
        new_root = Path(new_extraction).resolve()
        if new_vmdl is None:
            new_path = find_vmdl(new_root, preferred)
        else:
            candidate = Path(new_vmdl)
            new_path = (candidate if candidate.is_absolute() else new_root / candidate).resolve()
            if not new_path.is_file():
                raise MigrationError(f"new-vmdl-missing: {new_path}")
    old_text = old_path.read_text(encoding="utf-8", errors="replace")
    new_text = new_path.read_text(encoding="utf-8", errors="replace")
    old_assets = Path(old_source["assets_root"]) if old_source.get("assets_root") else None
    return {
        "package": str(Path(package).resolve()),
        "old_root": str(old_root),
        "old_vmdl": str(old_path),
        "old_source": old_source,
        "new_root": str(new_root),
        "new_vmdl": str(new_path),
        "nodes": model_node_diff(old_text, new_text),
        "files": model_file_diff(old_root, old_text, new_root, new_text, old_assets=old_assets),
    }


def _render_paths(text: str) -> list[str]:
    return section_files(text, "RenderMeshList", (".dmx",))


def _physics_paths(text: str) -> list[str]:
    return section_files(text, "PhysicsShapeList", (".dmx", ".vnmskel"))


def _skeleton_paths(text: str) -> list[str]:
    return section_files(text, "NmSkeletonList", (".vnmskel",))


def _is_custom_model(
    old_root: Path,
    old_text: str,
    new_root: Path,
    new_text: str,
    old_assets: Path | None = None,
) -> bool:
    old_paths = _render_paths(old_text)
    new_paths = _render_paths(new_text)
    if not old_paths:
        return False
    if old_paths != new_paths:
        return True
    for relative in old_paths:
        old = _old_asset(old_root, old_assets, relative)
        new = new_root / relative
        if old is None:
            raise MigrationError(f"old-model-missing: {relative}")
        if not new.is_file() or _digest(old) != _digest(new):
            return True
    return False


def _old_asset(old_root: Path, old_assets: Path | None, relative: str) -> Path | None:
    """A model file from the package, or from an isolated decompile root.

    Compiled-only packages decompile into a separate directory: the vmdl sits
    below its original ``models/...`` path, but the package tree itself has no
    source assets. Prefer the package (where old mods did ship the file), then
    the decompile root, then a unique basename for older flat S2V output.
    """
    direct = Path(old_root) / relative
    if direct.is_file():
        return direct
    if old_assets is None:
        return None
    staged = Path(old_assets) / relative
    if staged.is_file():
        return staged
    if not Path(old_assets).is_dir():
        return None
    matches = sorted(path for path in Path(old_assets).rglob(Path(relative).name) if path.is_file())
    return matches[0] if len(matches) == 1 else None


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
    sections: tuple[str, ...] | list[str] | None = None,
    force: bool = False,
    old_package: Path | None = None,
    old_source: dict | None = None,
    old_assets: Path | None = None,
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
    old_assets = old_assets.resolve() if old_assets is not None else None
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
    custom = (
        False
        if preserve_model == "live"
        else _is_custom_model(old_root, old_text, new_root, new_text, old_assets=old_assets)
    )
    keep_model = preserve_model == "old" or (preserve_model == "auto" and custom)
    if preserve_model == "old" and not old_render:
        raise MigrationError("old-model-list-missing")
    if keep_model:
        missing = [
            relative_path
            for relative_path in old_render
            if _old_asset(old_root, old_assets, relative_path) is None
        ]
        if missing:
            raise MigrationError(f"old-model-missing: {', '.join(missing[:8])}")

    requested = list(
        dict.fromkeys(
            modeldoc.cloth_physics_sections(old_text) if sections is None else sections
        )
    )
    if keep_model and sections is None:
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
    if not keep_model and "RenderMeshList" in requested:
        requested.remove("RenderMeshList")
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
            source = _old_asset(old_root, old_assets, relative_path)
            if source is None:
                raise MigrationError(f"old-model-missing: {relative_path}")
            _copy(source, root / relative_path)
            model_files.append(relative_path)
        # Physics hull and skeleton files are referenced by the old vmdl; keep
        # them beside the preserved meshes even when the live equivalents exist.
        for relative_path in dict.fromkeys(
            _physics_paths(old_text) + _skeleton_paths(old_text)
        ):
            source = _old_asset(old_root, old_assets, relative_path)
            if source is not None:
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
            "old_vmdl": (
                old_vmdl.relative_to(old_root).as_posix()
                if old_vmdl.is_relative_to(old_root)
                else str(old_vmdl)
            ),
            "old_vmdl_sha256": _digest(old_vmdl),
            "old_source": old_source or {"kind": "source"},
            "old_assets": str(old_assets) if old_assets is not None else "",
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


def add_component_mesh(
    vmdl: Path,
    *,
    mesh_name: str,
    dmx_relative: str,
    bodygroup: str = "",
    choice: str = "",
    replace: bool = False,
) -> dict:
    """Add one DMX-backed render mesh to a staged vmdl, plus a body-group choice.

    A modeldoc can reference several render meshes as separate DMX files, which
    is how the game's own heroes carry a body and a gun. A cosmetic component is
    the same shape: one more ``RenderMeshFile`` whose name appears in a
    ``BodyGroupChoice``, so the game can show or hide it. This is the only place
    that writes an edited vmdl for components; the caller owns the copy.
    """
    path = Path(vmdl).resolve()
    if not path.is_file():
        raise MigrationError(f"component-vmdl-missing: {path}")
    relative = dmx_relative.replace("\\", "/").lstrip("/")
    if not relative:
        raise MigrationError("component-dmx-path-required")
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        merged = modeldoc.add_render_mesh_file(
            text,
            name=mesh_name,
            filename=relative,
            bodygroup=bodygroup,
            choice=choice,
            replace=replace,
        )
    except modeldoc.ModeldocError as error:
        raise MigrationError(str(error)) from error
    if merged.text != text:
        path.write_text(merged.text, encoding="utf-8", newline="\n")
    return {
        "vmdl": str(path),
        "mesh": mesh_name,
        "filename": relative,
        "actions": merged.actions,
        "bodygroup": merged.bodygroup,
        "choice": merged.choice,
        "render_meshes": [item.name for item in modeldoc.render_mesh_files(merged.text)],
        "bodygroups": {group.name: list(group.meshes) for group in modeldoc.body_groups(merged.text)},
    }


def update_from_package(
    env: Environment,
    package: Path,
    output: Path,
    addon_name: str,
    *,
    hero: Hero | None = None,
    new_extraction: Path | None = None,
    new_vmdl: Path | None = None,
    old_vmdl: Path | None = None,
    old_matches=(),
    preserve_model: str = "auto",
    preserve_materials: bool = True,
    sections: tuple[str, ...] | list[str] | None = None,
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
    old_source: dict = {"kind": "source"}
    if old_vmdl is None:
        old_vmdl_path, old_source = resolve_old_model(
            env,
            old_root,
            preferred=preferred,
            hero=hero.slug if hero is not None else "",
            matches=old_matches,
            destination=output / "old-decompiled",
            timeout=timeout,
        )
    else:
        candidate = Path(old_vmdl)
        old_vmdl_path = (candidate if candidate.is_absolute() else old_root / candidate).resolve()
        if old_vmdl_path.suffix.lower() == ".vmdl_c":
            old_vmdl_path, old_source = resolve_old_model(
                env,
                old_root,
                preferred=old_vmdl_path.relative_to(old_root).as_posix()
                if old_vmdl_path.is_relative_to(old_root)
                else old_vmdl_path.name,
                hero=hero.slug if hero is not None else "",
                matches=old_matches,
                destination=output / "old-decompiled",
                timeout=timeout,
            )
        elif not old_vmdl_path.is_file():
            old_vmdl_path, old_source = resolve_old_model(
                env,
                old_root,
                preferred=(
                    old_vmdl_path.relative_to(old_root).as_posix()
                    if old_vmdl_path.is_relative_to(old_root)
                    else old_vmdl_path.name
                ),
                hero=hero.slug if hero is not None else "",
                matches=old_matches,
                destination=output / "old-decompiled",
                timeout=timeout,
            )
    old_assets = Path(old_source["assets_root"]) if old_source.get("assets_root") else None
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
        old_source=old_source,
        old_assets=old_assets,
    )


def repoint_render_mesh(vmdl: str | Path, mesh_name: str, filename: str) -> dict:
    """Repoint one render mesh at another DMX, through the sanctioned vmdl writer.

    This file is the only module allowed to write a vmdl (see AGENTS.md, 2026-11-13);
    a mesh repoint is a vmdl write, so it lives here rather than in a tool.
    """
    from . import modeldoc

    path = Path(vmdl)
    text = path.read_text(encoding="utf-8", errors="replace")
    before = {row.name: row.filename for row in modeldoc.render_mesh_files(text)}
    if mesh_name not in before:
        raise modeldoc.MeshListError(f"render-mesh-missing: {mesh_name}")
    updated = modeldoc.set_render_mesh_filename(text, mesh_name, filename)
    if updated == text:
        return {"vmdl": str(path), "mesh": mesh_name, "changed": False, "from": before[mesh_name], "to": filename}
    path.write_text(updated, encoding="utf-8", newline="\n")
    after = {row.name: row.filename for row in modeldoc.render_mesh_files(path.read_text(encoding="utf-8", errors="replace"))}
    return {"vmdl": str(path), "mesh": mesh_name, "changed": True, "from": before[mesh_name], "to": after.get(mesh_name)}


def write_model_text(vmdl: str | Path, text: str) -> dict:
    """Replace a vmdl's text with `text`, through the module that owns vmdl writes.

    Returns the digest of what is on disk afterwards, so a caller can record the file it
    actually produced rather than the string it meant to produce.
    """
    import hashlib

    path = Path(vmdl)
    before = path.read_bytes()
    data = text.encode("utf-8")
    if data == before:
        return {"vmdl": str(path), "changed": False, "sha256": hashlib.sha256(before).hexdigest()}
    path.write_bytes(data)
    after = path.read_bytes()
    return {"vmdl": str(path), "changed": True, "sha256": hashlib.sha256(after).hexdigest()}
