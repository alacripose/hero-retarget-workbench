import unittest

from forge.weights import (
    BoneSegment,
    WeightError,
    envelope_weights,
    fold_source,
    merge_weights,
    normalize_weights,
    segment_distance,
)


class WeightTests(unittest.TestCase):
    def test_segment_distance_clamps_to_the_segment(self):
        self.assertAlmostEqual(segment_distance((0, 0, 0), (0, 0, 0), (0, 0, 10)), 0.0)
        self.assertAlmostEqual(segment_distance((1, 0, 5), (0, 0, 0), (0, 0, 10)), 1.0)
        self.assertAlmostEqual(segment_distance((0, 0, 12), (0, 0, 0), (0, 0, 10)), 2.0)

    def test_normalize_keeps_the_strongest_influences(self):
        weights = normalize_weights({"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}, max_influences=3)
        self.assertEqual(list(weights), ["e", "d", "c"])
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_normalize_drops_negative_and_non_finite(self):
        weights = normalize_weights({"a": 1, "b": -1, "c": float("nan"), "d": 0})
        self.assertEqual(weights, {"a": 1.0})

    def test_normalize_refuses_zero_limit(self):
        with self.assertRaises(WeightError):
            normalize_weights({"a": 1}, max_influences=0)

    def test_envelope_prefers_the_near_bone(self):
        bones = [
            BoneSegment("spine", (0, 0, 0), (0, 0, 1)),
            BoneSegment("hand_l", (2, 0, 0), (2, 0, 0.2)),
        ]
        weights = envelope_weights((0.05, 0, 0.4), bones, max_distance=1.0)
        self.assertEqual(list(weights), ["spine"])
        self.assertAlmostEqual(weights["spine"], 1.0)

    def test_envelope_assigns_a_far_vertex_to_its_nearest_declared_bone(self):
        bones = [
            BoneSegment("spine", (0, 0, 0), (0, 0, 1)),
            BoneSegment("tail", (5, 0, 0), (6, 0, 0)),
        ]
        weights = envelope_weights((5.4, 0, 0), bones, max_distance=0.1)
        self.assertIn("tail", weights)
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_merge_adds_shared_bones(self):
        merged = merge_weights({"a": 0.5, "b": 0.5}, {"a": 0.25, "c": 0.25})
        self.assertEqual(merged, {"a": 0.75, "b": 0.5, "c": 0.25})

    def test_fold_walks_to_the_nearest_mapped_parent(self):
        mapping = {"pelvis": "pelvis", "spine_01": "spine_01"}
        parents = {"tail_01": "tail_root", "tail_root": "spine_01"}
        self.assertEqual(
            fold_source("tail_01", mapping, parents, extra_policy="FOLD"),
            "spine_01",
        )

    def test_keep_and_drop_are_explicit(self):
        mapping = {"pelvis": "pelvis"}
        parents = {"tail": "pelvis"}
        self.assertEqual(fold_source("tail", mapping, parents, extra_policy="KEEP"), "tail")
        self.assertIsNone(fold_source("tail", mapping, parents, extra_policy="DROP"))

    def test_fold_uses_the_declared_fallback(self):
        self.assertEqual(
            fold_source("tail", {}, {}, extra_policy="FOLD", fallback="pelvis"),
            "pelvis",
        )


if __name__ == "__main__":
    unittest.main()
