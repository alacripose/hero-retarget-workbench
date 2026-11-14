from __future__ import annotations

import unittest

from forge.live import choose_body, hero_vmdl_path, looks_like_body, parse_hero_roster


class HeroRosterTests(unittest.TestCase):
    def test_reads_every_top_level_hero_and_keeps_wip_paths(self):
        text = """
{
\thero_base = 
\t{
\t\t_not_pickable = 2
\t\tm_strModelName = resource_name:"models/heroes_wip/gen_man/gen_man.vmdl"
\t}
\thero_atlas = 
\t{
\t\tm_strModelName = resource_name:"models/heroes_wip/abrams/abrams.vmdl"
\t\tm_strHeroSearchName = "#hero_abrams_search"
\t\tm_strLogoImageEnglish = panorama:"file://{images}/heroes/hero_names/abrams.svg"
\t}
\thero_hornet = 
\t{
\t\tm_strModelName = resource_name:"models/heroes_staging/hornet_v3/hornet.vmdl"
\t\tm_strHeroSearchName = "#hero_hornet_search"
\t}
\thero_nano = 
\t{
\t\tm_strModelName = resource_name:"models/heroes_staging/nano/nano_v2/nano.vmdl"
\t}
\thero_kali = 
\t{
\t\tm_bDisabled = true
\t\tm_strModelName = resource_name:"models/heroes_wip/gen_man/gen_man.vmdl"
\t}
}
"""
        heroes = parse_hero_roster(text)
        self.assertEqual([hero.slug for hero in heroes], ["atlas", "kali", "hornet", "nano"])
        by_slug = {hero.slug: hero for hero in heroes}
        self.assertEqual(by_slug["atlas"].title, "Abrams")
        self.assertEqual(by_slug["atlas"].model_path, "models/heroes_wip/abrams/abrams.vmdl_c")
        self.assertEqual(by_slug["nano"].model_path, "models/heroes_staging/nano/nano_v2/nano.vmdl_c")
        self.assertEqual(by_slug["nano"].title, "Nano")
        self.assertNotIn("base", by_slug)

    def test_compiled_path_maps_to_the_vmdl_s2v_emits(self):
        self.assertEqual(
            hero_vmdl_path("models/heroes_staging/hornet_v3/hornet.vmdl_c"),
            "models/heroes_staging/hornet_v3/hornet.vmdl",
        )
        self.assertEqual(
            hero_vmdl_path("models/heroes_wip/abrams/abrams.vmdl_c"),
            "models/heroes_wip/abrams/abrams.vmdl",
        )

    def test_numbered_body_variants_are_bodies_and_heads_are_not(self):
        self.assertTrue(looks_like_body("familiar_wip_8inf_body8.dmx"))
        self.assertTrue(looks_like_body("hero_body_lod0.dmx"))
        self.assertTrue(looks_like_body("body.dmx"))
        self.assertFalse(looks_like_body("familiar_wip_head5.dmx"))
        self.assertFalse(looks_like_body("shiv_jacket4.dmx"))

    def test_a_larger_head_never_wins_over_the_body(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            head = root / "familiar_wip_head5.dmx"
            body = root / "familiar_wip_8inf_body8.dmx"
            head.write_bytes(b"x" * 900)
            body.write_bytes(b"x" * 100)
            self.assertEqual(choose_body([head, body]).name, body.name)

    def test_a_plain_part_folder_can_still_choose_a_body_by_name(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            head = root / "hero_head.dmx"
            body = root / "hero_body.dmx"
            head.write_bytes(b"x" * 900)
            body.write_bytes(b"x" * 100)
            self.assertEqual(choose_body([head, body]).name, body.name)


if __name__ == "__main__":
    unittest.main()
