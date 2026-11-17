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
import hashlib
import os
import re
import struct
import zlib
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

# Hash matching is deliberately limited to source and compiled assets a port
# can consume. Walking every sound or texture in a 4 GB package would make the
# scan slower without answering the question the Mods page asks.
HASH_SUFFIXES = (
    ".vmdl",
    ".vmdl_c",
    ".dmx",
    ".vmat",
    ".vmat_c",
    ".vtex",
    ".vtex_c",
    ".vnmclip",
    ".vnmclip_c",
    ".vnmskel",
    ".vnmskel_c",
)
_CHUNK_VPK = re.compile(r"_\d{3}\.vpk$", re.IGNORECASE)

# Loose matching only needs folders that can carry a hashable asset. Walking a
# whole engine or game tree (bin, maps, cache, logs) is the slow part on a big
# install and cannot produce a match.
HASH_ROOT_DIRS = ("models", "materials", "clips", "particles", "anims", "animation")
VPK_SKIP_DIRS = set(SKIP_DIRS) | {
    "bin",
    "bin_tools",
    "platform",
    "tools",
    "cache",
    "logs",
}

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


def _content_digest(path: Path) -> tuple[int, str]:
    """CRC32 and SHA-256 of one file, read once.

    A VPK directory stores CRC32 for every entry, so CRC32 is the identity that
    can be compared without extracting game data. SHA-256 keeps the receipt
    useful when two different files happen to share a size and a CRC.
    """
    crc = 0
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            crc = zlib.crc32(block, crc)
            sha.update(block)
    return crc & 0xFFFFFFFF, sha.hexdigest()


def _content_crc(path: Path) -> int:
    """CRC32 of one installed loose file.

    Matching only needs the identity a VPK directory already carries. The
    installed side is the slow side, so it does not spend time computing the
    SHA-256 receipt that is useful on the mod side.
    """
    crc = 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            crc = zlib.crc32(block, crc)
    return crc & 0xFFFFFFFF


def _is_compiled_suffix(value: str) -> bool:
    return PurePosixPath(str(value).replace("\\", "/")).suffix.lower().endswith("_c")


# A rescan of the same CSDK should not re-read every matching source file. The
# key includes size and mtime, so an edited asset is hashed again.
_LOOSE_CRC_CACHE: dict[str, tuple[int, int, int]] = {}
_MOD_HASH_CACHE: dict[str, tuple[int, int, int, str]] = {}


def _file_hash(relative: str, path: Path) -> FileHash | None:
    key = str(path).lower()
    try:
        stat = path.stat()
        cached = _MOD_HASH_CACHE.get(key)
        if cached is not None and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
            crc, digest = cached[2], cached[3]
        else:
            crc, digest = _content_digest(path)
            stat = path.stat()
            _MOD_HASH_CACHE[key] = (stat.st_size, stat.st_mtime_ns, crc, digest)
        size = stat.st_size
    except OSError:
        return None
    return FileHash(relative=relative, size=size, crc32=crc, sha256=digest)


@dataclass(frozen=True)
class FileHash:
    """The identity of one mod-side file."""

    relative: str
    size: int
    crc32: int
    sha256: str = ""

    def to_dict(self) -> dict:
        return {
            "relative": self.relative,
            "size": self.size,
            "crc32": self.crc32,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class HashMatch:
    """A mod file that is byte-identical to a file in an installed build.

    ``container`` is a VPK for compiled game files or the loose file itself in
    noaddon layouts. ``entry`` is the logical path inside that container. That
    is enough for ``migrate`` to ask Source 2 Viewer to decompile the installed
    copy without guessing which build or folder owns the model.
    """

    relative: str
    install: str
    label: str
    build: str
    kind: str
    container: str
    entry: str
    size: int
    crc32: int
    gameinfo: str = ""

    def to_dict(self) -> dict:
        return {
            "relative": self.relative,
            "install": self.install,
            "label": self.label,
            "build": self.build,
            "kind": self.kind,
            "container": self.container,
            "entry": self.entry,
            "size": self.size,
            "crc32": self.crc32,
            "gameinfo": self.gameinfo,
        }


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
    hashes: tuple[FileHash, ...] = ()
    matches: tuple[HashMatch, ...] = ()

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
            "hashes": [item.to_dict() for item in self.hashes],
            "matches": [item.to_dict() for item in self.matches],
        }


