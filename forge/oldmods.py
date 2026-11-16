"""Find older downloaded VPKs and unpacked addons, and record what they carry.

A port starts from a package someone made months or years ago. Before choosing
one, the workbench needs a corpus: which packages exist on this machine, which
hero model each one targets, how old it is, and — for unpacked source addons —
which cloth/physics sections its vmdl actually carries. A compiled VPK is only
listed by directory (file names, CRC, archive offsets); its contents are never
decompiled or interpreted here.

The owner's drives hold both shapes: ``*.vpk`` downloads and unpacked
``content/citadel_addons/<name>`` trees left behind by older CSDK installs.
Game paks are excluded by name and by the folders they live in, so a scan can
walk a whole drive without turning the live game into a mod.
"""
from __future__ import annotations

import json
import os
import re
import struct
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

from .modeldoc import ModeldocError, cloth_physics_sections

VPK_SIGNATURE = 0x55AA1234
VPK_DIR_ARCHIVE = 0x7FFF
HERO_DIRS = ("heroes_staging", "heroes_wip", "heroes")
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    "$recycle.bin",
    "system volume information",
    "windows",
    "winsxs",
    "appdata",
}
SKIP_PATH_MARKERS = ("/game/citadel/", "/game/core/", "/game/csgo_imported/", "/dist/")
MOD_LAYOUT_DIRS = (
    "models",
    "materials",
    "clips",
    "scripts",
    "maps",
    "particles",
    "animgraphs",
    "soundevents",
    "sound",
    "sounds",
    "soundsets",
    "scenes",
    "anims",
    "animation",
    "vscripts",
    "resource",
    "abilities",
    "panorama",
    "pulse",
    "smartprops",
    "smart_props",
    "stats",
    "surfaceproperties",
    "textures",
    "events",
    "cfg",
    "dev",
    "postprocessing",
    "tools",
)
MOD_FILE_SUFFIXES = (
    ".vmdl",
    ".vmdl_c",
    ".blend",
    ".blend1",
    ".vmat",
    ".vmat_c",
    ".vnmclip",
    ".vnmclip_c",
    ".vsnd",
    ".vsnd_c",
    ".vpcf",
    ".vpcf_c",
    ".vmap",
    ".vmap_c",
    ".lua",
    ".vts",
    ".vjs",
    ".vts_c",
    ".vjs_c",
    ".vdata_c",
    ".vsvg_c",
    ".vxml_c",
    ".vcd_c",
    ".vnmgraph_c",
    ".vnmskel_c",
    ".vmix_c",
    ".vsndevts_c",
    ".vsndstck_c",
    ".vsurf_c",
    ".vpulse_c",
    ".vsmart_c",
    ".vrman_c",
    ".vpost_c",
    ".vfont",
    ".vtex_c",
)
MAX_VMDL_PER_ADDON = 24
MAX_LISTED_FILES = 300

_MONTHS = {
    name: index
    for index, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}

# What a package carries, in the terms the Mods page groups it by. A VPK entry
# and an unpacked file use the same test, so a folder and a pak describe
# themselves the same way.
CONTENT_CATEGORIES = {
    "models": (".vmdl", ".vmdl_c", ".dmx", ".mesh"),
    "clips": (".vnmclip", ".vnmclip_c", ".vnm"),
    "materials": (".vmat", ".vmat_c", ".vtex", ".vtex_c", ".png", ".tga", ".jpg", ".jpeg", ".exr", ".hdr"),
    "blends": (".blend", ".blend1"),
}


def content_category(path: str) -> str:
    """One of models, clips, materials, blends or other, from the file's name."""
    lower = str(path).replace("\\", "/").lower()
    suffix = PurePosixPath(lower).suffix
    for category, suffixes in CONTENT_CATEGORIES.items():
        if suffix in suffixes:
            return category
    if "/clips/" in lower:
        return "clips"
    if "/materials/" in lower:
        return "materials"
    return "other"


