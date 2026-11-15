"""Hand-picked inputs are refused.

The defect these cover: a source clip was chosen for 197 target clips by an
invented fallback, over a Tengu source set that had only 28 of 188 clips
decompiled. A choice must be recorded, scored over the whole set, and named by
the consumer.
"""
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))


class InputSelectionTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("input_selection")
        self.folder = Path(tempfile.mkdtemp(prefix="selection-test-"))

    def test_missing_receipt_is_refused(self):
        with self.assertRaises(self.module.Refused) as caught:
            self.module.require(None)
        self.assertEqual(caught.exception.code, "hand-picked-input")

    def test_receipt_without_a_rule_is_refused(self):
        path = self.folder / "bare.json"
        path.write_text(json.dumps({"candidates": 5, "chosen": ["x"]}), encoding="utf-8")
        with self.assertRaises(self.module.Refused) as caught:
            self.module.load_selection(path)
        self.assertEqual(caught.exception.code, "selection-rule-missing")

    def test_partial_candidate_set_is_refused(self):
        path = self.folder / "partial.json"
        self.module.write_selection(
            path,
            role="tail source",
            rule="max swing",
            metric="tail_swing",
            candidates=[{"clip": "a", "tail_swing": 1.0}],
            chosen="a",
        )
        with self.assertRaises(self.module.Refused) as caught:
            self.module.load_selection(path, shipped=188)
        self.assertEqual(caught.exception.code, "selection-incomplete")

    def test_recorded_complete_selection_passes(self):
        path = self.folder / "good.json"
        candidates = [{"clip": f"c{index}", "tail_swing": float(index)} for index in range(188)]
        self.module.write_selection(
            path,
            role="tail source",
            rule="max swing",
            metric="tail_swing",
            candidates=candidates,
            chosen="c187",
            extra={"pairs": 197},
        )
        payload = self.module.load_selection(path, shipped=188)
        self.assertEqual(payload["candidates"], 188)
        self.assertEqual(payload["pairs"], 197)


if __name__ == "__main__":
    unittest.main()
