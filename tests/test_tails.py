"""Tail channel matching: exact and numbered, never a guessed neighbour."""
from __future__ import annotations

from forge import tails


def test_exact_tail_names_pair():
    rows = tails.candidates(["tail_01", "tail_02", "pelvis"], ["tail_01", "tail_02"])
    assert [(row.source, row.target, row.state) for row in rows] == [
        ("tail_01", "tail_01", "MATCHED"),
        ("tail_02", "tail_02", "MATCHED"),
    ]


def test_normalized_and_numbered_names_pair_without_inventing():
    rows = tails.candidates(["Tail_01", "Tail_02", "tail_03"], ["tail01", "tail_02"])
    assert [(row.source, row.target, row.state) for row in rows] == [
        ("Tail_01", "tail01", "MATCHED"),
        ("Tail_02", "tail_02", "MATCHED"),
        ("tail_03", "", "CHOOSE"),
    ]


def test_only_tail_channels_are_listed():
    rows = tails.candidates(["pelvis", "spine_01", "hair_01", "ponytail"], ["ponytail"])
    assert [row.source for row in rows] == ["hair_01", "ponytail"]


def test_mapping_ignores_unanswered_rows():
    rows = tails.candidates(["tail_01", "tail_02"], ["tail_01"])
    assert tails.mapping(rows) == {"tail_01": "tail_01"}