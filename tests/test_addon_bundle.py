import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_addon import addon_version, build_addon  # noqa: E402


class AddonBundleTests(unittest.TestCase):
    def test_archive_carries_addon_and_forge_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = build_addon(Path(temporary))
            self.assertTrue(result.path.is_file())
            self.assertEqual(result.version, addon_version())
            with zipfile.ZipFile(result.path) as archive:
                names = set(archive.namelist())
                self.assertIn("hero_retarget_workbench/__init__.py", names)
                self.assertIn("hero_retarget_workbench/core.py", names)
                self.assertIn("hero_retarget_workbench/forge/stage.py", names)
                self.assertIn("hero_retarget_workbench/forge/proof.py", names)
                self.assertIn("hero_retarget_workbench/forge/weights.py", names)
                self.assertIn("hero_retarget_workbench/proofing.py", names)
                self.assertIn("hero_retarget_workbench/workbench.py", names)
                self.assertIn("hero_retarget_workbench/_vendor/blake3/__init__.py", names)
                self.assertTrue(any(name.endswith((".pyd", ".so", ".dylib")) and "/blake3/" in name for name in names))
                self.assertFalse(any("__pycache__" in name for name in names))
                core = archive.read("hero_retarget_workbench/core.py").decode("utf-8")
                self.assertIn("bundled_core", core)
                self.assertIn("user_resource", core)

    def test_archive_name_uses_bl_info_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = build_addon(Path(temporary))
            self.assertEqual(result.path.name, f"hero_retarget_workbench-{addon_version()}.zip")


if __name__ == "__main__":
    unittest.main()
