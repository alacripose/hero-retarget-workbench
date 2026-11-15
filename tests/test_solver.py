"""The solver-input rule the body bake depends on."""

import unittest

from forge.solver import is_solver_input


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


if __name__ == "__main__":
    unittest.main()