def content_counts(paths) -> dict[str, int]:
    counts = {category: 0 for category in (*CONTENT_CATEGORIES, "other")}
    for path in paths:
        counts[content_category(path)] += 1
    return counts


class OldModsError(ValueError):
    """A package could not be read as an old mod."""


@dataclass(frozen=True)
class VpkEntry:
    path: str
    crc: int
    preload: int
    archive_index: int
    offset: int
    length: int


@dataclass(frozen=True)
class VpkTree:
    version: int
    entries: tuple[VpkEntry, ...]

    @property
    def split(self) -> bool:
        return any(entry.archive_index != VPK_DIR_ARCHIVE for entry in self.entries)


def _cstring(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\0", offset)
    if end < 0:
        raise OldModsError("vpk-tree-string-unterminated")
    return data[offset:end].decode("utf-8", errors="replace"), end + 1


def parse_tree(data: bytes) -> tuple[VpkEntry, ...]:
    """Parse a VPK directory tree into entries.

    The tree is a list of extensions, each holding directories, each holding file
    names and a fixed-size entry record. Preload bytes follow the record.
    """
    entries: list[VpkEntry] = []
    offset = 0
    while True:
        extension, offset = _cstring(data, offset)
        if not extension:
            break
        while True:
            directory, offset = _cstring(data, offset)
            if not directory:
                break
            prefix = directory.rstrip("/") + "/" if directory else ""
            while True:
                filename, offset = _cstring(data, offset)
                if not filename:
                    break
                if offset + 18 > len(data):
                    raise OldModsError("vpk-tree-entry-truncated")
                crc, preload, archive_index, entry_offset, length = struct.unpack_from("<IHHII", data, offset)
                offset += 16
                terminator = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                if terminator != 0xFFFF:
                    raise OldModsError("vpk-tree-entry-has-no-terminator")
                if offset + preload > len(data):
                    raise OldModsError("vpk-tree-preload-truncated")
                offset += preload
                name = f"{filename}.{extension}" if extension else filename
                entries.append(
                    VpkEntry(
                        path=prefix + name,
                        crc=crc,
                        preload=preload,
                        archive_index=archive_index,
                        offset=entry_offset,
                        length=length,
                    )
                )
    return tuple(entries)


def read_vpk(path: Path) -> VpkTree:
    """Read a VPK's directory without touching its file data."""
    path = Path(path)
    with path.open("rb") as handle:
        header = handle.read(28)
        if len(header) < 12:
            raise OldModsError(f"vpk-header-truncated: {path}")
        signature, version, tree_size = struct.unpack_from("<III", header, 0)
        if signature != VPK_SIGNATURE:
            raise OldModsError(f"vpk-signature-invalid: {path}")
        if version == 1:
            header_size = 12
        elif version == 2:
            if len(header) < 28:
                raise OldModsError(f"vpk-header-truncated: {path}")
            header_size = 28
        else:
            raise OldModsError(f"vpk-version-unsupported: {version} ({path})")
        if tree_size > 32 * 1024 * 1024:
            raise OldModsError(f"vpk-tree-too-large: {tree_size} ({path})")
        handle.seek(header_size)
        tree = handle.read(tree_size)
    if len(tree) != tree_size:
        raise OldModsError(f"vpk-tree-truncated: {path}")
    return VpkTree(version=version, entries=parse_tree(tree))


def content_shape(path: Path) -> tuple[set[str], set[str]]:
    """The game pak's own top-level folders and file suffixes.

    A mod is valid when it carries a folder or a file type the game itself
    ships. That covers models, materials, clips, scripts, particles, sounds and
    every other resource family without a hand-maintained allowlist. The tree
    read is the same directory read the VPK lister already uses; nothing is
    extracted.
    """
    tree = read_vpk(Path(path))
    roots: set[str] = set()
    suffixes: set[str] = set()
    for entry in tree.entries:
        parts = PurePosixPath(entry.path).parts
        if len(parts) > 1:
            roots.add(parts[0].lower())
        suffix = PurePosixPath(entry.path).suffix.lower()
        if suffix:
            suffixes.add(suffix)
    return roots, suffixes


def build_date(value: str) -> date | None:
    """Read the release date from a ``steam.inf`` build label, or return None."""
    text = str(value or "").strip()
    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    match = re.search(r"\b([A-Za-z]{3})[a-z]*\s+(\d{1,2}),?\s+(\d{4})\b", text)
    if match:
        month = _MONTHS.get(match.group(1).lower())
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(2)))
            except ValueError:
                pass
    return None


