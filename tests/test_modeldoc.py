from __future__ import annotations

import unittest

from forge.modeldoc import ModeldocError, cloth_physics_sections, merge, sections


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


def document(*blocks: str) -> str:
    return HEADER + "".join(blocks) + FOOTER


class ModeldocSectionTests(unittest.TestCase):
    def test_reads_every_top_level_class(self):
        text = document(
            block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"),
            block("Softbody", '\t\t\t\tchildren = [ { _class = "ClothChain" } ]\n'),
        )
        found = sections(text)
        self.assertEqual(list(found), ["BoneMarkupList", "Softbody"])
        self.assertIn('_class = "ClothChain"', found["Softbody"].text)

    def test_inserts_missing_section_with_exact_old_text(self):
        old = document(
            block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"),
            block("Softbody", '\t\t\t\tchildren = [ { _class = "ClothChain" } ]\n'),
        )
        new = document(block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"))
        result = merge(new, old, ["Softbody"])
        self.assertEqual(result.actions["Softbody"]["action"], "inserted")
        self.assertIn('_class = "ClothChain"', result.text)
        self.assertIn("Softbody", sections(result.text))
        # The old and output section bytes match; the section is not rebuilt.
        self.assertEqual(
            result.actions["Softbody"]["old_sha256"],
            result.actions["Softbody"]["output_sha256"],
        )

    def test_replaces_existing_section_and_preserves_new_neighbours(self):
        old = document(
            block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"),
            block("Softbody", '\t\t\t\tchildren = [ { _class = "ClothChain" } ]\n'),
        )
        new = document(
            block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"),
            block("Softbody", "\t\t\t\tchildren = [  ]\n"),
        )
        result = merge(new, old, ["Softbody"])
        self.assertEqual(result.actions["Softbody"]["action"], "replaced")
        self.assertIn('_class = "ClothChain"', result.text)
        self.assertEqual(list(sections(result.text)), ["BoneMarkupList", "Softbody"])

    def test_missing_old_section_is_recorded_absent(self):
        old = document(block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"))
        new = document(block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"))
        result = merge(new, old, ["Softbody"])
        self.assertEqual(result.actions["Softbody"]["action"], "absent")
        self.assertNotIn("Softbody", sections(result.text))

    def test_discovers_cloth_and_physics_by_class_marker(self):
        text = document(
            block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"),
            block("ClothRig", "\t\t\t\tchildren = [  ]\n"),
            block("PhysicsJointBall", "\t\t\t\tchildren = [  ]\n"),
        )
        self.assertEqual(cloth_physics_sections(text), ["ClothRig", "PhysicsJointBall"])

    def test_invalid_section_name_is_refused(self):
        old = document(block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"))
        with self.assertRaises(ModeldocError):
            merge(old, old, ["Softbody; rm -rf"])

    def test_duplicate_top_level_section_is_refused(self):
        text = document(
            block("Softbody", "\t\t\t\tchildren = [  ]\n"),
            block("Softbody", "\t\t\t\tchildren = [  ]\n"),
        )
        with self.assertRaises(ModeldocError):
            sections(text)


if __name__ == "__main__":
    unittest.main()
