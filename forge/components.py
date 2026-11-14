"""Stage live-game hero components beside a mod, without touching the mod.

Deadlock is growing cosmetic component slots (weapons, headwear, attachments),
and the live extraction already carries those meshes as separate DMX files. This
module finds them and copies the selected ones into an addon content tree at
their original relative paths. It writes a manifest naming every source and its
destination, and it says plainly that the mod's vmdl render list is not
rewritten: staging files is the non-destructive half, and the vmdl merge is a
separate, riskier operation.

Nothing here parses a vmdl or a compiled asset. Files are copied byte-for-byte.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

COMPONENT_WORDS = ("gun", "weapon", "hat", "head", "hair", "attachment", "cosmetic", "prop")


class ComponentError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentFile:
    name: str
    path: Path
    relative: str
    kind: str
    bytes: int


def inventory(extraction_root: Path, *, include_materials: bool = True) -> list[ComponentFile]:
    """Component-shaped assets in a hero extraction, keyed by relative path."""
    root = Path(extraction_root).expanduser()
    if not root.is_dir():
        raise ComponentError(f"extraction-missing: {root}")
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
        found.append(
            ComponentFile(
                name=path.name,
                path=path,
                relative=path.relative_to(root).as_posix(),
                kind=suffix.lstrip("."),
                bytes=path.stat().st_size,
            )
        )
    return found


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
    rather than a mesh that is always drawn.
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
            }
        )
        if vmdl is not None and component.kind == "dmx" and bodygroup:
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
                    "Files are staged at their original relative paths. Each staged DMX was "
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