@dataclass
class Inventory:
    roots: list[str]
    since: str
    until: str
    mods: list[ModRecord]
    skipped_game_paks: int
    skipped_unreadable: list[str]
    installs: tuple[str, ...] = ()
    hash_note: str = ""

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
            "hash_matches": sum(len(mod.matches) for mod in self.mods),
            "matched_packages": sum(1 for mod in self.mods if mod.matches),
            "installs_scanned": len(self.installs),
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
            "installs": list(self.installs),
            "hash_note": self.hash_note,
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


def _install_root(install) -> Path:
    if hasattr(install, "root"):
        return Path(install.root).expanduser()
    return Path(install).expanduser()


def _install_loose_roots(root: Path) -> list[Path]:
    """Where an install can leave compiled files without an addon.

    A CSDK can compile straight into its engine folder, and a source addon can
    live under any ``content/*_addons`` folder. Reading only ``citadel`` and
    ``core`` missed tools trees such as ``CSwin64`` and any future engine name,
    so this follows the tree's own ``gameinfo.gi`` files and addon folders.
    """
    def hash_roots(base: Path) -> list[Path]:
        found = [base / name for name in HASH_ROOT_DIRS if (base / name).is_dir()]
        return found or [base]

    def addon_hash_roots(base: Path) -> list[Path]:
        # A ``citadel_addons`` folder is a collection of addons, not one addon.
        # Walking its 260k-file root was the CSDK12 stall; reading each addon's
        # models/materials/clips keeps the same matches and skips the rest.
        if not any((base / name).is_dir() for name in HASH_ROOT_DIRS):
            try:
                children = [child for child in sorted(base.iterdir()) if child.is_dir()]
            except OSError:
                children = []
            if children:
                return [path for child in children for path in hash_roots(child)]
        return hash_roots(base)

    roots: list[Path] = []
    game = root / "game"
    if game.is_dir():
        try:
            engine_roots = [
                child
                for child in sorted(game.iterdir())
                if child.is_dir() and (child / "gameinfo.gi").is_file()
            ]
        except OSError:
            engine_roots = []
        if engine_roots:
            for engine in engine_roots:
                roots.extend(hash_roots(engine))
        else:
            # Old test fixtures and stripped tools trees can omit gameinfo.gi.
            for name in ("citadel", "core"):
                candidate = game / name
                if candidate.is_dir():
                    roots.extend(hash_roots(candidate))
            if not roots:
                roots.extend(hash_roots(game))
    elif root.name.lower() in ("game", "citadel", "core"):
        roots.extend(hash_roots(root))

    for content in (root / "content", root / "citadel_addons"):
        if not content.is_dir():
            continue
        try:
            addon_roots = [
                child
                for child in sorted(content.iterdir())
                if child.is_dir() and child.name.lower().endswith("addons")
            ]
        except OSError:
            addon_roots = []
        if addon_roots:
            for addon_root in addon_roots:
                roots.extend(addon_hash_roots(addon_root))
        elif content.name.lower() == "citadel_addons":
            roots.extend(addon_hash_roots(content))

    unique: dict[str, Path] = {}
    for candidate in roots:
        try:
            key = str(candidate.resolve()).lower()
        except OSError:
            key = str(candidate).lower()
        unique.setdefault(key, candidate)
    return list(unique.values())


def _install_vpks(root: Path) -> list[Path]:
    found: dict[str, Path] = {}
    base_depth = len(root.parts)
    try:
        for current, dirs, files in os.walk(root):
            depth = len(Path(current).parts) - base_depth
            if depth >= 6:
                dirs[:] = []
            else:
                dirs[:] = [name for name in dirs if name.lower() not in VPK_SKIP_DIRS]
            for name in files:
                if not name.lower().endswith(".vpk") or _CHUNK_VPK.search(name):
                    continue
                lower = name.lower()
                if "bakeresourcecache" in lower or lower.startswith(("shaders_", "toolscene_")):
                    # These paks hold compiled shader/cache data, never a model,
                    # clip or material entry the matcher can use.
                    continue
                path = Path(current) / name
                found.setdefault(str(path.resolve()).lower(), path)
    except OSError:
        return []
    return list(found.values())


def _install_gameinfo(root: Path) -> Path | None:
    for candidate in sorted((root / "game").glob("*/gameinfo.gi")):
        if candidate.is_file():
            return candidate
    for candidate in (root / "gameinfo.gi", root / "citadel" / "gameinfo.gi"):
        if candidate.is_file():
            return candidate
    return None


