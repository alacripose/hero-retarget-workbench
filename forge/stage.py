"""Stage live S2V files and replace the selected model and its LOD DMXs.

The hero vmdl is copied byte for byte. The stage manifest records the source
hash and the replacement hashes so a later compile can prove the vmdl was not
rewritten. Material files are copied verbatim; custom material files are copied
after the hero assets so a ported model's vmat paths win. Layers and options
live inside those files and are never flattened by this module.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .hashes import blake3_file


class StageError(ValueError):
    pass


# Material staging is a closed inventory, not "every file that is not a DMX".
# A material root may contain notes, thumbnails, source maps, or engine junk;
# none of that belongs in the compiler handoff.
MATERIAL_SUFFIXES = {
    ".vmat",
    ".vmat_c",
    ".vtex",
    ".vtex_c",
    ".png",
    ".jpg",
    ".jpeg",
    ".tga",
    ".tif",
    ".tiff",
    ".dds",
    ".bmp",
    ".exr",
    ".hdr",
    ".psd",
}
TEXTURE_SUFFIXES = MATERIAL_SUFFIXES - {".vmat", ".vmat_c"}


def is_material_asset(path: Path) -> bool:
    return path.suffix.lower() in MATERIAL_SUFFIXES


def is_texture_asset(path: Path) -> bool:
    return path.suffix.lower() in TEXTURE_SUFFIXES


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


@dataclass(frozen=True)
class MaterialCopy:
    source: Path
    relative: str


@dataclass
class StageRequest:
    extraction_root: Path
    vmdl: Path
    target_dmx: Path
    custom_dmx: Path
    target_dmx_relative: str
    vmdl_relative: str
    addon_name: str
    destination: Path
    materials: list[MaterialCopy] = field(default_factory=list)
    custom_materials: list[MaterialCopy] = field(default_factory=list)
    extra_files: list[MaterialCopy] = field(default_factory=list)
    custom_lods: list[Path] = field(default_factory=list)
    include_extraction: bool = True


@dataclass
class Staged:
    root: Path
    vmdl: Path
    custom_dmx: Path
    manifest: Path
    vmdl_sha256: str
    custom_sha256: str
    material_count: int
    material_texture_count: int = 0
    custom_material_count: int = 0
    custom_material_texture_count: int = 0
    custom_lods: list[Path] = field(default_factory=list)
    custom_lod_sha256: list[str] = field(default_factory=list)
    vmdl_blake3: str = ""
    custom_blake3: str = ""
    custom_lod_blake3: list[str] = field(default_factory=list)


def _safe_relative(value: str) -> str:
    path = value.replace("\\", "/").strip("/")
    if not path or ".." in path.split("/") or path.startswith("/"):
        raise StageError(f"unsafe-relative-path: {value!r}")
    return path


def _copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise StageError(f"missing-input: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def material_files(root: Path) -> list[MaterialCopy]:
    """Inventory material source/compiled assets and their texture images.

    Point this at a content root: the relative path below that root is preserved
    in the stage. The inventory is closed to ``MATERIAL_SUFFIXES`` so a folder of
    notes, JSON, thumbnails, or unrelated engine files cannot become a material
    handoff. Model and animation files are excluded by the same rule.
    """
    result = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and is_material_asset(path):
            result.append(MaterialCopy(path, path.relative_to(root).as_posix()))
    return result


def default_materials(extraction_root: Path) -> list[MaterialCopy]:
    return material_files(extraction_root)


def target_lod_relatives(extraction_root: Path, target_dmx_relative: str) -> list[str]:
    """Return the hero LOD DMX paths that the unchanged vmdl already references.

    The vmdl is opaque: its LOD filenames are not parsed. S2V emits the
    referenced DMX files beside the body, so the existing files are the
    authoritative target slots. They are sorted by their numeric suffix so a
    generated LOD1, LOD2, LOD3 set lines up with the hero's slots.
    """
    target = Path(target_dmx_relative.replace("\\", "/"))
    stem = target.stem
    folder = extraction_root.resolve() / target.parent
    if not folder.is_dir():
        folder = extraction_root.resolve()
    pattern = re.compile(rf"^{re.escape(stem)}_lod(\d+)$", re.IGNORECASE)
    found: list[tuple[int, str]] = []
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() != ".dmx":
            continue
        match = pattern.match(path.stem)
        if match:
            found.append((int(match.group(1)), path.relative_to(extraction_root.resolve()).as_posix()))
    return [relative for _, relative in sorted(found)]


def canonical_lod_relatives(target_dmx_relative: str, count: int) -> list[str]:
    target = Path(target_dmx_relative.replace("\\", "/"))
    return [
        (target.parent / f"{target.stem}_lod{index}.dmx").as_posix()
        for index in range(1, count + 1)
    ]


def stage(request: StageRequest) -> Staged:
    extraction = request.extraction_root.resolve()
    vmdl_source = request.vmdl.resolve()
    target_source = request.target_dmx.resolve()
    custom_source = request.custom_dmx.resolve()
    if not extraction.is_dir():
        raise StageError(f"missing-extraction-root: {extraction}")
    if vmdl_source.suffix.lower() != ".vmdl":
        raise StageError(f"not-a-vmdl: {vmdl_source}")
    if target_source.suffix.lower() != ".dmx" or custom_source.suffix.lower() != ".dmx":
        raise StageError("stage-expects-dmx: target and custom model must be .dmx")
    if not request.addon_name.strip():
        raise StageError("addon-name-blank")
    addon = _safe_relative(request.addon_name)
    vmdl_relative = _safe_relative(request.vmdl_relative)
    target_relative = _safe_relative(request.target_dmx_relative)

    custom_lods = [path.resolve() for path in request.custom_lods]
    for lod in custom_lods:
        if lod.suffix.lower() != ".dmx":
            raise StageError(f"stage-expects-dmx: custom LOD is not a .dmx: {lod}")

    existing_lods = target_lod_relatives(extraction, target_relative)
    if custom_lods:
        if existing_lods:
            lod_relatives = existing_lods
        else:
            lod_relatives = canonical_lod_relatives(target_relative, len(custom_lods))
        if len(lod_relatives) != len(custom_lods):
            raise StageError(
                "lod-count-mismatch: "
                f"the hero vmdl has {len(lod_relatives)} LOD slots and the export produced "
                f"{len(custom_lods)} LOD DMXs"
            )
    else:
        lod_relatives = []

    replacements: dict[str, Path] = {target_relative: custom_source}
    for relative, source in zip(lod_relatives, custom_lods):
        replacements[relative] = source

    root = request.destination.resolve() / "content" / "citadel_addons" / addon
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    vmdl_out = root / vmdl_relative
    custom_out = root / target_relative
    _copy(vmdl_source, vmdl_out)
    for relative, source in replacements.items():
        _copy(source, root / relative)

    material_copies = list(request.materials) if request.materials else default_materials(extraction)
    material_by_relative = {
        _safe_relative(material.relative): material for material in material_copies
    }
    copied_extraction = 0
    if request.include_extraction:
        for source in sorted(extraction.rglob("*")):
            if not source.is_file() or source.suffix.lower() == ".log":
                continue
            relative = source.relative_to(extraction).as_posix()
            if relative in replacements or relative == vmdl_relative:
                continue
            # The selected material root owns these paths; fall back to the
            # extraction for material assets it does not provide.
            if relative in material_by_relative:
                continue
            if source.resolve() in (target_source, vmdl_source):
                continue
            _copy(source, root / relative)
            copied_extraction += 1

    copied_materials = 0
    material_texture_count = 0
    for relative, material in material_by_relative.items():
        if relative in replacements or relative == vmdl_relative:
            continue
        _copy(material.source, root / relative)
        copied_materials += 1
        material_texture_count += int(is_texture_asset(material.source))

    # Custom material files are copied after the hero assets so a ported model's
    # pbr.vfx / status-effects-proxy / NPR vmat and its textures take precedence.
    custom_material_count = 0
    custom_material_texture_count = 0
    custom_by_relative = {
        _safe_relative(material.relative): material for material in request.custom_materials
    }
    for relative, material in custom_by_relative.items():
        if relative in replacements or relative == vmdl_relative:
            continue
        _copy(material.source, root / relative)
        custom_material_count += 1
        custom_material_texture_count += int(is_texture_asset(material.source))

    for extra in request.extra_files:
        relative = _safe_relative(extra.relative)
        if relative in replacements or relative == vmdl_relative:
            continue
        _copy(extra.source, root / relative)

    if digest(vmdl_out) != digest(vmdl_source):
        raise StageError("vmdl-changed-during-stage")
    staged_lods = [root / relative for relative in lod_relatives]
    manifest = root / "stage.json"
    manifest.write_text(
        json.dumps(
            {
                "addon": addon,
                "extraction": extraction.as_posix(),
                "vmdl": vmdl_relative,
                "vmdl_sha256": digest(vmdl_source),
                "vmdl_blake3": blake3_file(vmdl_source),
                "vmdl_modified": False,
                "target_dmx": target_relative,
                "target_dmx_sha256": digest(target_source),
                "target_dmx_blake3": blake3_file(target_source),
                "custom_dmx": target_relative,
                "custom_dmx_sha256": digest(custom_source),
                "custom_dmx_blake3": blake3_file(custom_source),
                "lods": [
                    {
                        "relative": relative,
                        "sha256": digest(root / relative),
                        "blake3": blake3_file(root / relative),
                        "source": source.as_posix(),
                    }
                    for relative, source in zip(lod_relatives, custom_lods)
                ],
                "materials": copied_materials,
                "material_textures": material_texture_count,
                "custom_materials": custom_material_count,
                "custom_material_textures": custom_material_texture_count,
                "material_policy": "copied-verbatim",
                "custom_material_policy": "overlay-verbatim",
                "extraction_files": copied_extraction,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return Staged(
        root=root,
        vmdl=vmdl_out,
        custom_dmx=custom_out,
        manifest=manifest,
        vmdl_sha256=digest(vmdl_source),
        custom_sha256=digest(custom_source),
        material_count=copied_materials,
        material_texture_count=material_texture_count,
        custom_material_count=custom_material_count,
        custom_material_texture_count=custom_material_texture_count,
        custom_lods=staged_lods,
        custom_lod_sha256=[digest(path) for path in staged_lods],
        vmdl_blake3=blake3_file(vmdl_source),
        custom_blake3=blake3_file(custom_source),
        custom_lod_blake3=[blake3_file(path) for path in staged_lods],
    )


def verify(staged: Staged) -> None:
    manifest = json.loads(staged.manifest.read_text(encoding="utf-8"))
    if manifest.get("vmdl_modified") is not False:
        raise StageError("stage-manifest-claims-vmdl-modified")
    if digest(staged.vmdl) != manifest["vmdl_sha256"]:
        raise StageError("staged-vmdl-hash-mismatch")
    if blake3_file(staged.vmdl) != manifest["vmdl_blake3"]:
        raise StageError("staged-vmdl-blake3-mismatch")
    if digest(staged.custom_dmx) != manifest["custom_dmx_sha256"]:
        raise StageError("staged-custom-dmx-hash-mismatch")
    if blake3_file(staged.custom_dmx) != manifest["custom_dmx_blake3"]:
        raise StageError("staged-custom-dmx-blake3-mismatch")
    for entry in manifest.get("lods", []):
        path = staged.root / entry["relative"]
        if not path.is_file() or digest(path) != entry["sha256"]:
            raise StageError("staged-lod-hash-mismatch")
        if blake3_file(path) != entry["blake3"]:
            raise StageError("staged-lod-blake3-mismatch")
