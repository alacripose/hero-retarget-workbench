"""Search, invert and sort for a panel list, as plain data.

Blender's list header shows a magnifier, a reverse toggle and an A-Z button when
a ``UIList`` implements ``filter_items``. Those controls only work if that method
reads ``filter_name`` / ``use_filter_sort_alpha`` and returns the flags and the
order — a list that returns its own fixed selection makes the controls look
functional while they change nothing.

This module is the pure half: given the text each row shows, the query and the
sort flags, it says which rows survive and in what order. The ``UIList`` classes
only translate that into ``bitflag_filter_item``.
"""
from __future__ import annotations

from collections.abc import Iterable


def matches(text: str, query: str) -> bool:
    """Every whitespace-separated term of the query appears in the row's text."""
    terms = (query or "").lower().split()
    haystack = (text or "").lower()
    return all(term in haystack for term in terms)


def rows(
    texts: Iterable[str],
    query: str = "",
    *,
    sort_alpha: bool = False,
    reverse: bool = False,
    invert: bool = False,
    restrict: Iterable[bool] | None = None,
) -> tuple[list[int], list[int]]:
    """``(flags, order)`` for a list whose rows show ``texts``.

    ``flags`` is one 0/1 per row in the collection's own order; ``order`` is the
    row indices in display order, or empty when the list is not sorted. ``restrict``
    is another filter the caller already decided (the bone map's state selector):
    the search narrows it, it never widens it.
    """
    texts = list(texts)
    flags = [1 if matches(text, query) else 0 for text in texts]
    if invert:
        flags = [0 if flag else 1 for flag in flags]
    if restrict is not None:
        limit = list(restrict)
        flags = [flag if (index < len(limit) and limit[index]) else 0 for index, flag in enumerate(flags)]
    order: list[int] = []
    if sort_alpha:
        # Stable on the visible text: rows with the same text keep their order.
        order = sorted(range(len(texts)), key=lambda index: (texts[index].lower(), index), reverse=reverse)
    return flags, order
