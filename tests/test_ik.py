import unittest

from forge import ik


class SuggestTests(unittest.TestCase):
    def setUp(self):
        self.names = [
            "root",
            "pelvis",
            "hand_L",
            "hand_R",
            "lower_arm_L",
            "lower_arm_R",
            "ankle_L",
            "ankle_R",
            "thigh_L",
            "tail_01",
            "Ik_Hand_L",
            "Ik_Elbow_R",
            "Ik_Foot_L",
            "Ik_Weapon",
        ]

    def test_leading_ik_token_is_a_target(self):
        self.assertTrue(ik.is_target("Ik_Hand_L"))
        self.assertTrue(ik.is_target("IK_Foot_R"))
        self.assertTrue(ik.is_target("iktarget_hand_l"))
        self.assertFalse(ik.is_target("thighbone_ik"))
        self.assertFalse(ik.is_target("hand_L"))

    def test_hand_target_follows_the_same_side_hand(self):
        result = ik.suggest("Ik_Hand_L", self.names)
        self.assertEqual(result.target, "hand_L")
        self.assertEqual(result.confidence, "exact")
        self.assertTrue(result.ready)

    def test_elbow_target_follows_the_lower_arm(self):
        result = ik.suggest("Ik_Elbow_R", self.names)
        self.assertEqual(result.target, "lower_arm_R")
        self.assertEqual(result.confidence, "related")

    def test_foot_target_follows_the_same_side_ankle(self):
        result = ik.suggest("Ik_Foot_L", self.names)
        self.assertEqual(result.target, "ankle_L")

    def test_a_weapon_target_is_not_given_a_bone(self):
        result = ik.suggest("Ik_Weapon", self.names)
        self.assertEqual(result.target, "")

    def test_scan_lists_targets_in_name_order(self):
        rows = ik.scan(self.names)
        self.assertEqual(
            [row.bone for row in rows],
            ["Ik_Elbow_R", "Ik_Foot_L", "Ik_Hand_L", "Ik_Weapon"],
        )
        self.assertEqual([row.target for row in rows], ["lower_arm_R", "ankle_L", "hand_L", ""])

    def test_a_side_never_crosses(self):
        names = ["hand_R", "Ik_Hand_L"]
        self.assertEqual(ik.suggest("Ik_Hand_L", names).target, "")


if __name__ == "__main__":
    unittest.main()
