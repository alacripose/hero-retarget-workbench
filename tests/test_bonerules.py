"""Rules learned from one mapping row, and the built-in joint words."""
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


def test_one_row_teaches_the_other_side():
    rules = bonerules.learn({"elbow_L": "arm_lower_L"})
    assert len(rules) == 1
    assert rules[0].source == "elbow"
    assert rules[0].target == "arm_lower_L"
    assert rules[0].side_aware
    found = bonerules.suggest(rules, ["elbow_R"], ["arm_lower_R"])
    assert found["elbow_R"].target == "arm_lower_R"


def test_learning_ignores_cross_side_exceptions_and_root_rows():
    rules = bonerules.learn({"elbow_L": "arm_lower_R", "pelvis": "pelvis", "head": "head_0"})
    assert rules == []


def test_rule_matches_the_same_stem_on_both_sides_and_nothing_else():
    rules = bonerules.learn({"elbow_L": "arm_lower_L"})
    found = bonerules.suggest(rules, ["elbow_R", "elbow_L", "forearm_R"], ["arm_lower_R", "arm_lower_L"])
    assert found["elbow_R"].target == "arm_lower_R"
    # arm_lower_L is already claimed by the seeded row in a real map; here it is
    # simply the only L target and must not be handed to elbow_L twice.
    assert "forearm_R" not in found


def test_a_target_must_exist_in_the_hero_skeleton():
    rules = bonerules.learn({"elbow_L": "arm_lower_L"})
    assert bonerules.suggest(rules, ["elbow_R"], ["hand_R"]) == {}


def test_one_target_is_never_offered_twice():
    rules = bonerules.learn({"elbow_L": "arm_lower_L"})
    found = bonerules.suggest(rules, ["elbow_R", "forearm_R"], ["arm_lower_R"])
    assert len(found) == 1


def test_existing_targets_are_left_alone():
    rules = bonerules.learn({"elbow_L": "arm_lower_L"})
    found = bonerules.suggest(
        rules, ["elbow_R"], ["arm_lower_R"], existing={"elbow_R": "hand_R"}
    )
    assert found == {}


def test_a_regex_rule_suggests_from_a_capture_group():
    rule = bonerules.Rule(source=r"Elbow_(\d+)_L", target=r"arm_lower_\1_L", regex=True)
    found = bonerules.suggest([rule], ["Elbow_02_L"], ["arm_lower_02_L"])
    assert found["Elbow_02_L"].target == "arm_lower_02_L"


def test_a_broken_regex_is_ignored_instead_of_raising():
    rule = bonerules.Rule(source="[unclosed", target="x", regex=True)
    assert bonerules.suggest([rule], ["elbow_L"], ["elbow_L"]) == {}


def test_duplicate_rows_strengthen_one_rule():
    rules = bonerules.learn(
        {"elbow_L": "arm_lower_L", "elbow_R": "arm_lower_R", "knee_L": "leg_lower_L"}
    )
    by_source = {rule.source: rule for rule in rules}
    assert set(by_source) == {"elbow", "knee"}
    assert by_source["elbow"].support == 2
    assert by_source["knee"].support == 1


def test_builtin_only_names_stems_the_hero_actually_has():
    targets = ["pelvis", "arm_lower_L", "arm_lower_R", "hand_L"]
    rules = bonerules.builtin(targets)
    sources = {rule.source for rule in rules}
    assert "elbow" in sources and "forearm" in sources and "wrist" in sources
    # No leg bones in this skeleton, so no leg rule is invented.
    assert not sources & {"knee", "thigh", "shin", "foot"}

    found = bonerules.suggest(rules, ["elbow_R", "forearm_L"], targets)
    assert found["elbow_R"].target == "arm_lower_R"
    assert found["forearm_L"].target == "arm_lower_L"


def test_builtin_understands_the_other_spelling_of_the_same_word():
    rules = bonerules.builtin(["upperleg_L", "upperleg_R"])
    found = bonerules.suggest(rules, ["thigh_R"], ["upperleg_L", "upperleg_R"])
    assert found["thigh_R"].target == "upperleg_R"


def test_labels_stay_short_enough_for_a_panel_row():
    assert bonerules.label(bonerules.learn({"elbow_L": "arm_lower_L"})[0]) == (
        "elbow_{L,R} → arm_lower_{L,R}"
    )
    assert bonerules.label(bonerules.Rule(source="^x$", target="y", regex=True)) == "^x$ → y"
