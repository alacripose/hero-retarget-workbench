from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import paths


class PathConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = self.root / "Deadlock"
        (self.game / "game" / "citadel").mkdir(parents=True)
        (self.game / "game" / "citadel" / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
        (self.game / "game" / "citadel" / "pak01_dir.vpk").write_text("vpk", encoding="utf-8")
        (self.game / "game" / "citadel" / "steam.inf").write_text(
            "ClientVersion=6861\nVersionDate=Nov 09 2026\n",
            encoding="utf-8",
        )
        self.s2v = self.root / "tools" / "Source2Viewer-CLI.exe"
        self.s2v.parent.mkdir()
        self.s2v.write_bytes(b"s2v")
        self.csdk = self.root / "csdk"
        (self.csdk / "game" / "bin" / "win64").mkdir(parents=True)
        (self.csdk / "game" / "bin" / "win64" / "resourcecompiler.exe").write_bytes(b"compiler")
        (self.csdk / "game" / "citadel").mkdir(parents=True)
        (self.csdk / "game" / "citadel" / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_scene_paths_win_over_environment_and_build_is_read(self):
        with patch.dict(
            os.environ,
            {
                "DEADLOCK_GAME": str(self.root / "wrong-game"),
                "S2V_CLI": str(self.root / "wrong-s2v.exe"),
                "CSDK13_ROOT": str(self.root / "wrong-csdk"),
            },
            clear=False,
        ):
            env = paths.detect(
                deadlock_root=self.game,
                s2v_cli=self.s2v,
                csdk_root=self.csdk,
            )
        self.assertEqual(env.game_root, self.game)
        self.assertEqual(env.s2v, self.s2v)
        self.assertEqual(env.csdk_root, self.csdk)
        self.assertEqual(env.resourcecompiler, self.csdk / "game" / "bin" / "win64" / "resourcecompiler.exe")
        self.assertEqual(env.build, "6861")
        self.assertEqual(env.version_date, "Nov 09 2026")

    def test_a_set_but_invalid_path_does_not_fall_back(self):
        with patch.dict(
            os.environ,
            {
                "DEADLOCK_GAME": str(self.game),
                "S2V_CLI": str(self.s2v),
                "CSDK13_ROOT": str(self.csdk),
            },
            clear=False,
        ):
            env = paths.detect(
                deadlock_root=self.root / "missing-game",
                s2v_cli=self.root / "missing-s2v.exe",
                csdk_root=self.root / "missing-csdk",
            )
        self.assertIsNone(env.game_root)
        self.assertIsNone(env.s2v)
        self.assertIsNone(env.csdk_root)
        self.assertTrue(any("configured Deadlock install" in item for item in env.problems))
        self.assertTrue(any("Source 2 Viewer" in item for item in env.problems))
        self.assertTrue(any("CSDK13" in item for item in env.problems))

    def test_a_directory_may_be_chosen_for_the_viewer(self):
        self.assertEqual(paths.find_s2v(self.s2v.parent), self.s2v)

    def test_the_viewer_gui_is_not_accepted_as_the_cli(self):
        gui = self.s2v.with_name("Source2Viewer.exe")
        gui.write_bytes(b"gui")
        self.assertIsNone(paths.find_s2v(gui))

    def test_gui_path_reports_a_specific_problem(self):
        gui = self.s2v.with_name("Source2Viewer.exe")
        gui.write_bytes(b"gui")
        env = paths.detect(deadlock_root=self.game, s2v_cli=gui, csdk_root=self.csdk)
        self.assertIsNone(env.s2v)
        self.assertTrue(any("GUI selected" in item for item in env.problems))

    def test_personal_folders_are_not_candidates(self):
        home = self.root / "home"
        (home / "Documents" / "openlock_modern" / "tools" / "s2v").mkdir(parents=True)
        (home / "Documents" / "openlock_modern" / "tools" / "s2v" / "Source2Viewer-CLI.exe").write_bytes(b"fake")
        (home / "Downloads" / "Reduced_CSDK_13" / "game" / "bin" / "win64").mkdir(parents=True)
        (home / "Downloads" / "Reduced_CSDK_13" / "game" / "bin" / "win64" / "resourcecompiler.exe").write_bytes(b"fake")
        with patch.dict(
            os.environ,
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "PATH": "",
                "S2V_CLI": "",
                "CSDK13_ROOT": "",
            },
            clear=False,
        ):
            self.assertIsNone(paths.find_s2v())
            self.assertIsNone(paths.find_csdk()[0])

    def test_source_has_no_personal_or_drive_letter_defaults(self):
        source = Path(paths.__file__).read_text(encoding="utf-8")
        self.assertNotIn("openlock_modern", source)
        self.assertNotIn("Reduced_CSDK_13", source)
        self.assertNotIn("for letter in", source)
        self.assertNotIn("Path.home()", source)


if __name__ == "__main__":
    unittest.main()
