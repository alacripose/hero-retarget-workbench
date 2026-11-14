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
                csdk_root=self.root / "missing-tools",
            )
        self.assertIsNone(env.game_root)
        self.assertIsNone(env.s2v)
        self.assertIsNone(env.csdk_root)
        self.assertTrue(any("configured Deadlock install" in item for item in env.problems))
        self.assertTrue(any("Source 2 Viewer" in item for item in env.problems))
        self.assertTrue(any("CSDK13" in item for item in env.problems))

    def test_a_directory_may_be_chosen_for_the_viewer(self):
        self.assertEqual(paths.find_s2v(self.s2v.parent), self.s2v)

    def test_steam_appmanifest_finds_a_renamed_install(self) -> None:
        library = self.root / "library"
        renamed = library / "steamapps" / "common" / "Citadel Playtest"
        (renamed / "game" / "citadel").mkdir(parents=True)
        (renamed / "game" / "citadel" / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
        (renamed / "game" / "citadel" / "pak01_dir.vpk").write_text("vpk", encoding="utf-8")
        (library / "steamapps" / "appmanifest_1422450.acf").write_text(
            '"AppState"\n{\n\t"installdir"\t\t"Citadel Playtest"\n}\n', encoding="utf-8"
        )

        root, game_dir, problems = paths.find_game(roots=[library])

        self.assertEqual(root, renamed)
        self.assertEqual(game_dir, renamed / "game")
        self.assertEqual(problems, [])

    def test_steam_common_scan_finds_the_game_without_a_manifest(self) -> None:
        library = self.root / "library"
        renamed = library / "steamapps" / "common" / "Some Other Folder"
        (renamed / "game" / "citadel").mkdir(parents=True)
        (renamed / "game" / "citadel" / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
        (renamed / "game" / "citadel" / "pak01_dir.vpk").write_text("vpk", encoding="utf-8")

        root, _game_dir, _problems = paths.find_game(roots=[library])

        self.assertEqual(root, renamed)

    def test_tool_root_finds_the_viewer_the_addon_installed(self) -> None:
        workspace = self.root / "workspace"
        cli = workspace / "tools" / "s2v" / "Source2Viewer-CLI.exe"
        cli.parent.mkdir(parents=True)
        cli.write_bytes(b"cli")

        with patch.dict(os.environ, {"S2V_CLI": "", "PATH": ""}, clear=False):
            self.assertEqual(paths.find_s2v(roots=[workspace]), cli)
            self.assertEqual(
                paths.detect(deadlock_root=self.game, tool_roots=[workspace]).s2v, cli
            )

    def test_a_gui_path_resolves_to_the_cli_beside_it(self):
        gui = self.s2v.with_name("Source2Viewer.exe")
        gui.write_bytes(b"gui")
        self.assertEqual(paths.find_s2v(gui), self.s2v)

    def test_a_gui_folder_without_a_cli_returns_nothing(self):
        folder = self.root / "gui-only"
        folder.mkdir()
        gui = folder / "Source2Viewer.exe"
        gui.write_bytes(b"gui")
        self.assertIsNone(paths.find_s2v(folder))

    def test_a_gui_pick_with_a_cli_beside_it_has_no_note(self):
        gui = self.s2v.with_name("Source2Viewer.exe")
        gui.write_bytes(b"gui")
        self.assertIsNone(paths.s2v_gui_note(gui))
        self.assertIsNone(paths.s2v_gui_note(self.s2v))

    def test_gui_only_path_reports_that_the_gui_has_no_cli_mode(self):
        folder = self.root / "gui-only"
        folder.mkdir()
        gui = folder / "Source2Viewer.exe"
        gui.write_bytes(b"gui")
        env = paths.detect(deadlock_root=self.game, s2v_cli=gui, csdk_root=self.csdk)
        self.assertIsNone(env.s2v)
        self.assertTrue(any("GUI only" in item for item in env.problems))
        self.assertTrue(any("Source2Viewer-CLI.exe" in item for item in env.problems))

    def test_no_vendor_folder_is_a_hardcoded_candidate(self):
        home = self.root / "home"
        (home / "Documents" / "openlock_modern" / "tools" / "s2v").mkdir(parents=True)
        (home / "Documents" / "openlock_modern" / "tools" / "s2v" / "Source2Viewer-CLI.exe").write_bytes(b"fake")
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
            with patch.object(paths, "_tool_search_roots", return_value=[]):
                self.assertIsNone(paths.find_s2v())

    def test_stale_saved_viewer_falls_back_to_a_download_root(self):
        downloads = self.root / "home" / "Downloads"
        cli = downloads / "cli-windows-x64" / "Source2Viewer-CLI.exe"
        cli.parent.mkdir(parents=True)
        cli.write_bytes(b"cli")

        with patch.object(paths, "_tool_search_roots", return_value=[downloads]):
            with patch.dict(os.environ, {"S2V_CLI": "", "PATH": ""}, clear=False):
                self.assertEqual(paths.find_s2v(None), cli)
                env = paths.detect(s2v_cli=self.root / "moved" / "Source2Viewer-CLI.exe")
                self.assertEqual(env.s2v, cli)

    def test_unpacked_csdk_in_a_download_root_is_found(self):
        downloads = self.root / "home" / "Downloads"
        tools = downloads / "Reduced_CSDK_13"
        (tools / "game" / "bin" / "win64").mkdir(parents=True)
        compiler = tools / "game" / "bin" / "win64" / "resourcecompiler.exe"
        compiler.write_bytes(b"compiler")
        (tools / "game" / "citadel").mkdir(parents=True)

        with patch.object(paths, "_tool_search_roots", return_value=[downloads]):
            root, found, _info = paths.find_csdk()

        self.assertEqual(root, tools)
        self.assertEqual(found, compiler)

    def test_source_has_no_personal_or_absolute_user_defaults(self):
        source = Path(paths.__file__).read_text(encoding="utf-8")
        self.assertNotIn("openlock_modern", source)
        self.assertNotIn("Reduced_CSDK_13", source)
        self.assertNotIn("C:\\\\Users\\\\ala", source)


if __name__ == "__main__":
    unittest.main()
