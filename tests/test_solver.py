"""The solver-input rule the body bake depends on."""

import unittest

from forge.solver import is_hand_deform, is_solver_input


class SolverInputTests(unittest.TestCase):
    def test_targets_and_offsets_are_solver_inputs(self):
        for name in (
            "arm_L_IKTARGET",
            "arm_R_IKTARGET",
            "leg_L_IKTARGET",
            "leg_R_OFFSET",
            "chestHier_OFFSET",
            "weaponHier_L_IKTARGET",
        ):
            self.assertTrue(is_solver_input(name), name)

    def test_muzzle_and_weapon_hands_are_solver_inputs(self):
        for name in ("muzzle_flash", "muzzle_fx", "weaponHand_L", "weaponHand_R"):
            self.assertTrue(is_solver_input(name), name)

    def test_real_limbs_and_the_root_are_not(self):
        for name in ("root_motion", "pelvis", "spine_2", "head", "hand_L", "tail_0", "target_end"):
            self.assertFalse(is_solver_input(name), name)

    def test_hand_deform_chains_exclude_weapon_and_ik_proxies(self):
        for name in ("hand_L", "hand_R", "finger_index_0_L", "finger_thumb_2_R"):
            self.assertTrue(is_hand_deform(name), name)
        for name in ("weaponHand_L", "weaponIK_hand_L", "weapon_hand_R", "arm_lower_L", "muzzle_flash"):
            self.assertFalse(is_hand_deform(name), name)


if __name__ == "__main__":
    unittest.main()
