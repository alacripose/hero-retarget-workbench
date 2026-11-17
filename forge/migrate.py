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
from .fileio import copy_file, walk_files
from .hashes import blake3_file
from .live import Hero, LiveError, body_for_hero_folder, extract, hero_vmdl_path
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


@dataclass
class MaterialSourceResult:
    """Editable files recovered from a package's compiled material assets."""

    materials: int = 0
    textures: int = 0
    skipped: list[str] = field(default_factory=list)
    error: str = ""


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
    try:
        copy_file(source, destination)
    except OSError as error:
        raise MigrationError(
            f"copy-failed: {source} -> {destination}: {error}"
        ) from error


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
    for path, relative in walk_files(source):
        if relative.suffix.lower() == ".log":
            continue
        _copy(path, destination / relative)


def _copy_materials(root: Path, destination: Path) -> tuple[int, int]:
    count = 0
    textures = 0
    for item in material_files(root):
        relative = _safe_relative(item.relative)
        _copy(item.source, destination / relative)
        count += 1
        textures += int(is_texture_asset(item.source))
    return count, textures


# A decompiled vmat keeps its compiled texture references and the source
# texture fields that a material editor shows.  The compiled key names are
# stable even when a material has no source texture checked in beside it.
_TEXTURE_FIELDS = {
    "g_tAmbientOcclusion": ("TextureAmbientOcclusion1",),
    "g_tColor": ("TextureColor1",),
    "g_tNormalRoughness": ("TextureNormal1", "TextureRoughness1"),
    "g_tNprOutlineMask": ("TextureNprOutlineMask1",),
    "g_tNprTransmissiveColor": ("TextureNprTramsissiveColor1",),
    "g_tSelfIllumMask": ("TextureSelfIllumMask1",),
    "g_tTintMask": ("TextureTintMask1",),
    "g_tTintMaskRimLightMask": ("TextureRimLightMask1",),
}


def _material_texture_pairs(text: str, decompiled: Path) -> list[tuple[str, Path]]:
    """Map a decompiled vmat's source texture fields to its decoded PNGs.

    S2V writes one PNG per compiled ``.vtex_c`` under the compiled basename.
    The source texture field can name a different basename, so the compiled
    block is the bridge: it names the texture, and the field names the slot a
    person edits.  A missing/default texture is left alone rather than copied
    over the SDK's own default inventory.
    """
    lines = text.splitlines()
    compiled: dict[str, str] = {}
    source: dict[str, str] = {}
    in_compiled = False
    for line in lines:
        stripped = line.strip()
        if stripped == '"Compiled Textures"':
            in_compiled = True
            continue
        if in_compiled:
            if stripped == "}":
                break
            match = re.match(r'\s*"([^"]+)"\s+"([^"]+)"', line)
            if match:
                compiled[match.group(1)] = match.group(2)
            continue
        match = re.match(r'\s*"(Texture[^"]+)"\s+"([^"]+)"', line)
        if match:
            source[match.group(1)] = match.group(2)
    result: list[tuple[str, Path]] = []
    for key, fields in _TEXTURE_FIELDS.items():
        compiled_relative = compiled.get(key, "")
        if not compiled_relative:
            continue
        png = decompiled / Path(_safe_relative(compiled_relative)).with_suffix(".png")
        if not png.is_file():
            continue
        for field in fields:
            target = source.get(field, "").replace("\\", "/").strip("/")
            if (
                not target
                or target.startswith(("materials/default/", "materials/core/"))
                or not target.lower().endswith(
                    (".png", ".tga", ".jpg", ".jpeg", ".tif", ".tiff", ".dds", ".exr", ".hdr")
                )
            ):
                continue
            result.append((target, png))
    return result