def estimate_toolchain(modified: str, toolchains) -> str:
    """Predict the CSDK tool release a mod could have been compiled with.

    CSDK tools change far less often than the live game. A package carries the
    date it was last written, so the honest prediction is the latest CSDK build
    released by that date (or the next one when the date predates them all), not
    a made-up daily game build.
    ``toolchains`` is supplied by the caller from its detected compiler installs;
    no build number or owner path is baked into this module.
    """
    try:
        stamp = date.fromisoformat(str(modified))
    except (TypeError, ValueError):
        return ""
    rows = []
    for item in toolchains or ():
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            when, label = item[0], item[1]
        else:
            label = str(item)
            when = build_date(label)
        if isinstance(when, date) and when:
            rows.append((when, str(label)))
    if not rows:
        return ""
    rows = sorted(set(rows), key=lambda row: (row[0], row[1]))
    exact = [label for when, label in rows if when == stamp]
    if exact:
        return f"CSDK {_build_number(exact[-1])} ({stamp.isoformat()})"
    before = [row for row in rows if row[0] < stamp]
    after = [row for row in rows if row[0] > stamp]
    if before:
        label = f"CSDK {_build_number(before[-1][1])}"
        return f"{label} or newer" if after else label
    return f"CSDK {_build_number(after[0][1])} or older"


def _build_number(label: str) -> str:
    """The first token of a build label, which is the Steam build number."""
    parts = str(label or "").replace("CSDK", "").strip().split()
    return parts[0] if parts else "unknown"


def clean_slug(value: str) -> str:
    slug = value.strip().lower()
    for suffix in ("_rotation_test", "_backup", "_default", "_july", "_lod0", "_v2", "_v1"):
        if slug.endswith(suffix) and len(slug) > len(suffix):
            slug = slug[: -len(suffix)]
    return slug


def slug_from_model(relative: str) -> str:
    """Guess the hero slug from a model path, without knowing the live roster."""
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    lower = [part.lower() for part in parts]
    for marker in HERO_DIRS:
        if marker in lower:
            index = lower.index(marker)
            if index + 1 < len(parts):
                return clean_slug(parts[index + 1])
    return clean_slug(PurePosixPath(relative).stem)


def hero_slugs(paths) -> list[str]:
    return sorted({slug for slug in (slug_from_model(path) for path in paths) if slug})


def cloth_inventory(vmdl_paths) -> tuple[list[str], dict[str, list[str]]]:
    """Return the union of cloth/physics section names and per-model sections."""
    union: set[str] = set()
    per_model: dict[str, list[str]] = {}
    for path in vmdl_paths:
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            names = cloth_physics_sections(text)
        except (OSError, ModeldocError):
            names = []
        per_model[path.name] = names
        union.update(names)
    return sorted(union), per_model


@dataclass(frozen=True)
class ModRecord:
    path: str
    kind: str
    addon: str
    hero: str
    bytes: int
    modified: str
    toolchain: str = ""
    models: tuple[str, ...] = ()
    cloth_sections: tuple[str, ...] = ()
    per_model: dict[str, list[str]] = field(default_factory=dict)
    blends: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "addon": self.addon,
            "hero": self.hero,
            "bytes": self.bytes,
            "modified": self.modified,
            "toolchain": self.toolchain,
            "models": list(self.models),
            "cloth_sections": list(self.cloth_sections),
            "per_model": self.per_model,
            "blends": list(self.blends),
            "files": list(self.files),
            "counts": dict(self.counts),
            "note": self.note,
        }


