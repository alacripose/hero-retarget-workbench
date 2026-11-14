"""Stage live-game model components beside a mod, without touching the mod.

Deadlock is growing cosmetic component slots (weapons, headwear, attachments),
and an S2V extraction already carries those meshes as separate DMX files. This
module finds them, copies the selected ones into an addon content tree at their
original relative paths, and writes a manifest naming every source and its
destination.

Detection reads the model's own ``RenderMeshFile`` list.  A hero happens to name
its parts ``gun`` and ``hat``; an NPC or prop can call the same parts
``unnamed_1`` or ``ratking_minion``.  The vmdl render list is the authority for
both.  Filename words are only a fallback for a model with no readable vmdl.

Nothing here parses compiled assets or rewrites a model's render list except
through the existing component merge in ``forge.migrate``.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

COMPONENT_WORDS = ("gun", "weapon", "hat", "head", "hair", "attachment", "cosmetic", "prop")
_LOD = re.compile(r"(?:^|[_.\-])lod[_.\-]?\d+(?:$|[_.\-])", re.IGNORECASE)
_BODY_NAMES = {"body", "model", "hull", "base"}


class ComponentError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentFile:
    name: str
    path: Path
    relative: str
    kind: str
    bytes: int
    primary: bool = False


def _is_lod(*names: str) -> bool:
    return any(_LOD.search(name or "") for name in names)


def _primary_mesh(entries: list[tuple[str, str, Path]]) -> int:
    """Index of the model's body, so it is not offered as a component.

    Render meshes are in vmdl order, body first.  A declared body name wins;
    otherwise the first non-LOD mesh is the primary.  This covers hero bodies
    (``body``) and non-hero models whose only mesh is ``unnamed_1`` or
    ``ratking_minion``.
    """
    for index, (mesh, relative, path) in enumerate(entries):
        names = (mesh.lower(), Path(relative).stem.lower(), path.stem.lower())
        if any(name in _BODY_NAMES for name in names):
            return index
        if any(re.search(r"(?:^|[_.\-])(?:body|model|hull)(?:$|[_.\-])", name) for name in names):
            return index
    return 0


def _render_meshes(root: Path, vmdl: Path | None) -> list[tuple[str, str, Path]]:
    """Non-LOD render meshes that exist in this extraction, in vmdl order."""
    if vmdl is None:
        candidates = sorted(root.rglob("*.vmdl"))
        vmdl = candidates[0] if candidates else None
    if vmdl is None or not vmdl.is_file():
        return []
    try:
        from . import modeldoc

        text = vmdl.read_text(encoding="utf-8", errors="replace")
        rows = modeldoc.render_mesh_files(text)
    except Exception:
        return []
    found: list[tuple[str, str, Path]] = []
    for row in rows:
        relative = (row.filename or "").replace("\\", "/").lstrip("/")
        if not relative:
            continue
        path = root / relative
        if not path.is_file():
            continue
        if _is_lod(row.name, relative):
            continue
        found.append((row.name, relative, path))
    return found


def _entry(root: Path, path: Path, *, primary: bool = False) -> ComponentFile:
    return ComponentFile(
        name=path.name,
        path=path,
        relative=path.relative_to(root).as_posix(),
        kind=path.suffix.lower().lstrip("."),
        bytes=path.stat().st_size,
        primary=primary,
    )


def _inventory_from_render_list(root: Path, vmdl: Path | None) -> list[ComponentFile]:
    entries = _render_meshes(root, vmdl)
    if not entries:
        return []
    primary = _primary_mesh(entries)
    return [
        _entry(root, path, primary=index == primary)
        for index, (_mesh, _relative, path) in enumerate(entries)
    ]


def _inventory_from_names(root: Path, *, include_materials: bool) -> list[ComponentFile]:
    """Fallback for a model with no readable vmdl: keep the old word scan."""
    found: list[ComponentFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in (".dmx", ".vmdl", ".vmat", ".png", ".tga", ".exr", ".vtex"):
            continue
        name = path.stem.lower()
        if not any(word in name for word in COMPONENT_WORDS):
            continue
        if suffix in (".vmat", ".png", ".tga", ".exr", ".vtex") and not include_materials:
            continue
        if suffix == ".dmx" and _is_lod(name):
            continue
        found.append(_entry(root, path, primary=suffix in (".vmdl", ".vmat", ".png", ".tga", ".exr", ".vtex")))
    return found


def inventory(
    extraction_root: Path,
    *,
    include_materials: bool = True,
    vmdl: Path | None = None,
) -> list[ComponentFile]:
    """Component meshes for the current model, hero or not.

    ``vmdl`` names the model whose render list is read.  When it is omitted the
    first vmdl under the extraction is used, which keeps the pure API simple.
    A readable render list wins; otherwise the filename word scan is retained.
    """
    root = Path(extraction_root).expanduser()
    if not root.is_dir():
        raise ComponentError(f"extraction-missing: {root}")
    rows = _inventory_from_render_list(root, Path(vmdl).expanduser() if vmdl else None)
    if rows:
        if include_materials:
            stems = {Path(row.relative).stem.lower() for row in rows}
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in (
                    ".vmat",
                    ".png",
                    ".tga",
                    ".exr",
                    ".vtex",
                ):
                    continue
                name = path.stem.lower()
                if any(stem and (stem in name or name in stem) for stem in stems):
                    rows.append(_entry(root, path, primary=True))
        return rows
    return _inventory_from_names(root, include_materials=include_materials)


def stage(
    files,
    destination: Path,
    *,
    addon: str,
    hero: str = "",
    extraction_root: Path | None = None,
    vmdl: Path | None = None,
    bodygroup: str = "",
) -> Path:
    """Copy component files and, when a vmdl is given, register their meshes.

    Every staged DMX becomes a ``RenderMeshFile`` and a choice in ``bodygroup``
    on the staged vmdl, so a hat or a gun is a switchable body-group choice
    rather than a mesh that is always drawn.  A primary/body row is copied but
    never registered as a component choice.
    """
    destination = Path(destination).expanduser()
    if not files:
        raise ComponentError("no-components-selected")
    addon = (addon or "").strip().strip("/\\")
    if not addon or "/" in addon or "\\" in addon:
        raise ComponentError("addon-name-required")
    root = destination / "content" / "citadel_addons" / addon
    records = []
    merged: list[dict] = []
    for component in files:
        target = root / component.relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(component.path, target)
        records.append(
            {
                "source": str(component.path),
                "relative": component.relative,
                "kind": component.kind,
                "bytes": component.bytes,
                "primary": bool(getattr(component, "primary", False)),
            }
        )
        if (
            vmdl is not None
            and component.kind == "dmx"
            and bodygroup
            and not getattr(component, "primary", False)
        ):
            from . import migrate

            stem = Path(component.relative).stem
            merged.append(
                migrate.add_component_mesh(
                    Path(vmdl),
                    mesh_name=stem,
                    dmx_relative=component.relative,
                    bodygroup=bodygroup,
                )
            )
    manifest = root / "components.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "staged": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "addon": addon,
                "hero": hero,
                "extraction": str(extraction_root) if extraction_root else "",
                "files": records,
                "vmdl": str(vmdl) if vmdl else "",
                "bodygroup": bodygroup,
                "merged": merged,
                "vmdl_merge": "written" if merged else "not-written",
                "note": (
                    "Files are staged at their original relative paths. Each staged component DMX was "
                    "added to the vmdl as a RenderMeshFile and a BodyGroupChoice."
                    if merged
                    else "Files are staged at their original relative paths. The mod's vmdl "
                    "render list was not rewritten because no vmdl or body group was given."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest
