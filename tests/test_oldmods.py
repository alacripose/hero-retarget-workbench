from __future__ import annotations

import struct
from datetime import date
from pathlib import Path

import pytest

from forge.oldmods import (
    OldModsError,
    hero_slugs,
    inventory,
    parse_tree,
    read_vpk,
    slug_from_model,
)

MODELDOC = """[
	{
		"m_keyValues"
		{
			{
				_class = "Softbody"
			}
			{
				_class = "RenderMeshList"
			}
			{
				_class = "PhysicsJointList"
			}
		}
	}
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


def test_parse_tree_reads_extension_directory_and_name() -> None:
    entries = parse_tree(
        b"vmdl_c\0models/heroes_staging/kelvin/\0kelvin\0"
        + struct.pack("<IHHII", 7, 0, 0x7FFF, 0, 0)
        + struct.pack("<H", 0xFFFF)
        + b"\0\0\0"
    )
    assert [entry.path for entry in entries] == ["models/heroes_staging/kelvin/kelvin.vmdl_c"]
    assert entries[0].crc == 7


def test_read_vpk_rejects_foreign_file(tmp_path: Path) -> None:
    bad = tmp_path / "not.vpk"
    bad.write_bytes(b"nope" * 8)
    with pytest.raises(OldModsError, match="vpk-signature-invalid"):
        read_vpk(bad)


def test_read_vpk_lists_entries_and_detects_split_archives(tmp_path: Path) -> None:
    vpk = build_vpk(tmp_path / "old.vpk", [("models/heroes_staging/haze/", "haze.vmdl_c")])
    tree = read_vpk(vpk)
    assert tree.version == 2
    assert [entry.path for entry in tree.entries] == ["models/heroes_staging/haze/haze.vmdl_c"]
    assert tree.split is False


def test_slug_from_model_reads_hero_folder_and_cleans_suffix() -> None:
    assert slug_from_model("models/heroes_staging/kelvin_v2/kelvin_july.vmdl") == "kelvin"
    assert slug_from_model("models/heroes_wip/doorman_v2/doorman_default.vmdl") == "doorman"
    assert slug_from_model("models/heroes_staging/haze/haze_backup.vmdl") == "haze"
    assert hero_slugs(["models/heroes_staging/haze/haze_backup.vmdl"]) == ["haze"]


def test_inventory_finds_cloth_sections_and_skips_game_paks(tmp_path: Path) -> None:
    addons = tmp_path / "content" / "citadel_addons"
    model = addons / "the_janitor" / "models" / "heroes_staging" / "kelvin" / "kelvin.vmdl"
    model.parent.mkdir(parents=True)
    model.write_text(MODELDOC, encoding="utf-8")
    game = tmp_path / "game" / "citadel"
    game.mkdir(parents=True)
    build_vpk(game / "pak01_003.vpk", [("models/heroes_staging/shiv/", "shiv.vmdl_c")])
    build_vpk(addons / "haze_tac9.vpk", [("models/heroes_staging/haze/", "haze.vmdl_c")])

    result = inventory([tmp_path], since=date(2024, 1, 1))

    addons_found = {mod.addon: mod for mod in result.mods}
    assert set(addons_found) == {"the_janitor", "haze_tac9"}
    assert addons_found["the_janitor"].hero == "kelvin"
    assert addons_found["the_janitor"].cloth_sections == ("PhysicsJointList", "Softbody")
    assert addons_found["haze_tac9"].kind == "vpk"
    assert addons_found["haze_tac9"].hero == "haze"
    assert result.counts()["skipped_game_paks"] == 1
    assert result.cloth_types() == {"PhysicsJointList": 1, "Softbody": 1}


def test_inventory_respects_date_window(tmp_path: Path) -> None:
    addons = tmp_path / "content" / "citadel_addons"
    model = addons / "old" / "models" / "heroes_staging" / "haze" / "haze.vmdl"
    model.parent.mkdir(parents=True)
    model.write_text(MODELDOC, encoding="utf-8")
    import os
    import time

    old = time.mktime((2025, 9, 29, 12, 0, 0, 0, 0, -1))
    os.utime(model, (old, old))
    os.utime(model.parent, (old, old))

    assert inventory([tmp_path], since=date(2024, 1, 1), until=date(2026, 1, 1)).mods
    assert inventory([tmp_path], since=date(2026, 1, 1)).mods == []