def match_installs(mods, installs, *, progress=None, stage=None) -> list[ModRecord]:
    """Attach byte-identical files from every detected install to each mod.

    The mod side is hashed once. A VPK entry already carries the CRC32 and byte
    length, so a game pak can be compared by reading its directory only. Loose
    files in a noaddon CSDK are hashed only when their size matches a mod file,
    which keeps a full game install from being read end to end.
    """
    wanted: dict[tuple[int, int], list[tuple[ModRecord, FileHash]]] = {}
    sizes: set[int] = set()
    for mod in mods:
        for item in mod.hashes:
            if item.size <= 0:
                continue
            wanted.setdefault((item.size, item.crc32), []).append((mod, item))
            sizes.add(item.size)
    if not wanted or not installs:
        if stage is not None:
            stage(
                "match",
                "Match installed builds",
                1.0,
                "no model hashes to match",
                "DONE",
            )
        return list(mods)

    matches: dict[str, list[HashMatch]] = {}
    seen: set[tuple] = set()
    match_count = 0
    source_count = 0

    def add(mod, item, install, kind, container, entry, gameinfo="") -> None:
        nonlocal match_count, source_count
        root = _install_root(install)
        key = (mod.path, item.relative, str(root), kind, str(container), entry)
        if key in seen:
            return
        seen.add(key)
        matches.setdefault(mod.path, []).append(
            HashMatch(
                relative=item.relative,
                install=str(root),
                label=str(getattr(install, "label", root.name)),
                build=str(getattr(install, "build", "")),
                kind=kind,
                container=str(container),
                entry=entry,
                size=item.size,
                crc32=item.crc32,
                gameinfo=gameinfo,
            )
        )
        match_count += 1
        if not _is_compiled_suffix(item.relative):
            source_count += 1

    installs = list(installs)
    total = max(1, len(installs))

    def report(index: int, fraction: float, message: str) -> None:
        if progress is not None:
            progress(min(1.0, (index + fraction) / total), message)
        if stage is not None:
            stage(
                "match",
                "Match installed builds",
                min(1.0, (index + fraction) / total),
                message,
                "RUNNING",
            )

    for index, install in enumerate(installs):
        root = _install_root(install)
        report(index, 0.0, f"matching {root.name or root}")
        gameinfo = _install_gameinfo(root)
        gameinfo_text = str(gameinfo) if gameinfo else ""
        vpks = _install_vpks(root)
        for vpk_index, vpk in enumerate(vpks):
            report(
                index,
                0.05 + 0.50 * (vpk_index / max(1, len(vpks))),
                f"matching {root.name or root}: {vpk.name} ({match_count} matches, {source_count} source)",
            )
            try:
                tree = read_vpk(vpk)
            except (OldModsError, OSError):
                continue
            for entry_index, entry in enumerate(tree.entries):
                if entry_index % 4096 == 0:
                    report(
                        index,
                        0.05 + 0.50 * (vpk_index / max(1, len(vpks))),
                        f"matching {root.name or root}: {vpk.name} ({match_count} matches, {source_count} source)",
                    )
                if PurePosixPath(entry.path).suffix.lower() not in HASH_SUFFIXES:
                    continue
                size = entry.length + entry.preload
                for mod, item in wanted.get((size, entry.crc), ()):
                    add(mod, item, install, "vpk", vpk, entry.path, gameinfo_text)
        loose_roots = _install_loose_roots(root)
        for loose_index, loose_root in enumerate(loose_roots):
            loose_start = 0.55 + 0.45 * (loose_index / max(1, len(loose_roots)))
            loose_end = 0.55 + 0.45 * ((loose_index + 1) / max(1, len(loose_roots)))
            report(
                index,
                loose_start,
                f"matching {root.name or root}: {loose_root.name}",
            )
            candidates: list[tuple[Path, int, int]] = []
            walked = 0
            for current, dirs, files in os.walk(loose_root):
                dirs[:] = [
                    name
                    for name in dirs
                    if name.lower() not in SKIP_DIRS
                    and name.lower() not in ("bin", "bin_tools", "platform", "tools")
                ]
                for name in files:
                    walked += 1
                    if walked % 1024 == 0:
                        report(
                            index,
                            loose_start,
                            f"matching {root.name or root}: scanned {walked} files "
                            f"({match_count} matches, {source_count} source)",
                        )
                    if PurePosixPath(name).suffix.lower() not in HASH_SUFFIXES:
                        continue
                    path = Path(current) / name
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    size = stat.st_size
                    if size not in sizes:
                        continue
                    candidates.append((path, size, stat.st_mtime_ns))
            report(
                index,
                loose_start + 0.10 * (loose_end - loose_start),
                f"matching {root.name or root}: hashing {len(candidates)} loose files "
                f"({match_count} matches, {source_count} source)",
            )
            hashing_start = loose_start + 0.10 * (loose_end - loose_start)
            for file_index, (path, size, modified) in enumerate(candidates):
                report(
                    index,
                    hashing_start
                    + (loose_end - hashing_start)
                    * (file_index / max(1, len(candidates))),
                    f"matching {root.name or root}: {file_index}/{len(candidates)} loose "
                    f"({match_count} matches, {source_count} source)",
                )
                key = str(path).lower()
                cached = _LOOSE_CRC_CACHE.get(key)
                if cached is not None and cached[0] == size and cached[1] == modified:
                    crc = cached[2]
                else:
                    try:
                        crc = _content_crc(path)
                    except OSError:
                        continue
                    _LOOSE_CRC_CACHE[key] = (size, modified, crc)
                for mod, item in wanted.get((size, crc), ()):
                    add(mod, item, install, "loose", path, path.name, gameinfo_text)
        report(
            index,
            1.0,
            f"matching {root.name or root}: {match_count} matches, {source_count} source",
        )
    if progress is not None:
        progress(1.0, f"matching complete: {match_count} matches, {source_count} source")
    if stage is not None:
        stage(
            "match",
            "Match installed builds",
            1.0,
            f"{match_count} matches, {source_count} source",
            "DONE",
        )
    return [
        ModRecord(
            path=mod.path,
            kind=mod.kind,
            addon=mod.addon,
            hero=mod.hero,
            bytes=mod.bytes,
            modified=mod.modified,
            toolchain=mod.toolchain,
            models=mod.models,
            cloth_sections=mod.cloth_sections,
            per_model=mod.per_model,
            blends=mod.blends,
            files=mod.files,
            counts=mod.counts,
            note=mod.note,
            hashes=mod.hashes,
            matches=tuple(matches.get(mod.path, ())),
        )
        for mod in mods
    ]


