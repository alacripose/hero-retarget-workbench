"""The gate's probe lane must report PASS, FAIL and SKIP, never a silent skip."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import probe_lane


class ProbeLaneTests(unittest.TestCase):
    def test_missing_blender_is_a_skip_not_a_pass(self):
        spec = probe_lane.ProbeSpec("probe", "tools/x.py", "x.json")
        missing = probe_lane.missing_requirements(spec, blender="", extractions="", zip_path="")
        self.assertTrue(any("Blender" in item for item in missing))

    def test_extraction_placeholder_resolves_or_reports_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "shiv").mkdir()
            resolved = probe_lane.resolve_arg(
                "{extraction:shiv}", blender="blender", extractions=str(root), zip_path=""
            )
            self.assertEqual(Path(resolved), root / "shiv")
            self.assertEqual(
                probe_lane.resolve_arg(
                    "{extraction:familiar}", blender="blender", extractions=str(root), zip_path=""
                ),
                "",
            )

    def test_receipt_failures_and_skips_are_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "receipt.json"
            path.write_text(
                json.dumps({"checks": {"draws": {"pass": False}}, "failed": ["draws"]}),
                encoding="utf-8",
            )
            self.assertEqual(probe_lane.receipt_status(path).status, "fail")
            path.write_text(
                json.dumps({"checks": {"draws": {"pass": True}}, "summary": "skipped: no extraction"}),
                encoding="utf-8",
            )
            self.assertEqual(probe_lane.receipt_status(path).status, "skip")
            path.write_text(
                json.dumps({"checks": {"draws": {"pass": True}}, "summary": "6/6 checks"}),
                encoding="utf-8",
            )
            self.assertEqual(probe_lane.receipt_status(path).status, "pass")

    def test_missing_receipt_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "absent.json"
            self.assertEqual(probe_lane.receipt_status(path).status, "fail")

    def test_lane_off_is_explicitly_skipped(self):
        checks = probe_lane.run_lane(mode="off")
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].status, "skip")
        self.assertIn("--no-probes", checks[0].detail)


if __name__ == "__main__":
    unittest.main()
