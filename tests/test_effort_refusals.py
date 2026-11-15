"""The effort-caveat refusal: a budget is not a reason work stops.

The owner's rule, and the reason it is a refusal rather than a note: an agent that
writes "running low on room" into the record hands the next session a reason the
project cannot improve on.
"""
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))


class EffortRefusalTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("effort_refusals")

    def test_context_caveat_is_refused(self):
        with self.assertRaises(self.module.Refused) as caught:
            self.module.scan_text("stopped because of the context length", "row")
        self.assertEqual(caught.exception.code, "effort-caveat")

    def test_session_deferral_is_refused(self):
        with self.assertRaises(self.module.Refused) as caught:
            self.module.scan_text("the rest can be checked next session", "row")
        self.assertEqual(caught.exception.code, "effort-deferral")

    def test_measured_statement_passes(self):
        self.module.scan_text(
            "the tail mesh is declared by the body RenderMeshFile and sits in a LODGroupAll",
            "row",
        )

    def test_ledger_with_a_planted_caveat_is_refused(self):
        folder = Path(tempfile.mkdtemp(prefix="effort-refusal-test-"))
        ledger = folder / "ledger.jsonl"
        ledger.write_text(
            json.dumps({"at": "now", "observed": "I am running low on room for this"}) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(self.module.Refused):
            self.module.scan_ledger(ledger)

    def test_selftest_passes(self):
        self.assertEqual(self.module.selftest(), 0)


if __name__ == "__main__":
    unittest.main()
