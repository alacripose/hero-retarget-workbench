from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forge.migrate import MigrationError, migrate_trees
from forge.modeldoc import sections


HEADER = """<!-- modeldoc fixture -->
{
\trootNode =
\t{
\t\t_class = "RootNode"
\t\tchildren =
\t\t[
"""

FOOTER = """\t\t]
\t}
}
"""


def block(name: str, body: str = "") -> str:
    return (
        "\t\t\t{\n"
        f'\t\t\t\t_class = "{name}"\n'
        f"{body}"
        "\t\t\t},\n"
    )


def render_list(path: str) -> str:
    return (
        "\t\t\t\tchildren = \n"
        "\t\t\t\t[\n"
        "\t\t\t\t\t{\n"
        '\t\t\t\t\t\t_class = "RenderMeshFile"\n'
        f'\t\t\t\t\t\tfilename = "{path}"\n'
        "\t\t\t\t\t},\n"
        "\t\t\t\t]\n"
    )


RENDER = "models/test/hero_body.dmx"
SOFTBODY = (
    "\t\t\t\tchildren = \n"
    "\t\t\t\t[\n"
    "\t\t\t\t\t{\n"
    '\t\t\t\t\t\t_class = "ClothChain"\n'
    '\t\t\t\t\t\tname = "ribbon"\n'
    "\t\t\t\t\t},\n"
    "\t\t\t\t]\n"
)
PHYSICS = (
    "\t\t\t\tchildren = \n"
    "\t\t\t\t[\n"
    "\t\t\t\t\t{\n"
    '\t\t\t\t\t\t_class = "PhysicsJointConical"\n'
    '\t\t\t\t\t\tparent_body = "spine_0"\n'
    "\t\t\t\t\t},\n"
    "\t\t\t\t]\n"
)


def document(*extra: str, render: str = RENDER) -> str:
    return (
        HEADER
        + block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n")
        + block("RenderMeshList", render_list(render))
        + block("MaterialGroupList", "\t\t\t\tchildren = [  ]\n")
        + "".join(extra)
        + FOOTER
    )


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old = self.root / "old"
        self.new = self.root / "new"
        for root in (self.old, self.new):
            (root / "models/test").mkdir(parents=True)
            (root / "materials").mkdir()
            (root / "models/test/hero_body.dmx").write_bytes(
                b"old custom dmx" if root == self.old else b"new live dmx"
            )
        (self.old / "materials/body.vmat").write_bytes(b"old material")
        (self.new / "materials/body.vmat").write_bytes(b"new material")
        (self.old / "models/test/hero.vmdl").write_text(
            document(
                block("Softbody", SOFTBODY),
                block("PhysicsJointList", PHYSICS),
            ),
            encoding="utf-8",
        )
        (self.new / "models/test/hero.vmdl").write_text(document(), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def request(self, **overrides):
        values = dict(
            old_root=self.old,
            old_vmdl=self.old / "models/test/hero.vmdl",
            new_root=self.new,
            new_vmdl=self.new / "models/test/hero.vmdl",
            output=self.root / "out",
            addon_name="updated_hero",
            vmdl_relative="models/test/hero.vmdl",
        )
        values.update(overrides)
        return values

    def test_custom_model_and_old_materials_are_preserved_with_cloth(self):
        result = migrate_trees(**self.request())
        self.assertTrue(result.preserved_model)
        self.assertEqual(
            (result.root / "models/test/hero_body.dmx").read_bytes(),
            b"old custom dmx",
        )
        self.assertEqual((result.root / "materials/body.vmat").read_bytes(), b"old material")
        text = result.vmdl.read_text(encoding="utf-8")
        self.assertIn("_class = \"ClothChain\"", text)
        self.assertIn("_class = \"PhysicsJointConical\"", text)
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        self.assertTrue(manifest["vmdl_modified"])
        self.assertEqual(manifest["cloth_chains"], 1)
        self.assertEqual(manifest["material_textures"], 0)
        self.assertIn("models/test/hero_body.dmx", result.model_files)
        self.assertIn(RENDER, result.new_model_files)

    def test_live_model_policy_keeps_cloth_but_uses_live_mesh(self):
        result = migrate_trees(**self.request(preserve_model="live"))
        self.assertFalse(result.preserved_model)
        self.assertEqual(
            (result.root / "models/test/hero_body.dmx").read_bytes(),
            b"new live dmx",
        )
        self.assertIn("_class = \"ClothChain\"", result.vmdl.read_text(encoding="utf-8"))

    def test_missing_old_model_is_refused_when_old_model_is_needed(self):
        (self.old / RENDER).unlink()
        with self.assertRaises(MigrationError) as raised:
            migrate_trees(**self.request(preserve_model="old"))
        self.assertIn("old-model-missing", str(raised.exception))

    def test_live_model_policy_does_not_require_the_old_mesh(self):
        (self.old / RENDER).unlink()
        result = migrate_trees(**self.request(preserve_model="live"))
        self.assertFalse(result.preserved_model)
        self.assertEqual((result.root / RENDER).read_bytes(), b"new live dmx")

    def test_existing_output_requires_force(self):
        output = self.root / "out"
        (output / "content/citadel_addons/updated_hero").mkdir(parents=True)
        with self.assertRaises(MigrationError) as raised:
            migrate_trees(**self.request())
        self.assertIn("output-exists", str(raised.exception))

    def test_output_vmdl_contains_the_old_sections_and_new_sections(self):
        result = migrate_trees(**self.request())
        names = list(sections(result.vmdl.read_text(encoding="utf-8")))
        self.assertIn("Softbody", names)
        self.assertIn("PhysicsJointList", names)
        self.assertIn("RenderMeshList", names)
        self.assertNotIn("ClothChain", names)  # it is a nested class, not a top-level section


if __name__ == "__main__":
    unittest.main()
