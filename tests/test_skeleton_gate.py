"""A release pak is only packed after comparison with the game's own skeleton.

The 2026-11-15 Haze pak shipped with `pelvis` as a root, `weaponHand_L/R` under
`hand_L`/`hand_R`, and all nine tail joints parented straight to `pelvis`. In game
that is a body wrong below the pelvis, head and arms rotated, and a tail lying on
the ground. The gate learned three checks for exactly that, and this pins the one
thing that made them run: the pack refuses without the game's skeleton to compare
against.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACK = REPO / "tools" / "tail_release_pack.py"


class ReleasePackNeedsGameSkeleton(unittest.TestCase):
    def test_without_game_skeleton_the_pack_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            addon = Path(folder) / "haze_tail"
            addon.mkdir()
            proc = subprocess.run(
                [
                    sys.executable,
                    str(PACK),
                    "--addon-game",
                    str(addon),
                    "--out",
                    str(Path(folder) / "haze.vpk"),
                    "--clips",
                    str(Path(folder) / "clips"),
                ],
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("gate-needs-game-skeleton", proc.stderr + proc.stdout)

    def test_skip_gate_is_the_only_escape(self):
        source = PACK.read_text(encoding="utf-8")
        self.assertIn("skip_gate", source)
        # The refusal must sit before the gate call, not after a pak already exists.
        self.assertLess(
            source.index("gate-needs-game-skeleton"),
            source.index("probe = subprocess.run("),
        )


if __name__ == "__main__":
    unittest.main()
