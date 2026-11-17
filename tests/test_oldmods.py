from __future__ import annotations

import os
import struct
import tempfile
import time
import unittest
import zlib
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from forge.oldmods import (
    OldModsError,
    content_category,
    content_counts,
    content_shape,
    build_date,
    estimate_toolchain,
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


def build_vpk_hashes(path: Path, entries: list[tuple[str, str, bytes]]) -> Path:
    """Write a VPK directory whose entries carry real CRC and length values."""
    tree = bytearray()

    def cstring(value: str) -> None:
        tree.extend(value.encode())
        tree.append(0)

    groups: dict[str, dict[str, list[tuple[str, bytes]]]] = {}
    for directory, name, data in entries:
        stem, extension = name.rsplit(".", 1)
        groups.setdefault(extension, {}).setdefault(directory, []).append((stem, data))
    for extension, directories in groups.items():
        cstring(extension)
        for directory, stems in directories.items():
            cstring(directory)
            for stem, data in stems:
                cstring(stem)
                tree.extend(
                    struct.pack(
                        "<IHHII",
                        zlib.crc32(data) & 0xFFFFFFFF,
                        0,
                        0x7FFF,
                        0,
                        len(data),
                    )
                )
                tree.extend(struct.pack("<H", 0xFFFF))
            cstring("")
        cstring("")
    cstring("")

    header = struct.pack("<III", 0x55AA1234, 2, len(tree))
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

    def test_content_categories_name_every_part_of_a_package(self) -> None:
        self.assertEqual(content_category("models/heroes_staging/haze/haze.vmdl_c"), "models")
        self.assertEqual(content_category("clips/haze_idle.vnmclip"), "clips")
        self.assertEqual(content_category("materials/haze/haze.vmat"), "materials")
        self.assertEqual(content_category("source.blend"), "blends")
        self.assertEqual(content_category("readme.txt"), "other")
        self.assertEqual(
            content_counts(["a.vmdl", "b.vmdl_c", "c.vmat", "d.blend", "e.txt"]),
            {"models": 2, "clips": 0, "materials": 1, "blends": 1, "other": 1},
        )

    def test_content_shape_reads_the_games_own_folders_and_suffixes(self) -> None:
        game = build_vpk(
            self.tmp_path / "pak01_dir.vpk",
            [
                ("scripts/", "citadel.lua"),
                ("sounds/", "impact.vsnd_c"),
                ("particles/", "spark.vpcf_c"),
            ],
        )

        roots, suffixes = content_shape(game)

        self.assertEqual(roots, {"scripts", "sounds", "particles"})
        self.assertEqual(suffixes, {".lua", ".vsnd_c", ".vpcf_c"})

    def test_toolchain_prediction_uses_tool_release_dates(self) -> None:
        self.assertEqual(build_date("6836 Oct 31 2026"), date(2026, 10, 31))
        self.assertEqual(
            estimate_toolchain(
                "2026-05-02",
                [
                    (date(2024, 5, 25), "4192 May 25 2024"),
                    (date(2026, 10, 31), "6836 Oct 31 2026"),
                ],
            ),
            "CSDK 4192 or newer",
        )
        self.assertEqual(
            estimate_toolchain("2026-10-31", ["6836 Oct 31 2026"]),
            "CSDK 6836 (2026-10-31)",
        )
        self.assertEqual(
            estimate_toolchain("2027-01-01", ["6836 Oct 31 2026"]),
            "CSDK 6836",
        )

    def test_inventory_finds_top_level_compiled_and_script_mods(self) -> None:
        root = self.tmp_path / "mods"
        compiled = root / "compiled_mod" / "models" / "heroes_staging" / "kelvin"
        compiled.mkdir(parents=True)
        (compiled / "kelvin.vmdl_c").write_bytes(b"compiled")
        script = root / "script_mod" / "scripts"
        script.mkdir(parents=True)
        (script / "citadel.lua").write_text("return {}", encoding="utf-8")

        result = inventory([root], since=date(2024, 1, 1))

        by_name = {mod.addon: mod for mod in result.mods if mod.kind == "addon"}
        self.assertEqual(set(by_name), {"compiled_mod", "script_mod"})
        self.assertEqual(by_name["compiled_mod"].hero, "kelvin")
        self.assertEqual(by_name["compiled_mod"].models, ("models/heroes_staging/kelvin/kelvin.vmdl_c",))
        self.assertEqual(by_name["compiled_mod"].counts["models"], 1)
        self.assertEqual(by_name["script_mod"].hero, "")
        self.assertIn("no-model", by_name["script_mod"].note)
        self.assertEqual(by_name["script_mod"].counts["other"], 1)

    def test_inventory_accepts_game_folder_and_suffix_shapes(self) -> None:
        root = self.tmp_path / "mods"
        empty = root / "folder_mod" / "abilities"
        empty.mkdir(parents=True)
        custom = root / "suffix_mod" / "custom"
        custom.mkdir(parents=True)
        (custom / "effect.vjs_c").write_bytes(b"effect")

        result = inventory(
            [root],
            since=date(2024, 1, 1),
            known_roots={"abilities"},
            known_suffixes={".vjs_c"},
        )

        by_name = {mod.addon: mod for mod in result.mods}
        self.assertEqual(set(by_name), {"folder_mod", "suffix_mod"})
        self.assertIn("empty-folder", by_name["folder_mod"].note)
        self.assertEqual(by_name["suffix_mod"].counts["other"], 1)

    def test_inventory_matches_vpk_and_noaddon_loose_files_by_hash(self) -> None:
        root = self.tmp_path / "mods"
        model = root / "compiled_mod" / "models" / "heroes_staging" / "kelvin" / "kelvin.vmdl_c"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"kelvin-compiled")
        second = root / "compiled_mod" / "models" / "heroes_staging" / "haze" / "haze.vmdl_c"
        second.parent.mkdir(parents=True)
        second.write_bytes(b"haze-compiled")

        install = self.tmp_path / "Reduced_CSDK_10"
        game = install / "game" / "citadel"
        game.mkdir(parents=True)
        (game / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
        build_vpk_hashes(
            game / "pak01_dir.vpk",
            [("models/heroes_staging/kelvin/", "kelvin.vmdl_c", b"kelvin-compiled")],
        )
        loose = game / "models" / "heroes_staging" / "haze" / "haze.vmdl_c"
        loose.parent.mkdir(parents=True)
        loose.write_bytes(b"haze-compiled")

        result = inventory(
            [root],
            installs=[SimpleNamespace(root=install, label="CSDK10", build="4391")],
        )

        record = next(mod for mod in result.mods if mod.addon == "compiled_mod")
        matched = {(match.relative, match.kind, match.entry) for match in record.matches}
        self.assertIn(("models/heroes_staging/kelvin/kelvin.vmdl_c", "vpk", "models/heroes_staging/kelvin/kelvin.vmdl_c"), matched)
        self.assertIn(("models/heroes_staging/haze/haze.vmdl_c", "loose", "haze.vmdl_c"), matched)
        self.assertEqual(result.counts()["hash_matches"], 2)
        self.assertEqual(result.counts()["matched_packages"], 1)
        self.assertIn("2 hash matches", result.hash_note)

    def test_inventory_matches_uncompiled_source_files(self):
        root = self.tmp_path / "mods"
        model = root / "source_mod" / "models" / "heroes_staging" / "kelvin" / "kelvin.vmdl"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"source-vmdl")
        mesh = model.parent / "kelvin_body.dmx"
        mesh.write_bytes(b"source-dmx")
        loose = model.parent / "kelvin_loose.vmdl"
        loose.write_bytes(b"loose-source-vmdl")

        install = self.tmp_path / "Reduced_CSDK_10"
        game = install / "game" / "citadel"
        game.mkdir(parents=True)
        (game / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
        build_vpk_hashes(
            game / "pak01_dir.vpk",
            [
                ("models/heroes_staging/kelvin/", "kelvin.vmdl", b"source-vmdl"),
                ("models/heroes_staging/kelvin/", "kelvin_body.dmx", b"source-dmx"),
            ],
        )
        installed_loose = game / "models" / "heroes_staging" / "kelvin" / "kelvin_loose.vmdl"
        installed_loose.parent.mkdir(parents=True)
        installed_loose.write_bytes(b"loose-source-vmdl")

        events: list[tuple[float, str]] = []
        result = inventory(
            [root],
            installs=[SimpleNamespace(root=install, label="CSDK10", build="4391")],
            progress=lambda fraction, message: events.append((fraction, message)),
        )

        record = next(mod for mod in result.mods if mod.addon == "source_mod")
        matched = {(match.relative, match.kind, match.entry) for match in record.matches}
        self.assertIn(("models/heroes_staging/kelvin/kelvin.vmdl", "vpk", "models/heroes_staging/kelvin/kelvin.vmdl"), matched)
        self.assertIn(("models/heroes_staging/kelvin/kelvin_body.dmx", "vpk", "models/heroes_staging/kelvin/kelvin_body.dmx"), matched)
        self.assertIn(("models/heroes_staging/kelvin/kelvin_loose.vmdl", "loose", "kelvin_loose.vmdl"), matched)
        self.assertIn("3 hash matches (3 source, 0 compiled)", result.hash_note)
        self.assertTrue(any("loose" in message for _fraction, message in events))
        fractions = [fraction for fraction, _message in events]
        self.assertEqual(fractions, sorted(fractions))
        self.assertTrue(all(0.0 <= fraction <= 1.0 for fraction in fractions))

    def test_inventory_matches_every_valid_tools_tree_and_addon_root(self) -> None:
        root = self.tmp_path / "mods"
        source = root / "source_mod" / "models" / "heroes_staging" / "kelvin" / "kelvin.vmdl"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"shared-source")

        cs_win = self.tmp_path / "CSwin64_build_10924"
        core = cs_win / "game" / "core"
        core.mkdir(parents=True)
        (core / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
        core_copy = core / "models" / "heroes_staging" / "kelvin" / "kelvin.vmdl"
        core_copy.parent.mkdir(parents=True)
        core_copy.write_bytes(b"shared-source")

        other = self.tmp_path / "Reduced_CSDK_12"
        addon = other / "content" / "future_addons"
        addon_copy = addon / "models" / "heroes_staging" / "kelvin" / "kelvin.vmdl"
        addon_copy.parent.mkdir(parents=True)
        addon_copy.write_bytes(b"shared-source")

        stages: list[tuple[str, str, float, str, str]] = []
        result = inventory(
            [root],
            installs=[
                SimpleNamespace(root=cs_win, label="CSwin64", build="10924"),
                SimpleNamespace(root=other, label="CSDK12", build=""),
            ],
            stage=lambda key, label, value, message, state: stages.append(
                (key, label, value, message, state)
            ),
        )

        record = next(mod for mod in result.mods if mod.addon == "source_mod")
        self.assertEqual({match.label for match in record.matches}, {"CSwin64", "CSDK12"})
        self.assertEqual({match.kind for match in record.matches}, {"loose"})
        self.assertIn("2 hash matches", result.hash_note)
        self.assertIn("root:0", {key for key, *_ in stages})
        self.assertIn("match", {key for key, *_ in stages})
        self.assertTrue(any(state == "DONE" for *_rest, state in stages))
        for key in {key for key, *_ in stages}:
            values = [value for item_key, _label, value, _message, _state in stages if item_key == key]
            self.assertEqual(values, sorted(values), f"stage {key} moved backwards")

    def test_two_mods_roots_with_the_same_leaf_are_inventoried_separately(self) -> None:
        first = self.tmp_path / "Documents" / "mods"
        second = self.tmp_path / "Documents" / "Documents" / "mods"
        for root, name in ((first, "first_mod"), (second, "second_mod")):
            model = root / name / "models" / "heroes_staging" / name / f"{name}.vmdl_c"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"compiled")

        result = inventory([first, second], since=date(2024, 1, 1))

        found = {(mod.addon, mod.path) for mod in result.mods if mod.kind == "addon"}
        self.assertEqual({name for name, _path in found}, {"first_mod", "second_mod"})
        self.assertEqual(len({path for _name, path in found}), 2)
        self.assertEqual(result.counts()["addons"], 2)

    def test_inventory_records_a_vpk_without_a_compiled_model(self) -> None:
        addons = self.tmp_path / "content" / "citadel_addons"
        addons.mkdir(parents=True)
        build_vpk(
            addons / "materials_only.vpk",
            [("materials/haze/", "haze.vmat_c"), ("clips/", "haze_idle.vnmclip_c")],
        )

        result = inventory([self.tmp_path], since=date(2024, 1, 1))

        record = next(mod for mod in result.mods if mod.addon == "materials_only")
        self.assertEqual(record.kind, "vpk")
        self.assertIn("no-compiled-model", record.note)
        self.assertEqual(record.counts["materials"], 1)
        self.assertEqual(record.counts["clips"], 1)
        self.assertEqual(result.counts()["vpks"], 1)

    def test_inventory_records_standalone_blends_and_blends_inside_addons(self) -> None:
        addon = self.tmp_path / "content" / "citadel_addons" / "blend_project"
        addon.mkdir(parents=True)
        (addon / "source.blend").write_bytes(b"BLENDER")
        (addon / "notes.txt").write_text("notes", encoding="utf-8")
        (self.tmp_path / "loose.blend").write_bytes(b"BLENDER")

        result = inventory([self.tmp_path], since=date(2024, 1, 1))

        by_kind = {mod.kind: mod for mod in result.mods}
        self.assertEqual(set(by_kind), {"addon", "blend"})
        self.assertEqual(by_kind["addon"].blends, ("source.blend",))
        self.assertEqual(by_kind["addon"].counts["blends"], 1)
        self.assertEqual(by_kind["blend"].path, str((self.tmp_path / "loose.blend").resolve()))
        self.assertEqual(by_kind["blend"].counts["blends"], 1)
        self.assertEqual(result.counts()["blends"], 1)
        self.assertEqual(result.counts()["blend_files"], 2)

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
