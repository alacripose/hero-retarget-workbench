"""The list search and sort behind the panel's native list header."""
from __future__ import annotations

from forge import uilist


def test_an_empty_query_keeps_every_row():
    flags, order = uilist.rows(["pelvis", "spine_0", "hand_L"])
    assert flags == [1, 1, 1]
    assert order == []


def test_a_query_narrows_to_the_rows_that_show_it():
    flags, _ = uilist.rows(["pelvis", "Sp_Hi_Mskirt0_B_00", "hand_L"], "skirt")
    assert flags == [0, 1, 0]


def test_every_word_of_a_query_has_to_appear():
    texts = ["Sp_Hi_Mskirt0_B_00", "Sp_Hi_Mskirt0_BL_01", "hand_L"]
    flags, _ = uilist.rows(texts, "sp hi bl")
    assert flags == [0, 1, 0]


def test_the_query_is_case_insensitive():
    flags, _ = uilist.rows(["Arm_Lower_L"], "arm_lower")
    assert flags == [1]


def test_sorting_orders_by_the_visible_text_and_reverses():
    texts = ["spine_0", "Arm_Lower_L", "pelvis"]
    _, order = uilist.rows(texts, sort_alpha=True)
    assert order == [1, 2, 0]
    _, reverse = uilist.rows(texts, sort_alpha=True, reverse=True)
    assert reverse == [0, 2, 1]


def test_invert_flips_the_search_without_hiding_an_unsearched_list():
    assert uilist.rows(["pelvis", "hand_L"], "hand")[0] == [0, 1]
    assert uilist.rows(["pelvis", "hand_L"], "hand", invert=True)[0] == [1, 0]
    assert uilist.rows(["pelvis", "hand_L"], invert=True)[0] == [0, 0]


def test_a_restriction_narrows_the_search_and_is_never_widened_by_it():
    texts = ["pelvis", "spine_0", "hand_L"]
    restrict = [True, False, False]
    flags, _ = uilist.rows(texts, "pelvis", restrict=restrict)
    assert flags == [1, 0, 0]
    flags, _ = uilist.rows(texts, "hand", restrict=restrict)
    assert flags == [0, 0, 0]
