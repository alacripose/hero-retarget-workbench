"""The UI pass's own refusals: one home per action, clean copy, a real picker.

`tools/ui_parity.py` reads the addon's panels and page map. These tests keep the
result from drifting back: an action drawn on two pages fails, a page with no
panel fails, and a stop-slop hit in a user-facing string fails.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _heropick():
    """Load the picker without Blender: its only import is the roster module."""
    import types

    package = types.ModuleType("hero_retarget_workbench")
    package.__path__ = [str(ROOT / "blender" / "hero_retarget_workbench")]
    sys.modules["hero_retarget_workbench"] = package
    roster = types.ModuleType("hero_retarget_workbench.properties")
    roster.HERO_ITEMS = []
    roster.ROSTER_SERIAL = 0
    sys.modules["hero_retarget_workbench.properties"] = roster
    return importlib.import_module("hero_retarget_workbench.heropick")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PARITY = _load("ui_parity")
PROSE = _load("ui_prose")


class PageParityTests(unittest.TestCase):
    def setUp(self):
        self.report = PARITY.survey()

    def test_no_action_is_drawn_on_two_pages(self):
        self.assertEqual(self.report["duplicates"], {})

    def test_every_page_owns_a_panel(self):
        self.assertEqual(self.report["empty_pages"], [])

    def test_every_drawn_action_exists(self):
        self.assertEqual(self.report["unknown_actions"], [])

    def test_every_declared_action_has_a_button(self):
        self.assertEqual(self.report["undrawn_actions"], [])

    def test_staging_and_compiling_live_on_release(self):
        self.assertNotIn("HANDOFF", self.report["pages"])
        actions = self.report["actions"]["RELEASE"]
        self.assertIn("dmf.compile", actions)
        self.assertIn("dmf.export_stage", actions)
        self.assertIn("dmf.pack_vpk", actions)

    def test_the_hero_picker_is_a_filtered_list(self):
        lists = (ROOT / "blender" / "hero_retarget_workbench" / "ui_lists.py").read_text(encoding="utf-8")
        self.assertIn("class DMF_UL_heroes(UIList):", lists)
        self.assertIn("    DMF_UL_heroes,\n", lists)
        heropick = _heropick()
        self.assertEqual(heropick.kind_of("Hideout · Ghost Doorman", "models/hideout/ghost.vmdl_c"), "HIDEOUT")
        self.assertEqual(heropick.kind_of("Haze", "models/heroes_staging/haze/haze.vmdl_c"), "HERO")
        self.assertEqual(heropick.kind_of("Shiv", "models/heroes_staging/shiv/shiv.vmdl_c"), "HERO")
        self.assertEqual(heropick.kind_of("Trooper", "models/npc/trooper.vmdl_c"), "OTHER")


class CopyTests(unittest.TestCase):
    def test_user_facing_strings_pass_the_writing_rules(self):
        hits = PROSE.scan(sorted((ROOT / "blender" / "hero_retarget_workbench").glob("*.py")))
        self.assertEqual([], hits, "\n".join(f"{hit['file']}:{hit['line']} {hit['rule']}" for hit in hits))


if __name__ == "__main__":
    unittest.main()
