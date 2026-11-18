import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from forge.compile import CompileError, _run, compile_stage, stage_content
from forge.paths import Environment


class CompileStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.csdk = self.root / "csdk"
        self.content_root = self.csdk / "content" / "citadel_addons"
        self.game_root = self.csdk / "game" / "citadel_addons"
        self.content_root.mkdir(parents=True)
        self.game_root.mkdir(parents=True)
        self.gameinfo = self.csdk / "game" / "citadel" / "gameinfo.gi"
        self.gameinfo.parent.mkdir(parents=True)
        self.gameinfo.write_text("gameinfo", encoding="utf-8")
        self.compiler = self.csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
        self.compiler.parent.mkdir(parents=True)
        self.compiler.write_bytes(b"compiler")

        self.stage = self.root / "stage"
        self.source = self.stage / "content" / "citadel_addons" / "haze"
        (self.source / "models" / "heroes" / "haze").mkdir(parents=True)
        (self.source / "models" / "heroes" / "haze" / "haze.vmdl").write_bytes(b"vmdl")
        (self.source / "models" / "heroes" / "haze" / "haze_body.dmx").write_bytes(b"dmx")
        (self.source / "stage.json").write_text(
            json.dumps({"vmdl": "models/heroes/haze/haze.vmdl"}),
            encoding="utf-8",
        )
        self.env = Environment(
            csdk_root=self.csdk,
            resourcecompiler=self.compiler,
            csdk_gameinfo=self.gameinfo,
        )
        self.log = self.root / "compile.log"

    def tearDown(self):
        self.temp.cleanup()

    def fake_compile(self, env, command, log_path, timeout, cancel=None):
        input_relative = Path(command[command.index("-i") + 1])
        addon = input_relative.parts[1]
        game_addon = env.csdk_root / "game" / "citadel_addons" / addon
        for relative, payload in (
            ("models/heroes/haze/haze.vmdl_c", b"vmdl_c"),
            ("models/heroes/haze/materials/haze.vmat_c", b"vmat_c"),
            ("models/heroes/haze/materials/haze.vtex_c", b"vtex_c"),
            ("tools_asset_info.bin", b"cache"),
        ):
            path = game_addon / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("$ fake compile\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "compiled", "")

    def test_compile_installs_the_addon_into_the_csdk(self):
        with patch("forge.compile._run", side_effect=self.fake_compile):
            result = compile_stage(self.env, self.stage, "haze", log_path=self.log)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.content_addon, self.content_root / "haze")
        self.assertTrue(
            (self.content_root / "haze" / "models" / "heroes" / "haze" / "haze.vmdl").is_file()
        )
        game_addon = self.game_root / "haze"
        self.assertEqual(result.game_addon, game_addon)
        self.assertEqual(
            result.output,
            game_addon / "models" / "heroes" / "haze" / "haze.vmdl_c",
        )
        self.assertEqual(
            {path.relative_to(game_addon).as_posix() for path in result.compiled_files},
            {
                "models/heroes/haze/haze.vmdl_c",
                "models/heroes/haze/materials/haze.vmat_c",
                "models/heroes/haze/materials/haze.vtex_c",
            },
        )
        # The compiler's own metadata stays with the addon; it is not reported
        # as a compiled resource.
        self.assertTrue((game_addon / "tools_asset_info.bin").is_file())
        self.assertTrue(result.output.is_file())

    def test_an_existing_addon_keeps_the_files_the_stage_does_not_own(self):
        keeper = self.content_root / "haze" / "models" / "heroes" / "haze" / "clip.dmx"
        keeper.parent.mkdir(parents=True)
        keeper.write_bytes(b"owner clip")

        with patch("forge.compile._run", side_effect=self.fake_compile):
            compile_stage(self.env, self.stage, "haze", log_path=self.log)

        self.assertEqual(keeper.read_bytes(), b"owner clip")
        self.assertTrue((self.content_root / "haze" / "stage.json").is_file())

    def test_failed_compile_keeps_the_addon_and_the_old_output(self):
        game_addon = self.game_root / "haze"
        old = game_addon / "models" / "heroes" / "haze" / "haze.vmdl_c"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"old")

        def failed(env, command, log_path, timeout, cancel=None):
            log_path.write_text("failed", encoding="utf-8")
            return subprocess.CompletedProcess(command, 1, "", "failure")

        with patch("forge.compile._run", side_effect=failed):
            result = compile_stage(self.env, self.stage, "haze", log_path=self.log)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.compiled_files, [])
        self.assertEqual(old.read_bytes(), b"old")
        self.assertTrue((self.content_root / "haze" / "stage.json").is_file())

    def test_cancel_terminates_the_waiting_compiler(self):
        class Cancel:
            def __init__(self):
                self.cancelled = False
                self.process = None

            def attach(self, process):
                self.process = process

            def detach(self, process):
                if self.process is process:
                    self.process = None

            def cancel(self):
                self.cancelled = True
                if self.process is not None and self.process.poll() is None:
                    self.process.terminate()

        cancel = Cancel()
        timer = threading.Timer(0.5, cancel.cancel)
        timer.start()
        try:
            with self.assertRaises(CompileError) as raised:
                _run(
                    self.env,
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    self.log,
                    30,
                    cancel=cancel,
                )
        finally:
            timer.cancel()
            timer.join(timeout=2)
        self.assertIn("compile-cancelled", str(raised.exception))
        self.assertIsNone(cancel.process)

    def test_addon_name_cannot_leave_the_addon_root(self):
        with self.assertRaises(CompileError):
            compile_stage(self.env, self.stage, "../escape", log_path=self.log)

    def test_compile_refuses_a_migrated_body_with_live_lod_slots(self):
        live_root = self.root / "live"
        live_body = live_root / "models" / "heroes" / "haze" / "haze_body.dmx"
        live_body.parent.mkdir(parents=True)
        live_body.write_bytes(b"live body")
        (live_body.parent / "haze_body_lod13.dmx").write_bytes(b"live lod")
        manifest = {
            "vmdl": "models/heroes/haze/haze.vmdl",
            "preserved_model": True,
            "new_root": str(live_root),
            "new_vmdl": "models/heroes/haze/haze.vmdl",
            "target_dmx": "models/heroes/haze/haze_body.dmx",
        }
        (self.source / "stage.json").write_text(json.dumps(manifest), encoding="utf-8")
        with patch("forge.compile._run") as run:
            with self.assertRaises(CompileError) as raised:
                compile_stage(self.env, self.stage, "haze", log_path=self.log)
        self.assertIn("compile-needs-restaged-lods", str(raised.exception))
        run.assert_not_called()

    def test_compile_compiles_target_material_sources(self):
        material = self.source / "models/heroes/haze/materials/haze.vmat"
        material.parent.mkdir(parents=True)
        material.write_text('"shader" "pbr.vfx"\n', encoding="utf-8")
        manifest = {
            "vmdl": "models/heroes/haze/haze.vmdl",
            "material_target_dir": "models/heroes/haze/materials",
        }
        (self.source / "stage.json").write_text(json.dumps(manifest), encoding="utf-8")
        with patch("forge.compile._run", side_effect=self.fake_compile) as run:
            result = compile_stage(self.env, self.stage, "haze", log_path=self.log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.material_errors, [])
        self.assertTrue(any(path.name == "haze.vmat_c" for path in result.material_files))
        self.assertEqual(run.call_count, 2)

    def test_compile_reads_the_edited_csdk_content_instead_of_copying_the_build_again(self):
        stage_content(self.env, self.stage, "haze")
        edited = self.content_root / "haze" / "models" / "heroes" / "haze" / "haze.vmdl"
        edited.write_bytes(b"owner edit")

        with patch("forge.compile._run", side_effect=self.fake_compile):
            compile_stage(self.env, self.env.csdk_root, "haze", log_path=self.log)

        self.assertEqual(edited.read_bytes(), b"owner edit")

    def test_stage_content_copies_materials_without_compiling(self):
        material = (
            self.source
            / "models"
            / "heroes"
            / "haze"
            / "materials"
            / "haze_l_arm_vmat_g_tselfillummask_2b2ebb3f.vtex_c"
        )
        material.parent.mkdir(parents=True)
        material.write_bytes(b"old material")
        keeper = self.content_root / "haze" / "notes.txt"
        keeper.parent.mkdir(parents=True)
        keeper.write_bytes(b"owner note")

        installed = stage_content(self.env, self.stage, "haze")

        self.assertEqual(installed, self.content_root / "haze")
        self.assertEqual(
            (installed / "models/heroes/haze/materials/haze_l_arm_vmat_g_tselfillummask_2b2ebb3f.vtex_c").read_bytes(),
            b"old material",
        )
        self.assertEqual(keeper.read_bytes(), b"owner note")
        self.assertFalse((self.game_root / "haze").exists())


if __name__ == "__main__":
    unittest.main()
