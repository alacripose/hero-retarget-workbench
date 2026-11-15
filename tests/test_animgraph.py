"""AnimGraph 2 clip planning: source DMX first, compiled skeleton never shipped."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from forge import animgraph


MINIMAL = """{
\tm_sourceFilename = "models/old/body.dmx"
\tm_highLODBones =
\t[
\t\t"head",
\t]
\tm_boneMaskSetDefinitions =
\t[
\t\t{
\t\t\tm_ID = "UpperBody"
\t\t\tm_primaryWeightList =
\t\t\t{
\t\t\t\tm_boneIDs = [ "hand_L" ]
\t\t\t\tm_weights = [ 1.0 ]
\t\t\t}
\t\t},
\t\t{
\t\t\tm_ID = "FullBody"
\t\t\tm_primaryWeightList =
\t\t\t{
\t\t\t\tm_boneIDs =
\t\t\t\t[
\t\t\t\t\t"pelvis",
\t\t\t\t]
\t\t\t\tm_weights =
\t\t\t\t[
\t\t\t\t\t1.0,
\t\t\t\t]
\t\t\t}
\t\t},
\t]
}
"""


class AnimGraphTests(unittest.TestCase):
    def test_documents_follow_the_clip_source_not_its_preview_name(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            hero = base / "models/heroes_staging/h/hero"
            content = base
            (hero / "clips").mkdir(parents=True)
            source = content / "models/heroes_staging/h/hero/dmx/animation/primary_idle.dmx"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"<!-- dmx -->")
            (hero / "clips/weapon_stand_idle.vnmclip").write_text(
                'm_sourceFilename = "models/heroes_staging/h/hero/dmx/animation/primary_idle.dmx"\n',
                encoding="utf-8",
            )
            (hero / "clips/weapon_stand_idle.dmx").write_bytes(b"preview")
            rows = animgraph.documents(hero, content)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].source, source)
            self.assertEqual(rows[0].preview, hero / "clips/weapon_stand_idle.dmx")

    def test_a_document_with_a_missing_source_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            hero = base / "models/heroes_staging/h/hero"
            (hero / "clips").mkdir(parents=True)
            (hero / "clips/idle.vnmclip").write_text(
                'm_sourceFilename = "models/heroes_staging/h/hero/dmx/animation/missing.dmx"\n',
                encoding="utf-8",
            )
            self.assertEqual(animgraph.documents(hero, base), [])

    def test_prepare_skeleton_points_at_tail_dmx_and_widens_pelvis_masks(self):
        result = animgraph.prepare_skeleton(
            MINIMAL,
            "models/heroes_staging/h/hero/dmx/mesh/body_tailbones.dmx",
            ["tail_0", "tail_1", "tail_end"],
        )
        self.assertIn('m_sourceFilename = "models/heroes_staging/h/hero/dmx/mesh/body_tailbones.dmx"', result)
        upper, full = result.split('m_ID = "UpperBody"', 1)[1].split('m_ID = "FullBody"', 1)
        self.assertNotIn("tail_0", upper)
        self.assertEqual(full.count('"tail_0"'), 1)
        self.assertEqual(full.count("1.0,"), 4)

    def test_compiled_outputs_keep_the_document_relative_path(self):
        with tempfile.TemporaryDirectory() as folder:
            content = Path(folder) / "content/citadel_addons/mod"
            game = Path(folder) / "game/citadel_addons/mod"
            document = content / "models/h/clips/idle.vnmclip"
            row = animgraph.ClipDoc("idle", document, "", document, None)
            self.assertEqual(
                animgraph.compiled_outputs(game, content, [row]),
                [game / "models/h/clips/idle.vnmclip_c"],
            )


if __name__ == "__main__":
    unittest.main()
