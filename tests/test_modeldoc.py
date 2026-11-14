from __future__ import annotations

import unittest

from forge.modeldoc import (
    ModeldocError,
    add_render_mesh_file,
    body_groups,
    cloth_physics_sections,
    ensure_bodygroup,
    merge,
    render_mesh_files,
    sections,
)


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


RENDER_BODY = """\t\t\t{
\t\t\t\t_class = "RenderMeshList"
\t\t\t\tchildren = 
\t\t\t\t[
\t\t\t\t\t{
\t\t\t\t\t\t_class = "RenderMeshFile"
\t\t\t\t\t\tname = "body"
\t\t\t\t\t\tfilename = "models/heroes_staging/haze/haze_body.dmx"
\t\t\t\t\t},
\t\t\t\t]
\t\t\t},
"""

RENDER_BODYGROUP = """\t\t\t{
\t\t\t\t_class = "BodyGroupList"
\t\t\t\tchildren = 
\t\t\t\t[
\t\t\t\t\t{
\t\t\t\t\t\t_class = "BodyGroup"
\t\t\t\t\t\tname = "gun"
\t\t\t\t\t\tchildren = 
\t\t\t\t\t\t[
\t\t\t\t\t\t\t{
\t\t\t\t\t\t\t\t_class = "BodyGroupChoice"
\t\t\t\t\t\t\t\tname = "0_#&gun_model"
\t\t\t\t\t\t\t\tmeshes = 
\t\t\t\t\t\t\t\t[
\t\t\t\t\t\t\t\t\t"gun_model",
\t\t\t\t\t\t\t\t]
\t\t\t\t\t\t\t},
\t\t\t\t\t\t]
\t\t\t\t\t},
\t\t\t\t]
\t\t\t},
"""


def render_document(*bodygroups: str) -> str:
    return document(block("BoneMarkupList", "\t\t\t\tchildren = [  ]\n"), RENDER_BODY, *bodygroups)


class RenderMeshBodyGroupTests(unittest.TestCase):
    def test_reads_render_mesh_files(self):
        files = render_mesh_files(render_document())
        self.assertEqual([(item.name, item.filename) for item in files], [("body", "models/heroes_staging/haze/haze_body.dmx")])

    def test_adds_separate_dmx_and_creates_bodygroup(self):
        result = add_render_mesh_file(
            render_document(),
            name="hat",
            filename="models/heroes_staging/haze/haze_hat.dmx",
            bodygroup="headwear",
        )
        self.assertIn('filename = "models/heroes_staging/haze/haze_hat.dmx"', result.text)
        self.assertEqual(result.actions["RenderMeshList"], "inserted")
        self.assertEqual(result.actions["BodyGroupList"], "created")
        self.assertEqual(result.choice, "0_#&hat")
        groups = {group.name: group for group in body_groups(result.text)}
        self.assertEqual(groups["headwear"].meshes, ("hat",))
        self.assertIn("BodyGroupList", sections(result.text))
        self.assertIn("body", [item.name for item in render_mesh_files(result.text)])

    def test_adds_choice_to_an_existing_group(self):
        result = add_render_mesh_file(
            render_document(RENDER_BODYGROUP),
            name="gun_chrome",
            filename="models/heroes_staging/haze/haze_gun_chrome.dmx",
            bodygroup="gun",
        )
        self.assertEqual(result.actions["BodyGroupList"], "choice-inserted")
        groups = {group.name: group for group in body_groups(result.text)}
        self.assertEqual(sorted(groups["gun"].meshes), ["gun_chrome", "gun_model"])
        self.assertIn("1_#&gun_chrome", groups["gun"].choices)

    def test_duplicate_mesh_is_refused_and_replacement_updates_filename(self):
        text = render_document()
        with self.assertRaises(ModeldocError):
            add_render_mesh_file(text, name="body", filename="models/other/body.dmx")
        replaced = add_render_mesh_file(
            text, name="body", filename="models/new/body.dmx", replace=True
        )
        self.assertEqual(replaced.actions["RenderMeshList"], "replaced")
        self.assertEqual(render_mesh_files(replaced.text)[0].filename, "models/new/body.dmx")

    def test_bodygroup_choice_is_idempotent(self):
        text = render_document(RENDER_BODYGROUP)
        again = ensure_bodygroup(text, "gun", "gun_model")
        self.assertEqual(again.actions["BodyGroupList"], "exists")
        self.assertEqual(again.text, text)

    def test_added_sections_keep_the_document_parseable(self):
        result = add_render_mesh_file(
            render_document(RENDER_BODYGROUP),
            name="hat",
            filename="models/heroes_staging/haze/haze_hat.dmx",
            bodygroup="headwear",
        )
        parsed = sections(result.text)
        self.assertEqual(list(parsed), ["BoneMarkupList", "RenderMeshList", "BodyGroupList"])
        self.assertTrue(result.text.rstrip().endswith("}"))


if __name__ == "__main__":
    unittest.main()
