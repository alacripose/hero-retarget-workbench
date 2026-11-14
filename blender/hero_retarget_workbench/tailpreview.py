"""Preview images for the tail tile selector."""
from __future__ import annotations

from pathlib import Path

import bpy
from bpy.utils import previews

_COLLECTION = None


def register() -> None:
    global _COLLECTION
    if _COLLECTION is None:
        _COLLECTION = previews.new()


def unregister() -> None:
    global _COLLECTION
    if _COLLECTION is not None:
        previews.remove(_COLLECTION)
        _COLLECTION = None


def icon(path: str) -> int:
    """The icon id for one generated tail thumbnail, or 0 when it is unreadable."""
    if not path or _COLLECTION is None:
        return 0
    file = Path(bpy.path.abspath(path))
    if not file.is_file():
        return 0
    key = str(file.resolve())
    if key not in _COLLECTION:
        try:
            _COLLECTION.load(key, key, "IMAGE")
        except Exception:
            return 0
    image = _COLLECTION.get(key)
    return image.icon_id if image is not None else 0
