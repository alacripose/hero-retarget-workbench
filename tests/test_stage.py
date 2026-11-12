import json
import tempfile
import unittest
from pathlib import Path

from forge.stage import (
    MaterialCopy,
    StageError,
    StageRequest,
    material_files,
    stage,
    target_lod_relatives,
    verify,
)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.extraction = self.root / "extraction"
        self.extraction.mkdir()
        (self.extraction / "haze.vmdl").write_bytes(b"OPAQUE-VMDL-MARKER\n\x00\xff")
        (self.extraction / "haze_body.dmx").write_bytes(b"target dmx")
        (self.extraction / "materials").mkdir()
        (self.extraction / "materials" / "haze_body.vmat").write_bytes(b"pbr.vfx = true\n")
        (self.extraction / "materials" / "haze_body_color.png").write_bytes(b"PNG")
        (self.extraction / "materials" / "notes.txt").write_text("not a material", encoding="utf-8")
        (self.extraction / "materials" / "meta.json").write_text("{}", encoding="utf-8")
        (self.extraction / "clips").mkdir()
        (self.extraction / "clips" / "idle.dmx").write_bytes(b"animation dmx")
        (self.extraction / "s2v-extract.log").write_text("log", encoding="utf-8")
        self.custom = self.root / "custom.dmx"
        self.custom.write_bytes(b"custom dmx")

    def tearDown(self):
        self.temp.cleanup()

    def request(self, **overrides):
        values = dict(
            extraction_root=self.extraction,
            vmdl=self.extraction / "haze.vmdl",
            target_dmx=self.extraction / "haze_body.dmx",
            custom_dmx=self.custom,
            target_dmx_relative="models/heroes_staging/haze/haze_body.dmx",
            vmdl_relative="models/heroes_staging/haze/haze.vmdl",
            addon_name="haze_port",
            destination=self.root / "out",
        )
        values.update(overrides)
        return StageRequest(**values)

    def test_vmdl_is_unchanged_and_materials_are_copied(self):
        result = stage(self.request())
        verify(result)
        self.assertEqual(result.vmdl.read_bytes(), (self.extraction / "haze.vmdl").read_bytes())
        self.assertTrue((result.root / "materials/haze_body.vmat").is_file())
        self.assertTrue((result.root / "clips/idle.dmx").is_file())
        self.assertFalse((result.root / "s2v-extract.log").exists())
        manifest = json.loads(result.manifest.read_text())
        self.assertFalse(manifest["vmdl_modified"])
        self.assertEqual(manifest["material_policy"], "copied-verbatim")
        self.assertGreater(manifest["extraction_files"], 0)
        self.assertEqual(len(manifest["vmdl_blake3"]), 64)
        self.assertEqual(len(manifest["custom_dmx_blake3"]), 64)
        self.assertEqual(result.vmdl_blake3, manifest["vmdl_blake3"])
        self.assertEqual(result.custom_blake3, manifest["custom_dmx_blake3"])

    def test_custom_dmx_is_written_at_the_target_path(self):
        result = stage(self.request())
        self.assertEqual(result.custom_dmx.read_bytes(), b"custom dmx")
        self.assertEqual(result.custom_dmx.relative_to(result.root).as_posix(), "models/heroes_staging/haze/haze_body.dmx")

    def test_vmdl_extension_is_required(self):
        with self.assertRaises(StageError):
            stage(self.request(vmdl=self.custom))

    def test_path_traversal_is_refused(self):
        with self.assertRaises(StageError):
            stage(self.request(target_dmx_relative="../escape.dmx"))

    def test_explicit_material_list_is_honored(self):
        material = self.extraction / "materials" / "haze_body.vmat"
        result = stage(
            self.request(
                materials=[MaterialCopy(material, "models/heroes_staging/haze/materials/haze_body.vmat")]
            )
        )
        self.assertEqual(result.material_count, 1)
        copied = result.root / "models/heroes_staging/haze/materials/haze_body.vmat"
        self.assertTrue(copied.is_file())
        self.assertEqual(copied.read_bytes(), b"pbr.vfx = true\n")

    def test_material_inventory_excludes_models_and_clips(self):
        inventory = material_files(self.extraction)
        names = {copy.relative for copy in inventory}
        self.assertIn("materials/haze_body.vmat", names)
        self.assertIn("materials/haze_body_color.png", names)
        self.assertNotIn("haze_body.dmx", names)
        self.assertNotIn("haze.vmdl", names)
        self.assertNotIn("clips/idle.dmx", names)
        self.assertNotIn("materials/notes.txt", names)
        self.assertNotIn("materials/meta.json", names)

    def test_material_counts_distinguish_vmat_and_textures(self):
        result = stage(
            self.request(
                include_extraction=False,
                materials=[
                    MaterialCopy(
                        self.extraction / "materials" / "haze_body.vmat",
                        "materials/haze_body.vmat",
                    ),
                    MaterialCopy(
                        self.extraction / "materials" / "haze_body_color.png",
                        "materials/haze_body_color.png",
                    ),
                ],
            )
        )
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        self.assertEqual(result.material_count, 2)
        self.assertEqual(result.material_texture_count, 1)
        self.assertEqual(manifest["materials"], 2)
        self.assertEqual(manifest["material_textures"], 1)
        self.assertTrue((result.root / "materials/haze_body_color.png").is_file())
        self.assertFalse((result.root / "materials/notes.txt").exists())
        self.assertFalse((result.root / "materials/meta.json").exists())

    def test_material_copy_cannot_overwrite_the_replacement_dmx(self):
        result = stage(
            self.request(
                materials=[
                    MaterialCopy(
                        self.extraction / "haze_body.dmx",
                        "models/heroes_staging/haze/haze_body.dmx",
                    )
                ]
            )
        )
        self.assertEqual(result.custom_dmx.read_bytes(), b"custom dmx")
        self.assertEqual(result.material_count, 0)

    def test_flat_extraction_target_does_not_overwrite_custom(self):
        flat = self.root / "flat"
        flat.mkdir()
        (flat / "haze.vmdl").write_bytes(b"OPAQUE-VMDL-MARKER\n\x00\xff")
        target = flat / "haze_body.dmx"
        target.write_bytes(b"flat target")
        result = stage(
            self.request(
                extraction_root=flat,
                vmdl=flat / "haze.vmdl",
                target_dmx=target,
                target_dmx_relative="models/heroes_staging/haze/haze_body.dmx",
            )
        )
        self.assertEqual(result.custom_dmx.read_bytes(), b"custom dmx")
        self.assertFalse((result.root / "haze_body.dmx").exists())

    def _hero_lods(self):
        folder = self.extraction / "models" / "heroes_staging" / "haze"
        folder.mkdir(parents=True, exist_ok=True)
        for index in (13, 26, 39):
            (folder / f"haze_body_lod{index}.dmx").write_bytes(
                f"hero lod {index}".encode()
            )
        return [
            "models/heroes_staging/haze/haze_body_lod13.dmx",
            "models/heroes_staging/haze/haze_body_lod26.dmx",
            "models/heroes_staging/haze/haze_body_lod39.dmx",
        ]

    def _custom_lods(self, count=3):
        paths = []
        for index in range(1, count + 1):
            path = self.root / f"custom_lod{index}.dmx"
            path.write_bytes(f"custom lod {index}".encode())
            paths.append(path)
        return paths

    def test_generated_lods_replace_the_hero_lod_slots(self):
        relatives = self._hero_lods()
        custom_lods = self._custom_lods()
        result = stage(self.request(custom_lods=custom_lods))
        verify(result)
        self.assertEqual(len(result.custom_lods), 3)
        for index, relative in enumerate(relatives, 1):
            staged = result.root / relative
            self.assertEqual(staged.read_bytes(), f"custom lod {index}".encode())
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["lods"]), 3)
        self.assertEqual(manifest["lods"][0]["relative"], relatives[0])
        self.assertEqual(len(result.custom_lod_sha256), 3)
        self.assertEqual(len(manifest["lods"][0]["blake3"]), 64)
        self.assertEqual(result.custom_lod_blake3[0], manifest["lods"][0]["blake3"])

    def test_lod_discovery_sorts_the_hero_suffixes_numerically(self):
        relatives = self._hero_lods()
        self.assertEqual(
            target_lod_relatives(self.extraction, "models/heroes_staging/haze/haze_body.dmx"),
            relatives,
        )

    def test_lod_count_mismatch_is_refused_instead_of_leaving_hero_lods(self):
        self._hero_lods()
        with self.assertRaises(StageError) as raised:
            stage(self.request(custom_lods=self._custom_lods(count=2)))
        self.assertIn("lod-count-mismatch", str(raised.exception))

    def test_lods_without_hero_slots_use_canonical_paths(self):
        result = stage(self.request(custom_lods=self._custom_lods(count=2)))
        self.assertEqual(
            [path.relative_to(result.root).as_posix() for path in result.custom_lods],
            [
                "models/heroes_staging/haze/haze_body_lod1.dmx",
                "models/heroes_staging/haze/haze_body_lod2.dmx",
            ],
        )
        self.assertEqual(
            result.custom_lods[0].read_bytes(),
            b"custom lod 1",
        )

    def test_custom_materials_overlay_hero_material_paths(self):
        custom_root = self.root / "custom-materials"
        relative = "materials/haze_body.vmat"
        source = custom_root / relative
        source.parent.mkdir(parents=True)
        source.write_bytes(b'"shader" "pbr.vfx"\n"F_USE_NPR_LIGHTING" "1"\n')
        result = stage(
            self.request(
                custom_materials=[MaterialCopy(source, relative)]
            )
        )
        copied = result.root / relative
        self.assertEqual(copied.read_bytes(), source.read_bytes())
        self.assertNotEqual(copied.read_bytes(), b"pbr.vfx = true\n")
        self.assertEqual(result.custom_material_count, 1)
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest["custom_materials"], 1)
        self.assertEqual(manifest["custom_material_policy"], "overlay-verbatim")


if __name__ == "__main__":
    unittest.main()
