"""User-authored rules: side stems, prefixes, regex, and the row state they set."""
from __future__ import annotations

from forge import bonerules


def test_split_side_reads_every_separator_and_case():
    assert bonerules.split_side("elbow_L") == ("elbow", "L")
    assert bonerules.split_side("elbow.l") == ("elbow", "L")
    assert bonerules.split_side("ElbowLeft") == ("Elbow", "L")
    assert bonerules.split_side("arm lower r") == ("arm lower", "R")
    assert bonerules.split_side("pelvis") == ("pelvis", "")


def test_split_side_does_not_mistake_a_word_for_a_side():
    assert bonerules.split_side("spine") == ("spine", "")
    assert bonerules.split_side("r") == ("r", "")


def test_set_side_keeps_separator_and_capitalisation():
    assert bonerules.set_side("elbow_L", "R") == "elbow_R"
    assert bonerules.set_side("elbow_l", "R") == "elbow_r"
    assert bonerules.set_side("elbow.Left", "R") == "elbow.Right"
    assert bonerules.set_side("ForearmLeft", "R") == "ForearmRight"
    assert bonerules.set_side("pelvis", "L") == "pelvis"


def test_mirror_swaps_a_side_and_leaves_a_root_alone():
    assert bonerules.mirror("elbow_L") == "elbow_R"
    assert bonerules.mirror("finger.03.R") == "finger.03.L"
    assert bonerules.mirror("pelvis") == "pelvis"


def test_one_typed_row_teaches_the_other_side():
    rules = bonerules.learn({"elbow_L": "arm_lower_L"})
    assert len(rules) == 1
    assert rules[0].source == "elbow"
    assert rules[0].target == "arm_lower_L"
    assert rules[0].kind == "side"
    found = bonerules.suggest(rules, ["elbow_R"], ["arm_lower_R"])
    assert found["elbow_R"].target == "arm_lower_R"


def test_learning_ignores_cross_side_exceptions_and_root_rows():
    assert bonerules.learn({"elbow_L": "arm_lower_R", "pelvis": "pelvis", "head": "head_0"}) == []


def test_a_rule_never_invents_a_target_the_skeleton_does_not_have():
    rules = [bonerules.Rule(source="elbow", target="arm_lower_L")]
    assert bonerules.suggest(rules, ["elbow_R"], ["hand_R"]) == {}


def test_a_side_rule_never_takes_a_target_another_row_holds():
    rules = [bonerules.Rule(source="elbow", target="arm_lower_L")]
    found = bonerules.suggest(
        rules, ["elbow_L"], ["arm_lower_L"], existing={"arm": "arm_lower_L"}
    )
    assert found == {}


def test_a_prefix_rule_may_send_a_whole_chain_to_one_bone():
    rules = [bonerules.Rule(source="skirt_*", target="pelvis")]
    found = bonerules.suggest(
        rules, ["skirt_01", "skirt_02", "skirt_03"], ["pelvis"]
    )
    assert {hit.target for hit in found.values()} == {"pelvis"}
    assert len(found) == 3


def test_an_existing_target_is_left_alone():
    rules = [bonerules.Rule(source="elbow", target="arm_lower_L")]
    found = bonerules.suggest(rules, ["elbow_R"], ["arm_lower_R"], existing={"elbow_R": "hand_R"})
    assert found == {}


def test_a_prefix_rule_answers_every_name_starting_with_it():
    rules = [bonerules.Rule(source="Sp_Hi_Mskirt*", target="pelvis")]
    found = bonerules.suggest(
        rules,
        ["Sp_Hi_Mskirt0_B_00", "Sp_Hi_Mskirt0_B_01", "Hip"],
        ["pelvis"],
    )
    assert set(found) == {"Sp_Hi_Mskirt0_B_00", "Sp_Hi_Mskirt0_B_01"}
    assert found["Sp_Hi_Mskirt0_B_01"].target == "pelvis"
    assert all(hit.rule.kind == "prefix" for hit in found.values())


def test_a_prefix_rule_can_mark_a_row_extra_instead_of_mapping_it():
    rules = [bonerules.Rule(source="Sp_Hi_Mskirt*", target="", state="EXTRA")]
    found = bonerules.suggest(rules, ["Sp_Hi_Mskirt0_B_01"], ["pelvis"])
    assert found["Sp_Hi_Mskirt0_B_01"].state == "EXTRA"
    assert found["Sp_Hi_Mskirt0_B_01"].target == "Sp_Hi_Mskirt0_B_01"


def test_a_prefix_rule_can_ignore_a_row():
    rules = [bonerules.Rule(source="ik_*", target="", state="IGNORED")]
    found = bonerules.suggest(rules, ["ik_hand_L"], ["hand_L"])
    assert found["ik_hand_L"].state == "IGNORED"


def test_extra_and_ignored_rules_do_not_consume_a_hero_bone():
    rules = [
        bonerules.Rule(source="Sp_Hi_Mskirt*", target="", state="IGNORED"),
        bonerules.Rule(source="Hip", target="pelvis", side_aware=False),
    ]
    found = bonerules.suggest(rules, ["Sp_Hi_Mskirt0_B_00", "Hip"], ["pelvis"])
    assert found["Sp_Hi_Mskirt0_B_00"].state == "IGNORED"
    assert found["Hip"].target == "pelvis"


def test_a_regex_rule_suggests_from_a_capture_group():
    rule = bonerules.Rule(source=r"Elbow_(\d+)_L", target=r"arm_lower_\1_L", regex=True)
    found = bonerules.suggest([rule], ["Elbow_02_L"], ["arm_lower_02_L"])
    assert found["Elbow_02_L"].target == "arm_lower_02_L"
    assert found["Elbow_02_L"].rule.kind == "regex"


def test_a_broken_regex_is_ignored_instead_of_raising():
    rule = bonerules.Rule(source="[unclosed", target="x", regex=True)
    assert bonerules.suggest([rule], ["elbow_L"], ["elbow_L"]) == {}


def test_a_disabled_rule_is_skipped():
    rule = bonerules.Rule(source="elbow", target="arm_lower_L", enabled=False)
    assert bonerules.suggest([rule], ["elbow_L"], ["arm_lower_L"]) == {}


def test_duplicate_rows_strengthen_one_rule():
    rules = bonerules.learn({"elbow_L": "arm_lower_L", "elbow_R": "arm_lower_R"})
    assert len(rules) == 1
    assert rules[0].support == 2


def test_regex_rules_are_tried_before_prefixes_and_stems():
    rules = bonerules.ordered(
        [
            bonerules.Rule(source="Sp_", target="x", side_aware=False),
            bonerules.Rule(source="Sp_.*", target="y", regex=True),
            bonerules.Rule(source="Sp_Hi_Mskirt*", target="z"),
        ]
    )
    assert [rule.kind for rule in rules] == ["regex", "prefix", "side"]


def test_labels_and_descriptions_name_the_rule_form():
    side = bonerules.learn({"elbow_L": "arm_lower_L"})[0]
    assert bonerules.label(side) == "elbow_{L,R} → arm_lower_{L,R}"
    assert "side token" in bonerules.describe(side)
    assert "starting with" in bonerules.describe(bonerules.Rule(source="a*", target="b"))
    assert "\\1" in bonerules.describe(bonerules.Rule(source="a", target="b", regex=True))
