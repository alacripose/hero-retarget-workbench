"""Hero mesh parts and cloth chains: what an extraction carries beyond the body."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from forge import cloth


def _write(folder: Path, name: str, size: int = 32) -> Path:
    path = folder / name
    path.write_bytes(b"\0" * size)
    return path


def test_part_name_drops_the_hero_index_but_keeps_the_word():
    assert cloth.part_name("shiv_hair3") == "shiv_hair"
    assert cloth.part_name("shiv_jacket4") == "shiv_jacket"
    assert cloth.part_name("shiv_body") == "shiv_body"


def test_is_cloth_reads_the_hanging_parts_and_not_the_glasses():
    assert cloth.is_cloth("hair")
    assert cloth.is_cloth("jacket4")
    assert cloth.is_cloth("Sp_Hi_Mskirt0")
    assert not cloth.is_cloth("glasses2")
    assert not cloth.is_cloth("gun1")


def test_mesh_files_collects_a_lod_family_and_skips_flat_clips(tmp_path: Path):
    _write(tmp_path, "shiv_body.dmx", 400)
    _write(tmp_path, "shiv_body_lod15.dmx")
    _write(tmp_path, "shiv_hair3.dmx")
    _write(tmp_path, "shiv_hair_lod18.dmx")
    _write(tmp_path, "shiv_primary_idle.dmx")
    _write(tmp_path, "shiv_ability_shiv_dash.dmx")
    (tmp_path / "clips").mkdir()
    _write(tmp_path / "clips", "dash.dmx")

    found = cloth.mesh_files(tmp_path)
    assert [row.stem for row in found] == ["shiv_body", "shiv_hair3"]
    assert found[0].lods and found[0].lods[0].name == "shiv_body_lod15.dmx"
    assert found[1].cloth and not found[0].cloth


def test_mesh_files_matches_lods_named_after_the_part_not_the_indexed_base(tmp_path: Path):
    _write(tmp_path, "shiv_glasses2.dmx")
    _write(tmp_path, "shiv_glasses_lod17.dmx")
    _write(tmp_path, "shiv_glasses_lod212.dmx")
    _write(tmp_path, "shiv_gun1.dmx")
    _write(tmp_path, "shiv_gun_lod16.dmx")
    found = cloth.mesh_files(tmp_path)
    assert [row.stem for row in found] == ["shiv_glasses2", "shiv_gun1"]
    assert len(found[0].lods) == 2
    assert [lod.name for lod in found[1].lods] == ["shiv_gun_lod16.dmx"]


def test_mesh_files_keeps_a_cloth_part_that_has_no_lods(tmp_path: Path):
    _write(tmp_path, "doorman_jacket.dmx")
    _write(tmp_path, "doorman_idle.dmx")
    found = cloth.mesh_files(tmp_path)
    assert [row.stem for row in found] == ["doorman_jacket"]


def test_mesh_files_keeps_a_numbered_head_and_its_lod(tmp_path: Path):
    _write(tmp_path, "familiar_wip_8inf_body8.dmx", 400)
    _write(tmp_path, "familiar_wip_head5.dmx", 900)
    _write(tmp_path, "familiar_wip_head_lod12.dmx")
    _write(tmp_path, "familiar_wip_aim_idle.dmx")
    found = cloth.mesh_files(tmp_path)
    assert [row.stem for row in found] == [
        "familiar_wip_8inf_body8",
        "familiar_wip_head5",
    ]
    assert [lod.name for lod in found[1].lods] == ["familiar_wip_head_lod12.dmx"]


def test_mesh_files_on_a_missing_folder_is_empty(tmp_path: Path):
    assert cloth.mesh_files(tmp_path / "nope") == []


def test_chains_group_numbered_bones_by_base_and_side():
    names = [
        "pelvis",
        "jacket_0_L",
        "jacket_1_L",
        "jacket_2_L",
        "jacket_0_R",
        "jacket_1_R",
        "hair_01",
        "hair_02",
        "finger_index_0_L",
    ]
    found = {chain.name: chain for chain in cloth.chains(names)}
    assert found["jacket_L"].bones == ("jacket_0_L", "jacket_1_L", "jacket_2_L")
    assert found["jacket_R"].bones == ("jacket_0_R", "jacket_1_R")
    assert found["hair"].bones == ("hair_01", "hair_02")
    assert "finger_index_L" not in found  # one segment is not a chain
    assert found["jacket_L"].cloth


def test_cloth_chains_leaves_fingers_out():
    names = ["finger_index_0_L", "finger_index_1_L", "jacket_0_L", "jacket_1_L"]
    found = [chain.name for chain in cloth.cloth_chains(names)]
    assert found == ["jacket_L"]


def test_chain_order_is_deterministic_and_by_index_not_text():
    names = ["hem_2_L", "hem_10_L", "hem_1_L"]
    assert cloth.chains(names)[0].bones == ("hem_1_L", "hem_2_L", "hem_10_L")


class MeshBlindSpotTests(unittest.TestCase):
    def test_numbered_head_and_lod_are_companions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _write(root, "familiar_wip_8inf_body8.dmx", 400)
            _write(root, "familiar_wip_head5.dmx", 900)
            _write(root, "familiar_wip_head_lod12.dmx")
            _write(root, "familiar_wip_aim_idle.dmx")
            found = cloth.mesh_files(root)
            self.assertEqual(
                [row.stem for row in found],
                ["familiar_wip_8inf_body8", "familiar_wip_head5"],
            )
            self.assertEqual([lod.name for lod in found[1].lods], ["familiar_wip_head_lod12.dmx"])

    def test_render_variants_do_not_duplicate_a_part(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _write(root, "hero_body.dmx", 400)
            _write(root, "hero_head5.dmx", 900)
            _write(root, "hero_head_eyes_closed7.dmx")
            _write(root, "hero_head_ui_smile6.dmx")
            _write(root, "hero_clothes1.dmx", 300)
            _write(root, "hero_clothes_no_shirt11.dmx", 300)
            _write(root, "hero_clothes_nosim9.dmx", 300)
            _write(root, "hero_cloth_proxy.dmx")
            _write(root, "hero_duplicate.dmx", 500)
            found = cloth.mesh_files(root)
            self.assertEqual([row.stem for row in found], ["hero_body", "hero_clothes1", "hero_head5"])
