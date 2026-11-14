from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import installs


def make_tree(root: Path, game: str, *, deadlock_exe: bool = False, compiler: bool = False,
              vpk: bool = False, build: str = "") -> Path:
    info = root / "game" / game
    info.mkdir(parents=True)
    (info / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
    if build:
        (info / "steam.inf").write_text(build, encoding="utf-8")
    bin_dir = root / "game" / "bin" / "win64"
    bin_dir.mkdir(parents=True)
    name = "deadlock.exe" if deadlock_exe else "cs2.exe" if game == "csgo" else ""
    if name:
        (bin_dir / name).write_bytes(b"exe")
    if compiler:
        (bin_dir / "resourcecompiler.exe").write_bytes(b"compiler")
    if vpk:
        (info / "pak01_dir.vpk").write_bytes(b"vpk")
    return root


class InstallDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.drive = self.root / "drive"
        self.drive.mkdir()
        self.library = self.drive / "SteamLibrary"
        (self.library / "steamapps" / "common").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_steam_common_finds_deadlock_cs2_and_tools_trees(self) -> None:
        make_tree(
            self.library / "steamapps" / "common" / "Deadlock",
            "citadel",
            deadlock_exe=True,
            vpk=True,
            build="ClientVersion=6861\nVersionDate=Nov 09 2026\n",
        )
        make_tree(
            self.library / "steamapps" / "common" / "Counter-Strike Global Offensive",
            "csgo",
            build="ClientVersion=14000\n",
        )
        make_tree(
            self.library / "steamapps" / "common" / "Reduced_CSDK_13",
            "citadel",
            compiler=True,
        )

        rows = installs.discover(libraries=[self.library], drives=[])
        by_name = {row.label: row for row in rows}

        self.assertEqual(set(by_name), {"Deadlock", "Counter-Strike Global Offensive", "Reduced_CSDK_13"})
        self.assertEqual(by_name["Deadlock"].kind, "game")
        self.assertTrue(by_name["Deadlock"].can_backport)
        self.assertEqual(by_name["Deadlock"].build, "6861 Nov 09 2026")
        self.assertFalse(by_name["Deadlock"].can_compile)
        self.assertEqual(by_name["Counter-Strike Global Offensive"].engine, "csgo")
        self.assertEqual(by_name["Counter-Strike Global Offensive"].kind, "game")
        self.assertEqual(by_name["Reduced_CSDK_13"].kind, "tools")
        self.assertTrue(by_name["Reduced_CSDK_13"].can_compile)
        self.assertFalse(by_name["Reduced_CSDK_13"].can_backport)

    def test_preview_and_tools_placements_across_a_drive_are_found(self) -> None:
        make_tree(
            self.drive / "Users" / "anyone" / "Documents" / "Documents" / "deadlockpreview"
            / "Project8Staging" / "Reduced_CSDK_10",
            "citadel",
            compiler=True,
        )
        make_tree(
            self.drive / "Users" / "anyone" / "Downloads" / "CSwin64_build_123",
            "core",
            compiler=True,
        )
        rows = installs.discover(libraries=[], drives=[self.drive])
        names = {row.label for row in rows}

        self.assertIn("Reduced_CSDK_10", names)
        self.assertIn("CSwin64_build_123", names)
        by_name = {row.label: row for row in rows}
        self.assertEqual(by_name["CSwin64_build_123"].kind, "tools")
        self.assertEqual(by_name["CSwin64_build_123"].engine, "core")
        self.assertTrue(by_name["CSwin64_build_123"].can_compile)

    def test_steam_content_depots_are_read(self) -> None:
        depot = self.library / "steamapps" / "content" / "app_1422450" / "depot_1422456"
        make_tree(depot, "citadel", deadlock_exe=True, vpk=True)

        rows = installs.discover(libraries=[self.library], drives=[])

        self.assertEqual([row.label for row in rows], ["depot_1422456"])
        self.assertTrue(rows[0].can_backport)

    def test_a_citadel_tree_with_project8_but_no_deadlock_exe_is_tools(self) -> None:
        root = make_tree(
            self.library / "steamapps" / "common" / "Reduced_CSDK_13",
            "citadel",
            compiler=True,
        )
        (root / "game" / "bin" / "win64" / "project8.exe").write_bytes(b"exe")

        rows = installs.discover(libraries=[self.library], drives=[])

        self.assertEqual(rows[0].kind, "tools")
        self.assertTrue(rows[0].can_compile)

    def test_a_client_folder_is_searched_to_a_bounded_depth(self) -> None:
        nested = self.root / "clients" / "old" / "Reduced_CSDK_10"
        make_tree(nested, "citadel", compiler=True)

        rows = installs.discover(self.root / "clients", libraries=[], drives=[])

        self.assertEqual([row.label for row in rows], ["Reduced_CSDK_10"])

    def test_the_real_steam_libraries_still_work(self) -> None:
        with patch.object(installs, "steam_libraries", return_value=[]):
            rows = installs.discover(libraries=[], drives=[])
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
