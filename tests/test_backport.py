from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from forge import backport
from forge.backport import BackportError, backport_package, client_build, find_client_model
from forge.paths import Environment


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


class BackportBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_game(self) -> Path:
        game = self.tmp_path / "old-client" / "game" / "citadel"
        game.mkdir(parents=True)
        (game / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
        return game

    def test_client_build_accepts_install_game_or_citadel_root(self) -> None:
        game = self.make_game()
        build_vpk(game / "pak01_dir.vpk", [("models/heroes_wip/kelvin/", "kelvin.vmdl_c")])
        for root in (self.tmp_path / "old-client", self.tmp_path / "old-client" / "game", game):
            build = client_build(root)
            self.assertEqual(build.game_dir, game)
            self.assertEqual([path.name for path in build.vpks], ["pak01_dir.vpk"])
            self.assertIsNotNone(build.gameinfo)

    def test_client_build_searches_every_pack_and_skips_chunks(self) -> None:
        game = self.make_game()
        build_vpk(game / "pak01_dir.vpk", [("models/heroes_wip/kelvin/", "kelvin.vmdl_c")])
        build_vpk(game / "pak01_000.vpk", [])
        build_vpk(game / "pak02_dir.vpk", [("models/heroes_wip/haze/", "haze.vmdl_c")])
        addons = game / "addons"
        addons.mkdir()
        build_vpk(addons / "custom.vpk", [("models/heroes_wip/shiv/", "shiv.vmdl_c")])

        build = client_build(game)
        names = [path.name for path in build.vpks]
        self.assertEqual(names, ["pak01_dir.vpk", "pak02_dir.vpk", "custom.vpk"])

    def test_exact_model_wins_even_in_a_second_pack(self) -> None:
        game = self.make_game()
        build_vpk(game / "pak01_dir.vpk", [("models/heroes_wip/kelvin/", "kelvin.vmdl_c")])
        wanted = "models/heroes_wip/haze/haze.vmdl"
        vpk = build_vpk(game / "pak02_dir.vpk", [("models/heroes_wip/haze/", "haze.vmdl")])
        build = client_build(game)

        match = find_client_model(build, wanted, "haze")

        self.assertTrue(match.exact)
        self.assertEqual(match.relative, "models/heroes_wip/haze/haze.vmdl")
        self.assertEqual(match.vpk, vpk)

    def test_model_source_path_matches_its_compiled_entry(self) -> None:
        game = self.make_game()
        build_vpk(game / "pak01_dir.vpk", [("models/heroes_wip/kelvin/", "kelvin.vmdl_c")])
        build = client_build(game)

        match = find_client_model(build, "models/heroes_wip/kelvin/kelvin.vmdl", "kelvin")

        self.assertTrue(match.exact)
        self.assertEqual(match.relative, "models/heroes_wip/kelvin/kelvin.vmdl_c")

    def test_hero_slug_finds_a_moved_model_and_marks_it_substituted(self) -> None:
        game = self.make_game()
        build_vpk(
            game / "pak02_dir.vpk",
            [
                ("models/heroes_wip/doorman_v2/", "doorman.vmdl"),
                ("models/heroes_wip/doorman_v2/", "doorman_alt.vmdl"),
            ],
        )
        build = client_build(game)

        match = find_client_model(
            build, "models/heroes_staging/doorman/doorman.vmdl", "doorman, wrecker"
        )

        self.assertFalse(match.exact)
        self.assertEqual(match.relative, "models/heroes_wip/doorman_v2/doorman.vmdl")

    def test_missing_model_names_what_was_searched(self) -> None:
        game = self.make_game()
        build_vpk(game / "pak01_dir.vpk", [("models/heroes_wip/kelvin/", "kelvin.vmdl_c")])
        build = client_build(game)

        with self.assertRaisesRegex(BackportError, "client-model-missing.*1 vpks"):
            find_client_model(build, "models/heroes_wip/haze/haze.vmdl", "haze")

    def test_backport_uses_the_resolved_client_model_and_records_it(self) -> None:
        game = self.make_game()
        vpk = build_vpk(
            game / "pak02_dir.vpk",
            [("models/heroes_wip/doorman_v2/", "doorman.vmdl")],
        )
        package = self.tmp_path / "mod"
        old_model = package / "models" / "heroes_staging" / "doorman" / "doorman.vmdl"
        old_model.parent.mkdir(parents=True)
        old_model.write_text("[old]", encoding="utf-8")
        output = self.tmp_path / "out"
        captured: dict = {}

        def fake_extract(env, relative, destination, *, vpk=None, timeout=0):
            destination = Path(destination)
            destination.mkdir(parents=True, exist_ok=True)
            model = destination / "doorman.vmdl"
            model.write_text("[client]", encoding="utf-8")
            captured["extract"] = (relative, Path(vpk) if vpk else None)
            return model

        def fake_migrate(**kwargs):
            captured.update(kwargs)
            manifest = Path(kwargs["output"]) / "manifest.json"
            manifest.write_text("{}\n", encoding="utf-8")
            return SimpleNamespace(manifest=manifest, output=kwargs["output"], new_root=kwargs["new_root"], sections={})

        env = Environment(s2v=Path("s2v.exe"))
        with mock.patch.object(backport, "extract_client_model", fake_extract), mock.patch.object(
            backport.migrate, "extract_package", lambda env, path, destination, timeout=0: Path(path)
        ), mock.patch.object(backport.migrate, "migrate_trees", fake_migrate):
            result = backport_package(
                env,
                game,
                package,
                output,
                "doorman_backport",
                relative="models/heroes_staging/doorman/doorman.vmdl",
                hero="doorman",
                force=True,
            )

        self.assertEqual(captured["extract"], ("models/heroes_wip/doorman_v2/doorman.vmdl", vpk))
        self.assertEqual(captured["addon_name"], "doorman_backport")
        self.assertEqual(
            captured["vmdl_relative"], "models/heroes_wip/doorman_v2/doorman.vmdl"
        )
        self.assertEqual(captured["old_vmdl"], old_model)
        data = json.loads(Path(result.manifest).read_text(encoding="utf-8"))
        self.assertFalse(data["backport_exact_model"])
        self.assertEqual(data["backport_client_vpk"], str(vpk))
        self.assertEqual(data["backport_model"], "models/heroes_wip/doorman_v2/doorman.vmdl")

    def test_single_file_pack_without_gameinfo_is_a_build(self) -> None:
        game = self.tmp_path / "repack" / "game" / "citadel"
        game.mkdir(parents=True)
        build_vpk(game / "pak01.vpk", [("models/heroes_wip/haze/", "haze.vmdl")], version=1)
        build = client_build(game)

        self.assertIsNone(build.gameinfo)
        self.assertEqual([path.name for path in build.vpks], ["pak01.vpk"])
        self.assertTrue(find_client_model(build, "", "haze").exact is False)


if __name__ == "__main__":
    unittest.main()
