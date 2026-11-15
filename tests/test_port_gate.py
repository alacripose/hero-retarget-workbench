"""The port tooling must not be pinned to one hero.

These tests build a fake extraction for an arbitrary hero and prove that the
resolver finds it, that a pin is checked from data, and that a candidate pin
does not make the project gate red.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import port_gate  # noqa: E402
from forge import port_target  # noqa: E402


def make_extraction(root: Path, hero: str) -> Path:
    folder = root / "models" / "heroes_staging" / hero
    (folder / "clips").mkdir(parents=True)
    (folder / "dmx" / "mesh").mkdir(parents=True)
    (folder / f"{hero}.vmdl").write_text("model", encoding="utf-8")
    (folder / f"{hero}_body.dmx").write_text("body", encoding="utf-8")
    (folder / f"{hero}_body_lod13.dmx").write_text("lod", encoding="utf-8")
    (folder / "dmx" / "mesh" / f"{hero}_skel.dmx").write_text("skeleton tail_0", encoding="utf-8")
    (folder / "clips" / "aim_weapon_idle.dmx").write_text("clip", encoding="utf-8")
    (folder / "clips" / "aim_weapon_idle.vnmclip+non_additive.dmx").write_text("variant", encoding="utf-8")
    return folder


class PortTargetTests(unittest.TestCase):
    def test_describe_finds_any_hero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_extraction(root, "kestrel")
            found = port_target.describe(root)
            self.assertEqual(found["hero"], "kestrel")
            self.assertTrue(found["body_dmx"].endswith("kestrel_body.dmx"))
            self.assertTrue(found["game_skeleton"].endswith("kestrel_skel.dmx"))
            self.assertEqual(found["clip_labels"], ["aim_weapon_idle"])

    def test_hero_can_be_named_and_missing_hero_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_extraction(root, "kestrel")
            self.assertEqual(port_target.hero_root(root, "kestrel").name, "kestrel")
            with self.assertRaises(port_target.PortTargetError):
                port_target.hero_root(root, "nobody")

    def test_body_prefers_the_hero_body_over_a_lod(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = make_extraction(root, "kestrel")
            self.assertEqual(port_target.body_dmx(folder).name, "kestrel_body.dmx")


class PortGateTests(unittest.TestCase):
    def _port(self, tmp: Path, **overrides) -> Path:
        pak = tmp / "port.vpk"
        pak.write_bytes(b"pak-bytes")
        receipt = tmp / "receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "errors": [],
                    "checks": {
                        "updated": 2,
                        "moving": ["item_stand_idle"],
                        "hero_tail_bones": ["tail_0", "tail_1", "tail_2", "tail_3", "tail_4"],
                    },
                }
            ),
            encoding="utf-8",
        )
        fields = {
            "addon": "kestrel_tail",
            "pak": str(pak),
            "sha256": hashlib.sha256(pak.read_bytes()).hexdigest(),
            "bytes": pak.stat().st_size,
            "receipt": str(receipt),
        }
        fields.update(overrides)
        return port_gate.write_pin(tmp / "pin.json", **fields)

    def test_a_matching_pin_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = port_gate.gate_pin(self._port(Path(tmp)), skip_installed=True)
            self.assertTrue(report["pass"], report)

    def test_tampered_pak_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            pin = self._port(Path(tmp))
            (Path(tmp) / "port.vpk").write_bytes(b"different")
            report = port_gate.gate_pin(pin, skip_installed=True)
            self.assertFalse(report["pass"])

    def test_a_port_that_moved_no_tail_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            pin = self._port(Path(tmp))
            receipt = json.loads((Path(tmp) / "receipt.json").read_text(encoding="utf-8"))
            receipt["checks"]["moving"] = []
            receipt["checks"]["updated"] = 0
            (Path(tmp) / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
            report = port_gate.gate_pin(pin, skip_installed=True)
            self.assertFalse(report["pass"])

    def test_candidate_pins_never_make_the_gate_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            pin = self._port(Path(tmp), status="candidate", sha256="not-the-bytes")
            report = port_gate.gate_pin(pin, skip_installed=True)
            self.assertTrue(report["pass"])
            self.assertEqual(report["status"], "candidate")


if __name__ == "__main__":
    unittest.main()
