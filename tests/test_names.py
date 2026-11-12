import unittest

from forge.names import match, normalize


class NameTests(unittest.TestCase):
    def test_exact_wins(self):
        result = match(["pelvis", "spine_01"], ["pelvis", "spine_01"])
        self.assertEqual(result.mapping, {"pelvis": "pelvis", "spine_01": "spine_01"})
        self.assertEqual(result.unmatched, [])

    def test_normalized_matches_one_candidate(self):
        result = match(["ValveBiped.Bip01_L_UpperArm"], ["Bip01_L_UpperArm"])
        self.assertEqual(result.mapping["ValveBiped.Bip01_L_UpperArm"], "Bip01_L_UpperArm")

    def test_alias_matches_only_target(self):
        result = match(["hand_L"], ["hand_left"], aliases={"hand_l": "hand_left"})
        self.assertEqual(result.mapping, {"hand_L": "hand_left"})
        self.assertEqual(result.aliases["hand_L"], "hand_left")

    def test_unmatched_is_reported_not_guessed(self):
        result = match(["unknown"], ["pelvis", "spine"])
        self.assertEqual(result.unmatched, ["unknown"])
        self.assertEqual(result.mapping, {})

    def test_collision_is_reported(self):
        result = match(["a", "b"], ["a"], aliases={"b": "a"})
        self.assertEqual(result.collisions, [("a", ["a", "b"])])

    def test_normalize_keeps_numbers(self):
        self.assertEqual(normalize("ValveBiped.Bip01_L_Hand_02"), "lhand02")


if __name__ == "__main__":
    unittest.main()