def decompile_material_sources(
    env: Environment,
    root: Path,
    destination: Path,
    *,
    timeout: int = 900,
) -> MaterialSourceResult:
    """Recover editable vmat and texture sources from compiled material assets.

    Old addons often ship only resourcecompiler output.  Copying those files
    keeps the model renderable but leaves nothing a person can open in the
    CSDK material editor.  S2V can decompile the same folder it already used
    for the model; this helper preserves the package-relative paths, leaves
    existing source files alone, and never invents a shader for a failed
    decompile.
    """
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    compiled = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix.lower() in (".vmat_c", ".vtex_c")
    ]
    result = MaterialSourceResult()
    if not compiled:
        return result
    if env.s2v is None:
        result.error = "source-2-viewer-missing: choose the Source 2 Viewer CLI in Setup"
        return result
    destination.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".dmf-material-source-", dir=destination.parent))
    try:
        command = [
            str(env.s2v),
            "-i",
            str(root),
            "-o",
            str(temporary),
            "-d",
            "--recursive",
            "-e",
            "vmat_c,vtex_c",
        ]
        if env.gameinfo is not None:
            command += ["--game", str(env.gameinfo)]
        run = _log(env, command, destination.parent / "s2v-materials.log", timeout)
        if run.returncode != 0:
            result.error = (
                f"old-material-decompile-failed: {root}; see {destination.parent / 's2v-materials.log'}"
            )
            return result
        for source in sorted(temporary.rglob("*.vmat")):
            relative = source.relative_to(temporary)
            target = destination / relative
            if not target.exists():
                _copy(source, target)
                result.materials += 1
            else:
                result.skipped.append(relative.as_posix())
            text = source.read_text(encoding="utf-8", errors="replace")
            for texture_relative, png in _material_texture_pairs(text, temporary):
                texture_target = destination / _safe_relative(texture_relative)
                if texture_target.exists():
                    continue
                _copy(png, texture_target)
                result.textures += 1
    except (OSError, subprocess.SubprocessError, MigrationError) as error:
        result.error = str(error)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return result


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
    env: Environment | None = None,
    timeout: int = 1800,
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
    old_meshes = modeldoc.render_mesh_files(old_text)
    new_meshes = modeldoc.render_mesh_files(new_text)
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
    # The live RenderMeshList, BodyGroupList and LODGroupList stay in place.
    # They are what make the model visible in matchmaking and what give
    # PulseSrcOps's LOD build a slot to replace.  Old meshes are mapped onto
    # the live mesh names where possible, and only a genuinely new mesh is
    # appended.  Replacing these sections with an old list made the compiler
    # reject every live LOD and body-group reference.
    if "RenderMeshList" in requested:
        requested.remove("RenderMeshList")
    requested = list(dict.fromkeys(requested))

    merged = modeldoc.merge(new_text, old_text, requested)
    merged_text = merged.text

    # The live tree supplies the current animation set, skeleton and default
    # materials. The old addon overlays only the assets it owns.
    _copy_tree(new_root, root)
    old_material_count = 0
    old_texture_count = 0
    material_sources = MaterialSourceResult()
    if preserve_materials:
        old_material_count, old_texture_count = _copy_materials(old_root, root)
        if env is not None:
            material_sources = decompile_material_sources(
                env,
                old_root,
                root,
                timeout=timeout,
            )

    model_files: list[str] = []
    model_remap: dict[str, str] = {}
    mesh_actions: dict[str, dict[str, str]] = {}
    if keep_model:
        live_by_name = {item.name.casefold(): item for item in new_meshes}
        live_filenames = {item.filename.casefold() for item in new_meshes}
        old_body = None
        live_body = None
        try:
            old_dmx = [
                path
                for relative in old_render
                for path in [_old_asset(old_root, old_assets, relative)]
                if path is not None
            ]
            old_body = body_for_hero_folder(old_vmdl, old_dmx) if old_dmx else None
            live_dmx = [new_root / relative for relative in new_render]
            live_body = body_for_hero_folder(new_vmdl, live_dmx) if live_dmx else None
        except Exception:
            old_body = None
            live_body = None
        old_body_relative = ""
        if old_body is not None:
            try:
                old_body_relative = old_body.relative_to(old_root).as_posix()
            except ValueError:
                old_body_relative = old_body.name
        live_body_filename = ""
        if live_body is not None:
            try:
                live_body_filename = live_body.relative_to(new_root).as_posix()
            except ValueError:
                live_body_filename = live_body.name
        live_body_mesh = next(
            (item for item in new_meshes if item.filename == live_body_filename),
            None,
        )
        groups = modeldoc.body_groups(merged_text)
        default_group = next(
            (group for group in groups if group.name.casefold() == "default"),
            groups[0] if groups else None,
        )
        bodygroup = default_group.name if default_group is not None else ""
        choice = default_group.choices[0] if default_group and default_group.choices else ""
        for old_mesh in old_meshes:
            source = _old_asset(old_root, old_assets, old_mesh.filename)
            if source is None:
                raise MigrationError(f"old-model-missing: {old_mesh.filename}")
            # The old body is the mesh the old model's own Skeleton and
            # BodyGroupList choose.  Its decompiled name can be ``unnamed_1``
            # (Tokamak), so name matching alone leaves the live body in place
            # and adds the old body as an extra mesh.  Map the chosen old body
            # onto the live body slot first.
            is_old_body = bool(old_body_relative) and (
                old_mesh.filename == old_body_relative
                or source.resolve() == old_body.resolve()
            )
            live_mesh = live_body_mesh if is_old_body else live_by_name.get(old_mesh.name.casefold())
            if live_mesh is not None:
                # The old geometry takes the live mesh slot: same name, same
                # filename and the same body-group/LOD references.  The live
                # declarations stay intact, so matchmaking keeps its slots.
                relative_path = live_mesh.filename
                _copy(source, root / relative_path)
                model_files.append(relative_path)
                model_remap[old_mesh.filename] = relative_path
                continue

            relative_path = old_mesh.filename
            if relative_path.casefold() in live_filenames:
                relative_path = f"{Path(relative_path).stem}_old{Path(relative_path).suffix}"
            _copy(source, root / relative_path)
            added = modeldoc.add_render_mesh_file(
                merged_text,
                name=old_mesh.name,
                filename=relative_path,
                bodygroup=bodygroup,
                choice=choice,
            )
            merged_text = added.text
            merged_text = modeldoc.add_mesh_to_lod_groups(merged_text, old_mesh.name)
            model_files.append(relative_path)
            model_remap[old_mesh.filename] = relative_path
            mesh_actions[old_mesh.name] = dict(added.actions)
        # A modeldoc without mesh names cannot be mapped by RenderMeshFile
        # name.  Keep its live paths and copy the old bytes into those same
        # slots instead of dropping the old model.
        unmapped = [
            relative
            for relative in old_render
            if relative not in model_remap
        ]
        for relative_path in unmapped:
            source = _old_asset(old_root, old_assets, relative_path)
            if source is None:
                raise MigrationError(f"old-model-missing: {relative_path}")
            _copy(source, root / relative_path)
            model_files.append(relative_path)
            model_remap[relative_path] = relative_path
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
    vmdl_out.write_text(merged_text, encoding="utf-8", newline="\n")

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
            "new_root": str(new_root.resolve()),
            "new_vmdl_sha256": _digest(new_vmdl),
            "model_policy": preserve_model,
            "custom_model": custom,
            "preserved_model": keep_model,
            "model_files": model_files,
            "new_model_files": new_render,
            "model_remap": model_remap,
            "mesh_actions": mesh_actions,
            "materials": old_material_count,
            "material_textures": old_texture_count,
            "material_sources": material_sources.materials,
            "material_source_textures": material_sources.textures,
            "material_source_error": material_sources.error,
            "material_source_skipped": material_sources.skipped,
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


