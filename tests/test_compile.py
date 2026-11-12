import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge.compile import compile_stage
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

    def fake_compile(self, env, command, log_path, timeout):
        input_relative = Path(command[command.index("-i") + 1])
        build_name = input_relative.parts[1]
        build_game = env.csdk_root / "game" / "citadel_addons" / build_name
        for relative, payload in (
            ("models/heroes/haze/haze.vmdl_c", b"vmdl_c"),
            ("models/heroes/haze/materials/haze.vmat_c", b"vmat_c"),
            ("models/heroes/haze/materials/haze.vtex_c", b"vtex_c"),
            ("tools_asset_info.bin", b"cache"),
        ):
            path = build_game / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("$ fake compile\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "compiled", "")

    def test_compile_uses_a_disposable_mirror_and_copies_only_compiled_files(self):
        with patch("forge.compile._run", side_effect=self.fake_compile):
            result = compile_stage(self.env, self.stage, "haze", log_path=self.log)

        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.content_addon)
        self.assertIsNone(result.build_addon)
        self.assertEqual(
            result.output,
            self.stage / "compiled" / "haze" / "models" / "heroes" / "haze" / "haze.vmdl_c",
        )
        self.assertEqual(
            {path.relative_to(self.stage / "compiled" / "haze").as_posix() for path in result.compiled_files},
            {
                "models/heroes/haze/haze.vmdl_c",
                "models/heroes/haze/materials/haze.vmat_c",
                "models/heroes/haze/materials/haze.vtex_c",
            },
        )
        self.assertFalse(
            (self.stage / "compiled" / "haze" / "tools_asset_info.bin").exists()
        )
        self.assertEqual(list(self.content_root.iterdir()), [])
        self.assertEqual(list(self.game_root.iterdir()), [])
        self.assertTrue(result.output.is_file())

    def test_failed_compile_removes_the_mirror_and_keeps_the_old_output(self):
        old = self.stage / "compiled" / "haze" / "models" / "heroes" / "haze" / "haze.vmdl_c"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"old")

        def failed(env, command, log_path, timeout):
            log_path.write_text("failed", encoding="utf-8")
            return subprocess.CompletedProcess(command, 1, "", "failure")

        with patch("forge.compile._run", side_effect=failed):
            result = compile_stage(self.env, self.stage, "haze", log_path=self.log)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.compiled_files, [])
        self.assertEqual(old.read_bytes(), b"old")
        self.assertEqual(list(self.content_root.iterdir()), [])
        self.assertEqual(list(self.game_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
