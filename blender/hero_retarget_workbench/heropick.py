"""The hero picker: one filtered list instead of a dropdown of every live model.

The Source page used to bind `hero_slug` straight to a search enum. That made a
several-hundred-row dropdown (every hideout NPC included) and gave no way to look
at one kind of model at a time. This module owns the visible rows: it reads the
roster `properties.set_hero_items` recorded, classifies each entry, applies the
search text and the kind filter, and keeps the list pointed at the chosen hero.

Rows are data, not a second roster: `properties.HERO_ITEMS` stays authoritative,
and `refresh` is the only writer.
"""
from __future__ import annotations

from . import properties

# Bumped by `properties.set_hero_items`; a stale list is refreshed without the
# panel draw having to know that detection ran.
_SEEN = ""


def kind_of(title: str, model: str) -> str:
    """HERO, HIDEOUT or OTHER from the roster's own title and model path."""
    text = (title or "").strip().lower()
    path = (model or "").replace("\\", "/").lower()
    if text.startswith("hideout"):
        return "HIDEOUT"
    if "heroes_staging" in path or "/heroes/" in path:
        return "HERO"
    return "OTHER"


def title_for(slug: str) -> str:
    for value, title, _model in properties.HERO_ITEMS:
        if value == slug:
            return title
    return ""


def refresh(settings) -> int:
    """Rebuild the visible rows from the roster, the query and the kind filter.

    The selected hero keeps its row when the filters still show it; otherwise the
    list points at the first row so a click always has a target.
    """
    global _SEEN
    query = " ".join((getattr(settings, "hero_query", "") or "").lower().split())
    kind = getattr(settings, "hero_kind", "ALL") or "ALL"
    chosen = getattr(settings, "hero_slug", "NONE")
    rows = settings.hero_rows
    rows.clear()
    index = 0
    for slug, title, model in properties.HERO_ITEMS:
        if slug == "NONE":
            continue
        row_kind = kind_of(title, model)
        if kind != "ALL" and row_kind != kind:
            continue
        haystack = f"{title} {model}".lower()
        if query and query not in haystack:
            continue
        row = rows.add()
        row.slug = slug
        row.title = title
        row.kind = row_kind
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
            getattr(settings, "hero_kind", "ALL") or "ALL",
        )
    )


def ensure(settings) -> int:
    """Refresh only when the roster or a filter changed, so a draw stays cheap."""
    if signature(settings) == _SEEN and len(settings.hero_rows):
        return len(settings.hero_rows)
    return refresh(settings)


def choose(settings, index: int) -> str:
    """Point `hero_slug` at one visible row and return the chosen title."""
    rows = settings.hero_rows
    if not rows:
        raise RuntimeError("hero-pick-empty: detect the live build first")
    index = max(0, min(int(index), len(rows) - 1))
    row = rows[index]
    settings.hero_slug = row.slug
    settings.hero_index = index
    return row.title