def _addon_from_dir(
    path: Path,
    since: date | None,
    until: date | None,
    *,
    allow_empty: bool = False,
    toolchains=(),
    progress=None,
) -> ModRecord | None:
    files: list[Path] = []
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        files.append(item)
        if progress is not None and len(files) % 256 == 0:
            progress(f"reading {path.name}: {len(files):,} files")
    files.sort(key=lambda item: str(item).lower())
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
    hash_files = [item for item in files if item.suffix.lower() in HASH_SUFFIXES]
    hashes_list: list[FileHash] = []
    for index, item in enumerate(hash_files):
        if progress is not None and (index % 64 == 0 or index == len(hash_files) - 1):
            progress(f"hashing {path.name}: {index + 1}/{len(hash_files)}")
        found = _file_hash(item.relative_to(path).as_posix(), item)
        if found is not None:
            hashes_list.append(found)
    hashes = tuple(hashes_list)
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
        hashes=hashes,
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
    hashes = tuple(
        FileHash(
            relative=entry.path,
            size=entry.length + entry.preload,
            crc32=entry.crc,
        )
        for entry in tree.entries
        if PurePosixPath(entry.path).suffix.lower() in HASH_SUFFIXES
        and entry.length + entry.preload > 0
    )
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
        hashes=hashes,
    )


