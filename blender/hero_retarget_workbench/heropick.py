"""The model picker: one filtered list over every model the live pak carries.

The Source page used to bind `hero_slug` to a search enum built from the hero
table. That made a several-hundred-row dropdown, hid every model outside the
hero roots, and offered categories that were invented in code. This module owns
the visible rows: it reads the full roster the pak listing recorded, filters by
the chosen VPK folder and the search text, and keeps the list on the chosen
model.

Rows are data, not a second roster: `properties.MODEL_ITEMS` stays authoritative,
and `refresh` is the only writer.
"""
from __future__ import annotations

from . import properties

# Bumped by `properties.set_model_items`; a stale list refreshes without the panel
# draw having to know that detection ran.
_SEEN = ""


def kind_of(title: str, model: str) -> str:
    """HERO, HIDEOUT or OTHER from a title and model path. Kept for old callers."""
    text = (title or "").strip().lower()
    path = (model or "").replace("\\", "/").lower()
    if text.startswith("hideout"):
        return "HIDEOUT"
    if "heroes_staging" in path or "/heroes/" in path:
        return "HERO"
    return "OTHER"


def _root(path: str) -> str:
    parts = [part for part in str(path or "").replace("\\", "/").strip("/").split("/") if part]
    return "/".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")


def root_items() -> list[tuple[str, str, str]]:
    return properties.MODEL_ROOT_ITEMS


def title_for(slug: str) -> str:
    for value, title, _model, _root in properties.MODEL_ITEMS:
        if value == slug:
            return title
    for value, title, _model in properties.HERO_ITEMS:
        if value == slug:
            return title
    return ""


def refresh(settings) -> int:
    properties.sync_folders(settings)
    """Rebuild the visible rows from the roster, the query and the folder filter.

    The chosen model keeps its row when the filters still show it; otherwise the
    list points at the first row so a click always has a target.
    """
    global _SEEN
    query = " ".join((getattr(settings, "hero_query", "") or "").lower().split())
    root = getattr(settings, "model_root", "ALL") or "ALL"
    chosen = getattr(settings, "hero_slug", "NONE")
    rows = settings.hero_rows
    rows.clear()
    index = 0
    items = properties.MODEL_ITEMS
    if not items:
        items = [(slug, title, model, _root(model)) for slug, title, model in properties.HERO_ITEMS if slug != "NONE"]
    for slug, title, model, folder in items:
        if root != "ALL" and folder != root:
            continue
        haystack = f"{title} {model}".lower()
        if query and query not in haystack:
            continue
        row = rows.add()
        row.slug = slug
        row.title = title
        row.kind = folder
        row.model = model
        if slug == chosen:
            index = len(rows) - 1
    settings.hero_index = index if rows else 0
    _SEEN = signature(settings)
    return len(rows)


def signature(settings) -> str:
    return "|".join(
        (
            str(properties.ROSTER_SERIAL),
            " ".join((getattr(settings, "hero_query", "") or "").lower().split()),
            getattr(settings, "model_root", "ALL") or "ALL",
        )
    )


def ensure(settings) -> int:
    """Refresh only when the roster or a filter changed, so a draw stays cheap."""
    if signature(settings) == _SEEN and len(settings.hero_rows):
        return len(settings.hero_rows)
    return refresh(settings)


def port_target(slug: str, model: str = "") -> str:
    """Map a picked model onto a valid `mod_target` enum value, or NONE.

    The picker's rows are every model in the pak, so `hero_slug` is usually a
    model path, never one of the roster enum's values.  A port target only
    exists when the picked path belongs to a live hero; assigning the path
    itself is what raised Blender's enum TypeError on Warden.
    """
    value = str(slug or "").replace("\\", "/").strip().casefold()
    model_path = str(model or "").replace("\\", "/").strip().casefold()
    items = [(str(row[0]), str(row[2]).replace("\\", "/").strip().casefold()) for row in properties.HERO_ITEMS]
    for item_slug, _item_model in items:
        if value == item_slug.casefold() and value != "none":
            return item_slug
    for item_slug, item_model in items:
        if item_slug.casefold() == "none":
            continue
        if model_path and model_path == item_model:
            return item_slug
    # A roster row can be stored as its model path, and a variant folder can
    # share the hero's stem (nano_v2/nano.vmdl).  Compare path stems and the
    # hero folder before giving up on the port target.
    model_stem = model_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    model_parent = model_path.rsplit("/", 1)[-2] if "/" in model_path else ""
    for item_slug, item_model in items:
        if item_slug.casefold() == "none":
            continue
        item_stem = item_model.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        item_parent = item_model.rsplit("/", 1)[-2] if "/" in item_model else ""
        if model_stem and model_stem == item_stem:
            return item_slug
        if model_parent and model_parent == item_parent:
            return item_slug
    return "NONE"


def choose(settings, index: int) -> str:
    """Point `hero_slug` at one visible row and return the chosen title."""
    rows = settings.hero_rows
    if not rows:
        raise RuntimeError("model-pick-empty: detect the live build first")
    index = max(0, min(int(index), len(rows) - 1))
    row = rows[index]
    settings.hero_slug = row.slug
    settings.hero_model_path = row.model
    settings.hero_index = index
    return row.title
