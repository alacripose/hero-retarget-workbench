"""Part names: keep the part word, drop the previous rig's prefix."""
from __future__ import annotations

from pathlib import Path

from forge import naming


def test_a_stale_hero_prefix_does_not_survive_an_import():
    names = naming.part_names(["shiv_body", "shiv_head", "shiv_hair"], ["shiv"])
    assert [row["object"] for row in names.values()] == ["body", "head", "hair"]


def test_a_multi_token_prefix_is_stripped_whole():
    names = naming.part_names(["thicc_mayu_v3_body"], ["thicc_mayu_v3"])
    assert names["thicc_mayu_v3_body"]["object"] == "body"


def test_a_numbered_duplicate_keeps_its_number():
    names = naming.part_names(["shiv_body.001"], ["shiv"])
    assert names["shiv_body.001"]["object"] == "body.001"


def test_a_name_that_is_only_the_prefix_is_left_alone():
    assert naming.strip_prefix("shiv", ["shiv"]) == "shiv"


def test_a_part_word_is_never_eaten_by_a_longer_prefix():
    assert naming.strip_prefix("thigh_ik", ["thighbone"]) == "thigh_ik"


def test_two_parts_never_collapse_onto_one_name():
    names = naming.part_names(["shiv_body", "body"], ["shiv"])
    assert names["shiv_body"]["object"] == "shiv_body"
    assert names["body"]["object"] == "body"


def test_no_prefixes_means_no_renaming():
    names = naming.part_names(["shiv_body"], [])
    assert names["shiv_body"]["object"] == "shiv_body"


def test_model_name_comes_from_the_file_not_the_hero():
    assert naming.model_name("Gold_Ship") == "Gold_Ship"
    assert naming.model_name("gold ship v2") == "gold_ship_v2"
    assert naming.model_name("") == "model"


def test_sanitize_keeps_blender_identifiers_safe():
    assert naming.sanitize("body:left*mesh") == "body_left_mesh"
    assert naming.sanitize("  .hidden.  ") == "hidden"
    assert naming.sanitize("x" * 80).__len__() <= 60


def test_collection_name_uses_the_import_file():
    assert naming.collection_name(Path("C:/models/Gold_Ship.glb")) == "DMF Gold_Ship"
