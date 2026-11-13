"""Ref-pose pairing and stance: the decisions the preview needs before matrices."""
from __future__ import annotations

import math

from forge import posematch


def test_pairs_come_parent_first():
    parents = {
        "pelvis": None,
        "spine_0": "pelvis",
        "arm_upper_L": "spine_0",
        "arm_lower_L": "arm_upper_L",
    }
    mapping = {"arm_lower_L": "elbow_L", "arm_upper_L": "shoulder_L", "pelvis": "root"}
    rows = posematch.pairs(mapping, parents, list(parents), ["elbow_L", "shoulder_L", "root"])
    assert [row.source for row in rows] == ["pelvis", "arm_upper_L", "arm_lower_L"]
    assert [row.depth for row in rows] == [0, 2, 3]


def test_pairs_skip_a_row_whose_target_is_missing():
    rows = posematch.pairs({"hand_L": "hand_L"}, {"hand_L": None}, ["hand_L"], ["foot_L"])
    assert rows == []
    assert posematch.unpaired({"hand_L": "hand_L"}, ["hand_L"], ["foot_L"]) == ["hand_L"]


def test_cycles_do_not_hang_the_depth_walk():
    level = posematch.depths({"a": "b", "b": "a", "c": "b"})
    assert level["a"] == 0
    assert level["c"] >= 1


def test_coverage_counts_only_real_rows():
    result = posematch.coverage({"a": "x", "b": "y"}, ["a", "b", "c", ""])
    assert result["rows"] == 3
    assert result["mapped"] == 2
    assert result["ratio"] == 2 / 3


def test_coverage_of_an_empty_rig_is_zero_not_a_division_error():
    assert posematch.coverage({}, [])["ratio"] == 0.0


def test_a_level_arm_is_a_t_pose():
    assert posematch.stance([(1.0, 0.0, 0.0), (1.0, 0.0, 0.05)])[0] == "T"


def test_a_lowered_arm_is_an_a_pose():
    kind, angle = posematch.stance([(1.0, 0.0, -0.6), (1.0, 0.0, -0.7)])
    assert kind == "A"
    assert 20 < angle < 50


def test_arms_hanging_down_are_not_a_rest_pose():
    assert posematch.stance([(0.1, 0.0, -1.0)])[0] == "down"


def test_stance_without_arms_is_unknown():
    assert posematch.stance([]) == ("unknown", 0.0)


def test_angle_is_measured_from_the_horizontal():
    assert posematch.angle_below_horizontal((1.0, 0.0, 0.0)) == 0.0
    assert math.isclose(posematch.angle_below_horizontal((0.0, 0.0, -1.0)), 90.0)
