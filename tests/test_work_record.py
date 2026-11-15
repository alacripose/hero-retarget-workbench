"""The refusals that keep work reproducible.

`ephemeral-path` exists because a working port command was run without being
recorded and a temp directory is not a place a project can build on.  These tests
prove the refusal fires and that the recorder writes the full command.
"""
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))


class WorkRecordTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("work_record")
        self._ledger = self.module.LEDGER
        self._temp = tempfile.mkdtemp(prefix="work-record-test-")
        self.module.LEDGER = Path(self._temp) / "ledger.jsonl"

    def tearDown(self):
        self.module.LEDGER = self._ledger

    def test_temp_output_is_refused(self):
        target = Path(tempfile.gettempdir()) / "haze-release.vpk"
        with self.assertRaises(self.module.WorkRefused) as caught:
            self.module.refuse_ephemeral_paths([target])
        self.assertEqual(caught.exception.code, "ephemeral-path")

    def test_repository_output_is_allowed(self):
        self.module.refuse_ephemeral_paths([REPO / "artifacts" / "haze-tail" / "ok.vpk"])

    def test_finish_records_the_full_command_and_outputs(self):
        out = REPO / "artifacts" / "haze-tail" / "recorded.vpk"
        row = self.module.finish("tail_release_pack", [out], "PACK recorded", "pass")
        self.assertEqual(row["tool"], "tail_release_pack")
        self.assertIn(str(out), row["artifacts"])
        stored = json.loads(self.module.LEDGER.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(stored["command"], row["command"])
        self.assertTrue(stored["command"])

    def test_require_recorded_refuses_an_unrecorded_artifact(self):
        self.module.finish("tail_release_pack", [REPO / "artifacts" / "a.vpk"], "one", "pass")
        with self.assertRaises(self.module.WorkRefused) as caught:
            self.module.require_recorded("tail_release_pack", [REPO / "artifacts" / "b.vpk"])
        self.assertEqual(caught.exception.code, "work-unrecorded")

    def test_require_recorded_accepts_a_recorded_artifact(self):
        out = REPO / "artifacts" / "haze-tail" / "recorded-2.vpk"
        self.module.finish("tail_release_pack", [out], "two", "pass")
        self.module.require_recorded("tail_release_pack", [out])


if __name__ == "__main__":
    unittest.main()