@dataclass
class Inventory:
    roots: list[str]
    since: str
    until: str
    mods: list[ModRecord]
    skipped_game_paks: int
    skipped_unreadable: list[str]

    def counts(self) -> dict[str, int]:
        return {
            "packages": len(self.mods),
            "vpks": sum(1 for mod in self.mods if mod.kind == "vpk"),
            "addons": sum(1 for mod in self.mods if mod.kind == "addon"),
            "folders": sum(1 for mod in self.mods if mod.kind == "addon"),
            "blends": sum(1 for mod in self.mods if mod.kind == "blend"),
            "files": sum(sum(mod.counts.values()) for mod in self.mods),
            "blend_files": sum(len(mod.blends) for mod in self.mods),
            "with_cloth_sections": sum(1 for mod in self.mods if mod.cloth_sections),
            "without_cloth_sections": sum(1 for mod in self.mods if not mod.cloth_sections),
            "hero_packages": sum(
                1 for mod in self.mods if any("hero" in model.lower() for model in mod.models)
            ),
            "skipped_game_paks": self.skipped_game_paks,
        }

    def cloth_types(self) -> dict[str, int]:
        types: dict[str, int] = {}
        for mod in self.mods:
            for name in mod.cloth_sections:
                types[name] = types.get(name, 0) + 1
        return dict(sorted(types.items()))

    def to_dict(self) -> dict:
        return {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "roots": self.roots,
            "since": self.since,
            "until": self.until,
            "counts": self.counts(),
            "cloth_types": self.cloth_types(),
            "skipped_unreadable": self.skipped_unreadable,
            "mods": [mod.to_dict() for mod in self.mods],
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path


def _is_game_pak(path: Path) -> bool:
    name = path.name.lower()
    if name.startswith("pak0") or name.startswith("pak1"):
        return True
    if name.startswith("shaders_"):
        return True
    if "bakeresourcecache" in name:
        return True
    marker = "/" + path.as_posix().lower().lstrip("/")
    return any(part in marker for part in SKIP_PATH_MARKERS)


def _within(path: Path, since: date | None, until: date | None) -> bool:
    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return False
    if since is not None and stamp < since:
        return False
    if until is not None and stamp > until:
        return False
    return True


def _looks_like_mod_dir(
    path: Path,
    known_roots: set[str] | None = None,
    known_suffixes: set[str] | None = None,
) -> bool:
    """A folder that carries a mod tree, even when its files are nested deeper.

    The owner's collection roots are one folder per mod. Those folders are not
    always under a ``citadel_addons`` parent: some are a bare ``models/heroes_*``
    scaffold, some hold only compiled ``.vmdl_c`` files, and some hold maps or
    scripts. Recognize the top-level shape here so a collection root can list
    its own children instead of only the VPKs sitting beside them.
    """
    roots = set(MOD_LAYOUT_DIRS) | set(known_roots or ())
    suffixes = set(MOD_FILE_SUFFIXES) | set(known_suffixes or ())
    if path.name.lower() in roots:
        return True
    for current, dirs, files in os.walk(path):
        dirs[:] = [
            name
            for name in dirs
            if name.lower() not in SKIP_DIRS and name.lower() != "citadel_addons"
        ]
        if any(name.lower() in roots for name in dirs):
            return True
        if any(PurePosixPath(name).suffix.lower() in suffixes for name in files):
            return True
    return False


def _top_level_packages(
    root: Path,
    known_roots: set[str] | None = None,
    known_suffixes: set[str] | None = None,
) -> tuple[list[Path], bool]:
    """The immediate mod folders under a scan root, and whether it is a collection.

    A collection root is a folder whose immediate children look like mods. Only
    those children become packages; an empty ``New Folder`` beside them is not a
    VPK-like tree and stays out. A scan root that only happens to contain a
    ``citadel_addons`` tree keeps the old explicit behavior and does not turn
    ``content`` or ``game`` into a package.
    """
    try:
        children = sorted(
            child
            for child in root.iterdir()
            if child.is_dir()
            and child.name.lower() not in SKIP_DIRS
            and child.name.lower() != "citadel_addons"
        )
    except OSError:
        return [], False
    candidates = [
        child
        for child in children
        if _looks_like_mod_dir(child, known_roots, known_suffixes)
    ]
    collection = len(candidates) >= 3
    return candidates, collection


def _date(stamp: float) -> str:
    return datetime.fromtimestamp(stamp).date().isoformat()


def _walk_dirs(root: Path, max_depth: int):
    root = root.resolve()
    base_depth = len(root.parts)
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        dirs[:] = [
            name
            for name in dirs
            if name.lower() not in SKIP_DIRS and depth < max_depth
        ]
        yield current_path, depth


def _addon_from_dir(
    path: Path,
    since: date | None,
    until: date | None,
    *,
    allow_empty: bool = False,
    toolchains=(),
) -> ModRecord | None:
    files = sorted(
        (item for item in path.rglob("*") if item.is_file()),
        key=lambda item: str(item).lower(),
    )
    model_files = sorted(
        item for item in files if item.suffix.lower() in (".vmdl", ".vmdl_c")
    )[:MAX_VMDL_PER_ADDON]
    text_models = [item for item in model_files if item.suffix.lower() == ".vmdl"]
    blends = tuple(
        item.relative_to(path).as_posix()
        for item in files
        if item.suffix.lower() in (".blend", ".blend1")
    )
    if not model_files and not blends and not allow_empty:
        return None
    newest = max(files, key=lambda item: item.stat().st_mtime) if files else path
    if not _within(newest, since, until):
        return None
    modified = _date(newest.stat().st_mtime)
    models = [item.relative_to(path).as_posix() for item in model_files]
    cloth, per_model = cloth_inventory(text_models)
    relative_files = tuple(item.relative_to(path).as_posix() for item in files)
    listed = relative_files[:MAX_LISTED_FILES]
    counts = content_counts(relative_files)
    notes = []
    if not model_files and not blends:
        notes.append("no-model")
    elif not cloth and text_models:
        notes.append("no-cloth-sections")
    if not files:
        notes.append("empty-folder")
    return ModRecord(
        path=str(path),
        kind="addon",
        addon=path.name,
        hero=", ".join(hero_slugs(models)) if models else "",
        bytes=sum(item.stat().st_size for item in files),
        modified=modified,
        toolchain=estimate_toolchain(modified, toolchains),
        models=tuple(models),
        cloth_sections=tuple(cloth),
        per_model=per_model,
        blends=blends,
        files=listed,
        counts=counts,
        note=", ".join(notes),
    )


def _blend_record(
    path: Path,
    since: date | None,
    until: date | None,
    toolchains=(),
) -> ModRecord | None:
    if not _within(path, since, until):
        return None
    name = path.stem
    modified = _date(path.stat().st_mtime)
    return ModRecord(
        path=str(path),
        kind="blend",
        addon=name,
        hero=clean_slug(path.parent.name),
        bytes=path.stat().st_size,
        modified=modified,
        toolchain=estimate_toolchain(modified, toolchains),
        blends=(path.name,),
        files=(path.name,),
        counts=content_counts((path.name,)),
        note="blender-project",
    )


def _vpk_record(
    path: Path,
    since: date | None,
    until: date | None,
    toolchains=(),
) -> ModRecord | None:
    if not _within(path, since, until):
        return None
    tree = read_vpk(path)
    compiled = [
        entry.path
        for entry in tree.entries
        if entry.path.lower().endswith((".vmdl_c", ".vmdl"))
    ]
    models = sorted(path for path in compiled if "hero" in path.lower())
    chosen = models or compiled
    slug = ", ".join(hero_slugs(chosen)) if chosen else clean_slug(path.stem)
    entries = tuple(entry.path for entry in tree.entries)
    note = ""
    if tree.split:
        note = "split-archives"
    if not compiled:
        note = f"{note}, no-compiled-model".strip(", ")
    modified = _date(path.stat().st_mtime)
    return ModRecord(
        path=str(path),
        kind="vpk",
        addon=path.stem,
        hero=slug,
        bytes=path.stat().st_size,
        modified=modified,
        toolchain=estimate_toolchain(modified, toolchains),
        models=tuple(chosen[:MAX_VMDL_PER_ADDON]),
        blends=tuple(item for item in entries if content_category(item) == "blends"),
        files=entries[:MAX_LISTED_FILES],
        counts=content_counts(entries),
        note=note,
    )


def inventory(
    roots,
    *,
    since: date | None = None,
    until: date | None = None,
    max_depth: int = 7,
    progress=None,
    known_roots: set[str] | None = None,
    known_suffixes: set[str] | None = None,
    toolchains=(),
) -> Inventory:
    """Scan roots for VPKs and unpacked citadel addons.

    ``progress`` is an optional ``(fraction, message)`` callback. The scan can
    walk tens of thousands of directories, and a button with no moving state
    reads as a button that did nothing.
    """
    mods: list[ModRecord] = []
    seen: set[str] = set()
    addon_roots: list[Path] = []
    skipped_game_paks = 0
    skipped_unreadable: list[str] = []
    resolved_roots = [Path(root).expanduser().resolve() for root in roots]
    total_roots = max(1, len(resolved_roots))

    for root_index, root in enumerate(resolved_roots):
        base = root_index / total_roots
        span = 1.0 / total_roots
        if progress is not None:
            progress(base + span * 0.01, f"scanning {root.name or root}")
        if not root.exists():
            skipped_unreadable.append(f"root-missing: {root}")
            continue

        top_packages, collection = _top_level_packages(root, known_roots, known_suffixes)
        if top_packages:
            if progress is not None:
                progress(base + span * 0.03, f"{root.name}: {len(top_packages)} folders")
            for child in top_packages:
                key = str(child.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                record = _addon_from_dir(
                    child,
                    since,
                    until,
                    allow_empty=collection or child != root,
                    toolchains=toolchains,
                )
                if record is not None:
                    mods.append(record)
                    addon_roots.append(child.resolve())

        walked = list(_walk_dirs(root, max_depth))
        step = max(1, len(walked) // 100)
        for index, (current, _depth) in enumerate(walked):
            if progress is not None and index % step == 0:
                progress(
                    base + span * (0.05 + 0.9 * index / max(1, len(walked))),
                    f"{current.name}: {len(mods)} found",
                )
            lower = current.name.lower()
            if lower == "citadel_addons":
                for child in sorted(current.iterdir()):
                    if not child.is_dir():
                        continue
                    key = str(child.resolve()).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    record = _addon_from_dir(child, since, until, toolchains=toolchains)
                    if record is not None:
                        mods.append(record)
                        addon_roots.append(child.resolve())
            for name in current.glob("*.blend"):
                if not name.is_file():
                    continue
                resolved = name.resolve()
                if any(parent == resolved.parent or parent in resolved.parents for parent in addon_roots):
                    continue
                key = str(resolved).lower()
                if key in seen:
                    continue
                seen.add(key)
                record = _blend_record(name, since, until, toolchains=toolchains)
                if record is not None:
                    mods.append(record)
            for name in current.glob("*.vpk"):
                if not name.is_file():
                    continue
                if _is_game_pak(name):
                    skipped_game_paks += 1
                    continue
                key = str(name.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    record = _vpk_record(name, since, until, toolchains=toolchains)
                except (OldModsError, OSError) as error:
                    skipped_unreadable.append(f"{error}")
                    continue
                if record is not None:
                    mods.append(record)

    mods.sort(key=lambda mod: (mod.modified, mod.path), reverse=True)
    return Inventory(
        roots=[str(root) for root in resolved_roots],
        since=since.isoformat() if since else "",
        until=until.isoformat() if until else "",
        mods=mods,
        skipped_game_paks=skipped_game_paks,
        skipped_unreadable=skipped_unreadable,
    )
