from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from forge.migrate import (
    MigrationError,
    migrate_trees,
    model_file_diff,
    model_node_diff,
    resolve_old_model,
    update_from_package,
)
from forge.modeldoc import sections
from forge.oldmods import HashMatch
from forge.paths import Environment


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

    def test_arbitrary_old_cloth_section_is_discovered_and_transplanted(self):
        (self.old / "models/test/hero.vmdl").write_text(
            document(block("ClothRig", SOFTBODY)),
            encoding="utf-8",
        )
        result = migrate_trees(**self.request())
        self.assertIn("ClothRig", result.sections)
        self.assertEqual(result.sections["ClothRig"]["action"], "inserted")
        self.assertIn("_class = \"ClothChain\"", result.vmdl.read_text(encoding="utf-8"))

    def test_explicit_old_vmdl_selects_among_multiple_vmdls(self):
        alternate = self.old / "models/test/alternate.vmdl"
        alternate.write_text(
            document(block("Softbody", SOFTBODY)),
            encoding="utf-8",
        )
        output = self.root / "explicit-out"
        result = update_from_package(
            None,
            self.old,
            output,
            "explicit_hero",
            new_extraction=self.new,
            new_vmdl=self.new / "models/test/hero.vmdl",
            old_vmdl=alternate,
        )
        self.assertEqual(result.old_vmdl, alternate.resolve())
        self.assertIn("_class = \"ClothChain\"", result.vmdl.read_text(encoding="utf-8"))

    def test_output_vmdl_contains_the_old_sections_and_new_sections(self):
        result = migrate_trees(**self.request())
        names = list(sections(result.vmdl.read_text(encoding="utf-8")))
        self.assertIn("Softbody", names)
        self.assertIn("PhysicsJointList", names)
        self.assertIn("RenderMeshList", names)
        self.assertNotIn("ClothChain", names)  # it is a nested class, not a top-level section

    def test_analysis_names_selectable_nodes_and_differing_files(self):
        old_text = (self.old / "models/test/hero.vmdl").read_text(encoding="utf-8")
        new_text = (self.new / "models/test/hero.vmdl").read_text(encoding="utf-8")

        nodes = {row["name"]: row for row in model_node_diff(old_text, new_text)}
        self.assertTrue(nodes["Softbody"]["selected"])
        self.assertTrue(nodes["PhysicsJointList"]["selected"])
        self.assertFalse(nodes["RenderMeshList"]["selected"])
        self.assertTrue(nodes["Softbody"]["changed"])

        files = {row["path"]: row for row in model_file_diff(self.old, old_text, self.new, new_text)}
        self.assertEqual(files[RENDER]["state"], "changed")

    def test_compiled_only_model_resolves_through_an_installed_copy(self):
        old = self.root / "compiled-old"
        compiled = old / "models/test/hero.vmdl_c"
        compiled.parent.mkdir(parents=True)
        compiled.write_bytes(b"compiled model bytes")
        container = self.root / "CSDK10" / "game/citadel/pak01_dir.vpk"
        container.parent.mkdir(parents=True)
        container.write_bytes(b"pak")
        gameinfo = container.parent / "gameinfo.gi"
        gameinfo.write_text("gameinfo", encoding="utf-8")
        destination = self.root / "resolved"

        def fake_run(command, **_kwargs):
            output = Path(command[command.index("-o") + 1])
            vmdl = output / "models/test/hero.vmdl"
            vmdl.parent.mkdir(parents=True, exist_ok=True)
            vmdl.write_text("[source]", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        match = HashMatch(
            relative="models/test/hero.vmdl_c",
            install=str(container.parent.parent.parent),
            label="CSDK10",
            build="4391",
            kind="vpk",
            container=str(container),
            entry="models/test/hero.vmdl_c",
            size=len(b"compiled model bytes"),
            crc32=0,
            gameinfo=str(gameinfo),
        )
        with mock.patch("forge.migrate.subprocess.run", side_effect=fake_run) as run:
            path, source = resolve_old_model(
                Environment(s2v=Path("s2v.exe")),
                old,
                preferred="models/test/hero.vmdl_c",
                matches=[match],
                destination=destination,
            )

        self.assertEqual(path.resolve(), (destination / "models/test/hero.vmdl").resolve())
        self.assertEqual(source["kind"], "compiled")
        self.assertTrue(source["matched"])
        command = run.call_args.args[0]
        self.assertIn(str(container), command)
        self.assertIn("-f", command)

    def test_compiled_only_model_falls_back_to_the_mod_file(self):
        old = self.root / "compiled-only"
        compiled = old / "models/test/hero.vmdl_c"
        compiled.parent.mkdir(parents=True)
        compiled.write_bytes(b"compiled model bytes")
        destination = self.root / "fallback"

        seen = {}

        def fake_run(command, **_kwargs):
            output = Path(command[command.index("-o") + 1])
            staged_root = Path(command[command.index("-i") + 1])
            staged = staged_root / "models/test/hero.vmdl_c"
            seen["staged"] = staged
            seen["staged_exists"] = staged.is_file()
            vmdl = output / "models/test/hero.vmdl"
            vmdl.parent.mkdir(parents=True, exist_ok=True)
            vmdl.write_text("[source]", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch("forge.migrate.subprocess.run", side_effect=fake_run) as run:
            path, source = resolve_old_model(
                Environment(s2v=Path("s2v.exe")),
                old,
                preferred="models/test/hero.vmdl_c",
                destination=destination,
            )

        self.assertFalse(source["matched"])
        self.assertEqual(path.resolve(), (destination / "models/test/hero.vmdl").resolve())
        self.assertEqual(Path(source["assets_root"]), destination)
        command = run.call_args.args[0]
        self.assertIn("--recursive", command)
        self.assertEqual(seen["staged"], Path(command[command.index("-i") + 1]) / "models/test/hero.vmdl_c")
        self.assertTrue(seen["staged_exists"])

    def test_extracted_vpk_source_satisfies_an_explicit_compiled_path(self):
        old = self.root / "extracted-vpk"
        source = old / "models/test/hero.vmdl"
        source.parent.mkdir(parents=True)
        source.write_text(document(), encoding="utf-8")

        path, info = resolve_old_model(
            Environment(s2v=Path("s2v.exe")),
            old,
            preferred="models/test/hero.vmdl_c",
        )

        self.assertEqual(path.resolve(), source.resolve())
        self.assertEqual(info["kind"], "source")

    def test_compiled_only_package_updates_without_a_source_vmdl(self):
        old = self.root / "compiled-package"
        compiled = old / "models/test/hero.vmdl_c"
        compiled.parent.mkdir(parents=True)
        compiled.write_bytes(b"compiled model bytes")

        def fake_run(command, **_kwargs):
            output = Path(command[command.index("-o") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / "hero.vmdl").write_text(
                document(block("Softbody", SOFTBODY)),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch("forge.migrate.subprocess.run", side_effect=fake_run):
            result = update_from_package(
                Environment(s2v=Path("s2v.exe")),
                old,
                self.root / "compiled-out",
                "compiled_updated",
                new_extraction=self.new,
                new_vmdl=self.new / "models/test/hero.vmdl",
                preserve_model="live",
                force=True,
            )

        self.assertIn("Softbody", result.sections)
        self.assertIn("_class = \"ClothChain\"", result.vmdl.read_text(encoding="utf-8"))
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest["old_source"]["kind"], "compiled")

    def test_compiled_assets_are_read_from_the_decompile_root(self):
        old = self.root / "compiled-assets"
        compiled = old / "models/test/hero.vmdl_c"
        compiled.parent.mkdir(parents=True)
        compiled.write_bytes(b"compiled model bytes")

        def fake_run(command, **_kwargs):
            output = Path(command[command.index("-o") + 1])
            vmdl = output / "models/test/hero.vmdl"
            vmdl.parent.mkdir(parents=True, exist_ok=True)
            vmdl.write_text(
                document(block("Softbody", SOFTBODY)),
                encoding="utf-8",
            )
            (output / "models/test/hero_body.dmx").write_bytes(b"old custom dmx")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch("forge.migrate.subprocess.run", side_effect=fake_run):
            result = update_from_package(
                Environment(s2v=Path("s2v.exe")),
                old,
                self.root / "compiled-assets-out",
                "compiled_assets",
                new_extraction=self.new,
                new_vmdl=self.new / "models/test/hero.vmdl",
                force=True,
            )

        self.assertTrue(result.preserved_model)
        self.assertEqual(
            (result.root / "models/test/hero_body.dmx").read_bytes(),
            b"old custom dmx",
        )
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        self.assertTrue(manifest["old_assets"])


if __name__ == "__main__":
    unittest.main()
