"""Tail channel matching: exact and numbered, never a guessed neighbour."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from forge import tailimage, tails


def test_exact_tail_names_pair():
    rows = tails.candidates(["tail_01", "tail_02", "pelvis"], ["tail_01", "tail_02"])
    assert [(row.source, row.target, row.state) for row in rows] == [
        ("tail_01", "tail_01", "MATCHED"),
        ("tail_02", "tail_02", "MATCHED"),
    ]


def test_normalized_and_numbered_names_pair_without_inventing():
    rows = tails.candidates(["Tail_01", "Tail_02", "tail_03"], ["tail01", "tail_02"])
    assert [(row.source, row.target, row.state) for row in rows] == [
        ("Tail_01", "tail01", "MATCHED"),
        ("Tail_02", "tail_02", "MATCHED"),
        ("tail_03", "", "CHOOSE"),
    ]


def test_only_tail_channels_are_listed():
    rows = tails.candidates(["pelvis", "spine_01", "hair_01", "ponytail"], ["ponytail"])
    assert [row.source for row in rows] == ["hair_01", "ponytail"]


def test_mapping_ignores_unanswered_rows():
    rows = tails.candidates(["tail_01", "tail_02"], ["tail_01"])
    assert tails.mapping(rows) == {"tail_01": "tail_01"}


def test_clip_header_scan_finds_tail_bones_without_opening_the_dmx(tmp_path):
    path = tmp_path / "aim_idle.dmx"
    path.write_bytes(
        b"<!-- dmx encoding binary 9 format model 22 -->\0"
        b"DmeJoint\0tail_0\0tail_1\0tail_end\0weapon_target_tail\0pelvis\0"
    )
    assert tails.dmx_bone_names(path) == ["tail_0", "tail_1", "tail_end"]


def test_chains_group_numbered_tail_bones_and_ignore_targets():
    found = {chain.name: chain.bones for chain in tails.chains([
        "tail_0", "tail_1", "tail_2", "tail_end",
        "tail_finger_0", "tail_finger_1", "weapon_target_tail", "hair_01",
    ])}
    assert found["tail"] == ("tail_0", "tail_1", "tail_2", "tail_end")
    assert found["tail_finger"] == ("tail_finger_0", "tail_finger_1")
    assert "weapon_target_tail" not in [
        bone for chain in tails.chains(["weapon_target_tail"]) for bone in chain.bones
    ]


def test_tail_thumbnail_is_a_real_png(tmp_path):
    output = tailimage.write_tail_png(
        tmp_path / "tail.png",
        [[(0.0, 0.0, 0.0), (0.0, 0.4, 0.0), (0.0, 0.8, 0.1)]],
        size=32,
    )
    assert output is not None and output.is_file()
    data = output.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[16:20] == b"\x00\x00\x00\x20"


class TailClipScanTests(unittest.TestCase):
    def test_clip_header_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "aim_idle.dmx"
            target.write_bytes(
                b"<!-- dmx encoding binary 9 format model 22 -->\0"
                b"DmeJoint\0tail_0\0tail_1\0tail_end\0weapon_target_tail\0pelvis\0"
            )
            self.assertEqual(tails.dmx_bone_names(target), ["tail_0", "tail_1", "tail_end"])

    def test_tail_chains(self):
        found = {
            chain.name: chain.bones
            for chain in tails.chains(
                ["tail_0", "tail_1", "tail_2", "tail_end", "tail_finger_0", "tail_finger_1", "weapon_target_tail"]
            )
        }
        self.assertEqual(found["tail"], ("tail_0", "tail_1", "tail_2", "tail_end"))
        self.assertEqual(found["tail_finger"], ("tail_finger_0", "tail_finger_1"))
        self.assertNotIn("weapon_target_tail", [name for row in tails.chains(["weapon_target_tail"]) for name in row.bones])

    def test_thumbnail(self):
        with tempfile.TemporaryDirectory() as folder:
            output = tailimage.write_tail_png(
                Path(folder) / "tail.png",
                [[(0.0, 0.0, 0.0), (0.0, 0.4, 0.0), (0.0, 0.8, 0.1)]],
                size=32,
            )
            self.assertIsNotNone(output)
            data = output.read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(data[16:20], b"\x00\x00\x00\x20")