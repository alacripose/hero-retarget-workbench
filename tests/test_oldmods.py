from __future__ import annotations

import os
import struct
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

from forge.oldmods import (
    OldModsError,
    hero_slugs,
    inventory,
    parse_tree,
    read_vpk,
    slug_from_model,
)

MODELDOC = """[
\t{
\t\t"m_keyValues"
\t\t{
\t\t\t{
\t\t\t\t_class = "Softbody"
\t\t\t}
\t\t\t{
\t\t\t\t_class = "RenderMeshList"
\t\t\t}
\t\t\t{
\t\t\t\t_class = "PhysicsJointList"
\t\t\t}
\t\t}
\t}
]
"""


def build_vpk(path: Path, entries: list[tuple[str, str]], *, version: int = 2) -> Path:
    """Write a minimal VPK whose tree lists the given (directory, filename.ext)."""
    tree = bytearray()

    def cstring(value: str) -> None:
        tree.extend(value.encode())
        tree.append(0)

    groups: dict[str, dict[str, list[str]]] = {}
    for directory, name in entries:
        stem, extension = name.rsplit(".", 1)
        groups.setdefault(extension, {}).setdefault(directory, []).append(stem)
    for extension, directories in groups.items():
        cstring(extension)
        for directory, stems in directories.items():
            cstring(directory)
            for stem in stems:
                cstring(stem)
                tree.extend(struct.pack("<IHHII", 0, 0, 0x7FFF, 0, 0))
                tree.extend(struct.pack("<H", 0xFFFF))
            cstring("")
        cstring("")
    cstring("")

    header = struct.pack("<III", 0x55AA1234, version, len(tree))
    if version == 2:
        header += struct.pack("<IIII", 0, 0, 0, 0)
    path.write_bytes(header + bytes(tree))
    return path


class OldModsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parse_tree_reads_extension_directory_and_name(self) -> None:
        entries = parse_tree(
            b"vmdl_c\0models/heroes_staging/kelvin/\0kelvin\0"
            + struct.pack("<IHHII", 7, 0, 0x7FFF, 0, 0)
            + struct.pack("<H", 0xFFFF)
            + b"\0\0\0"
        )
        self.assertEqual(
            [entry.path for entry in entries],
            ["models/heroes_staging/kelvin/kelvin.vmdl_c"],
        )
        self.assertEqual(entries[0].crc, 7)

    def test_read_vpk_rejects_foreign_file(self) -> None:
        bad = self.tmp_path / "not.vpk"
        bad.write_bytes(b"nope" * 8)
        with self.assertRaisesRegex(OldModsError, "vpk-signature-invalid"):
            read_vpk(bad)

    def test_read_vpk_lists_entries_and_detects_split_archives(self) -> None:
        vpk = build_vpk(
            self.tmp_path / "old.vpk", [("models/heroes_staging/haze/", "haze.vmdl_c")]
        )
        tree = read_vpk(vpk)
        self.assertEqual(tree.version, 2)
        self.assertEqual(
            [entry.path for entry in tree.entries],
            ["models/heroes_staging/haze/haze.vmdl_c"],
        )
        self.assertFalse(tree.split)

    def test_slug_from_model_reads_hero_folder_and_cleans_suffix(self) -> None:
        self.assertEqual(
            slug_from_model("models/heroes_staging/kelvin_v2/kelvin_july.vmdl"), "kelvin"
        )
        self.assertEqual(
            slug_from_model("models/heroes_wip/doorman_v2/doorman_default.vmdl"), "doorman"
        )
        self.assertEqual(
            slug_from_model("models/heroes_staging/haze/haze_backup.vmdl"), "haze"
        )
        self.assertEqual(
            hero_slugs(["models/heroes_staging/haze/haze_backup.vmdl"]), ["haze"]
        )

    def test_inventory_finds_cloth_sections_and_skips_game_paks(self) -> None:
        addons = self.tmp_path / "content" / "citadel_addons"
        model = (
            addons / "the_janitor" / "models" / "heroes_staging" / "kelvin" / "kelvin.vmdl"
        )
        model.parent.mkdir(parents=True)
        model.write_text(MODELDOC, encoding="utf-8")
        game = self.tmp_path / "game" / "citadel"
        game.mkdir(parents=True)
        build_vpk(
            game / "pak01_003.vpk",
            [("models/heroes_staging/shiv/", "shiv.vmdl_c")],
        )
        build_vpk(
            addons / "haze_tac9.vpk",
            [("models/heroes_staging/haze/", "haze.vmdl_c")],
        )

        result = inventory([self.tmp_path], since=date(2024, 1, 1))

        addons_found = {mod.addon: mod for mod in result.mods}
        self.assertEqual(set(addons_found), {"the_janitor", "haze_tac9"})
        self.assertEqual(addons_found["the_janitor"].hero, "kelvin")
        self.assertEqual(
            addons_found["the_janitor"].cloth_sections, ("PhysicsJointList", "Softbody")
        )
        self.assertEqual(addons_found["haze_tac9"].kind, "vpk")
        self.assertEqual(addons_found["haze_tac9"].hero, "haze")
        self.assertEqual(result.counts()["skipped_game_paks"], 1)
        self.assertEqual(
            result.cloth_types(), {"PhysicsJointList": 1, "Softbody": 1}
        )

    def test_inventory_reports_progress_for_a_scan(self) -> None:
        addons = self.tmp_path / "content" / "citadel_addons"
        model = addons / "old" / "models" / "heroes_staging" / "haze" / "haze.vmdl"
        model.parent.mkdir(parents=True)
        model.write_text(MODELDOC, encoding="utf-8")
        events: list[tuple[float, str]] = []

        result = inventory(
            [self.tmp_path], progress=lambda fraction, message: events.append((fraction, message))
        )

        self.assertTrue(result.mods)
        self.assertTrue(events, "a scan with a button must report progress")
        fractions = [fraction for fraction, _message in events]
        self.assertEqual(fractions, sorted(fractions))
        self.assertTrue(all(0.0 <= fraction <= 1.0 for fraction in fractions))
        self.assertTrue(all(message.strip() for _fraction, message in events))

    def test_inventory_respects_date_window(self) -> None:
        addons = self.tmp_path / "content" / "citadel_addons"
        model = addons / "old" / "models" / "heroes_staging" / "haze" / "haze.vmdl"
        model.parent.mkdir(parents=True)
        model.write_text(MODELDOC, encoding="utf-8")
        old = time.mktime((2025, 9, 29, 12, 0, 0, 0, 0, -1))
        os.utime(model, (old, old))
        os.utime(model.parent, (old, old))

        self.assertTrue(
            inventory([self.tmp_path], since=date(2024, 1, 1), until=date(2026, 1, 1)).mods
        )
        self.assertEqual(
            inventory([self.tmp_path], since=date(2026, 1, 1)).mods, []
        )


if __name__ == "__main__":
    unittest.main()