def inventory(
    roots,
    *,
    since: date | None = None,
    until: date | None = None,
    max_depth: int = 7,
    progress=None,
    stage=None,
    known_roots: set[str] | None = None,
    known_suffixes: set[str] | None = None,
    toolchains=(),
    installs=(),
) -> Inventory:
    """Scan roots for VPKs and unpacked citadel addons.

    ``progress`` is an optional ``(fraction, message)`` callback. ``stage`` is
    an optional ``(key, label, fraction, message, state)`` callback for named
    sub-bars: each scan root and the install matcher report separately, so a
    slow package read cannot hide which stage is working.
    """
    mods: list[ModRecord] = []
    seen: set[str] = set()
    addon_roots: list[Path] = []
    skipped_game_paks = 0
    skipped_unreadable: list[str] = []
    resolved_roots = [Path(root).expanduser().resolve() for root in roots]
    total_roots = max(1, len(resolved_roots))
    install_list = list(installs)
    scan_span = 0.80 if install_list else 1.0

    def mark(key, label, value, message, state="RUNNING") -> None:
        if stage is not None:
            stage(key, label, value, message, state)

    root_labels = [
        f"Folder {index + 1}/{total_roots}: {root.name or root}"
        for index, root in enumerate(resolved_roots)
    ]
    for index, label in enumerate(root_labels):
        mark(f"root:{index}", label, 0.0, "queued", "QUEUED")

    for root_index, root in enumerate(resolved_roots):
        base = scan_span * root_index / total_roots
        span = scan_span / total_roots
        root_key = f"root:{root_index}"
        root_label = root_labels[root_index]
        mark(root_key, root_label, 0.0, "finding packages")
        if progress is not None:
            progress(base + span * 0.01, f"scanning {root.name or root}")
        if not root.exists():
            skipped_unreadable.append(f"root-missing: {root}")
            mark(root_key, root_label, 1.0, "folder is missing", "DONE")
            continue

        top_packages, collection = _top_level_packages(root, known_roots, known_suffixes)
        if top_packages:
            if progress is not None:
                progress(base + span * 0.03, f"{root.name}: {len(top_packages)} folders")
            mark(root_key, root_label, 0.03, f"{len(top_packages)} folders")
            total_packages = max(1, len(top_packages))
            for child_index, child in enumerate(top_packages):
                package_fraction = 0.05 + 0.55 * (child_index / total_packages)
                package_message = (
                    f"reading {child.name} ({child_index + 1}/{len(top_packages)})"
                )
                mark(root_key, root_label, package_fraction, package_message)
                if progress is not None:
                    progress(base + span * package_fraction, package_message)

                def package_step(
                    text,
                    key=root_key,
                    label=root_label,
                    value=package_fraction,
                ):
                    mark(key, label, value, text)

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
                    progress=package_step,
                )
                if record is not None:
                    mods.append(record)
                    addon_roots.append(child.resolve())

        walked = 0
        for current, _depth in _walk_dirs(root, max_depth):
            walked += 1
            # Do not pre-collect the tree: a slow drive can spend minutes in that
            # first loop with no message. Walk and report in the same pass.
            walk_fraction = 0.62 + 0.33 * (walked / (walked + 250))
            if walked % 64 == 0:
                if progress is not None:
                    progress(
                        base + span * walk_fraction,
                        f"{current.name}: {len(mods)} found",
                    )
                mark(
                    root_key,
                    root_label,
                    walk_fraction,
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

                    def nested_step(
                        text,
                        key=root_key,
                        label=root_label,
                        value=walk_fraction,
                    ):
                        mark(key, label, value, text)

                    record = _addon_from_dir(
                        child,
                        since,
                        until,
                        toolchains=toolchains,
                        progress=nested_step,
                    )
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

        mark(
            root_key,
            root_label,
            1.0,
            f"{sum(1 for mod in mods if Path(mod.path).resolve().is_relative_to(root))} packages found",
            "DONE",
        )

    mods.sort(key=lambda mod: (mod.modified, mod.path), reverse=True)
    install_roots = tuple(str(_install_root(install).resolve()) for install in install_list)
    hash_note = ""
    if install_list:
        if progress is not None:
            progress(scan_span, f"matching {len(install_roots)} installed builds")
        mods = match_installs(
            mods,
            install_list,
            progress=(
                (
                    lambda fraction, message: progress(
                        scan_span + (1.0 - scan_span) * fraction, message
                    )
                )
                if progress is not None
                else None
            ),
            stage=stage,
        )
        matched = sum(len(mod.matches) for mod in mods)
        source_matches = sum(
            1
            for mod in mods
            for match in mod.matches
            if not _is_compiled_suffix(match.relative)
        )
        compiled_matches = matched - source_matches
        hash_note = (
            f"{matched} hash matches ({source_matches} source, {compiled_matches} compiled) "
            f"in {len(install_roots)} installs"
        )
        if matched == 0:
            hash_note = f"no hash matches in {len(install_roots)} installs"
        if progress is not None:
            progress(1.0, hash_note)
    return Inventory(
        roots=[str(root) for root in resolved_roots],
        since=since.isoformat() if since else "",
        until=until.isoformat() if until else "",
        mods=mods,
        skipped_game_paks=skipped_game_paks,
        skipped_unreadable=skipped_unreadable,
        installs=install_roots,
        hash_note=hash_note,
    )