def resolve_package_source(
    env: Environment,
    package: Path,
    destination: Path,
    *,
    old_vmdl: str | Path | None = None,
    hero: str = "",
    matches=(),
    timeout: int = 1800,
) -> dict[str, object]:
    """Resolve an old package as an editable Source-page file set.

    This is the read-only counterpart to ``update_from_package``: it extracts a
    VPK (a folder is used in place), resolves the package's own vmdl (decompiling
    a compiled-only model when needed), and picks its body from the model's own
    RenderMeshList.  Nothing is migrated, recompiled, or staged into a CSDK.
    The caller receives the vmdl, body DMX and material root it can assign to the
    same Source fields an S2V extraction fills.

    A ``.blend`` is not a Source 2 package. A project that contains one is a
    Blender scene, so the addon binds that scene directly instead of asking S2V
    to treat the blend as a VPK.
    """
    package = Path(package).expanduser().resolve()
    if package.suffix.lower() in (".blend", ".blend1"):
        raise MigrationError(
            f"old-source-is-blend: {package}; open the project and use its scene as the source"
        )
    if not package.exists():
        raise MigrationError(f"old-package-missing: {package}")
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    old_root = extract_package(env, package, destination / "package", timeout=timeout)
    preferred = str(old_vmdl) if old_vmdl else None
    source_path, source_info = resolve_old_model(
        env,
        old_root,
        preferred=preferred,
        hero=hero,
        matches=matches,
        destination=destination / "decompiled",
        timeout=timeout,
    )
    assets_root = Path(source_info.get("assets_root") or old_root).resolve()
    if not assets_root.is_dir():
        assets_root = old_root.resolve()
    dmx_files = sorted(path for path in assets_root.rglob("*.dmx") if path.is_file())
    body = body_for_hero_folder(source_path, dmx_files) if dmx_files else None
    materials = material_files(assets_root)
    materials_root = assets_root
    material_sources = MaterialSourceResult()
    if source_info.get("kind") == "compiled":
        old_materials = material_files(old_root)
        if old_materials:
            # A compiled-only package's materials stay in the package, and the
            # Source page gets a content root that carries both the shipped
            # compiled assets and the editable sources recovered from them.
            # S2V's model decompile writes only the vmdl and its DMX references.
            materials = old_materials
            materials_root = destination / "materials"
            for item in old_materials:
                _copy(item.source, materials_root / item.relative)
            material_sources = decompile_material_sources(
                env,
                old_root,
                materials_root,
                timeout=timeout,
            )
    try:
        vmdl_relative = source_path.relative_to(assets_root).as_posix()
    except ValueError:
        vmdl_relative = source_path.name
    body_relative = ""
    if body is not None:
        try:
            body_relative = body.relative_to(assets_root).as_posix()
        except ValueError:
            body_relative = body.name
    return {
        "package": str(package),
        "root": str(assets_root),
        "vmdl": str(source_path),
        "vmdl_relative": vmdl_relative,
        "body_dmx": str(body) if body is not None else "",
        "body_relative": body_relative,
        "materials_dir": str(materials_root) if materials else "",
        "material_count": len(materials),
        "material_sources": material_sources.materials,
        "material_source_textures": material_sources.textures,
        "material_source_error": material_sources.error,
        "dmx_count": len(dmx_files),
        "source": source_info,
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
        env=env,
        timeout=timeout,
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
