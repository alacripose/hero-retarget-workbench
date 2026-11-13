from __future__ import annotations

import unittest

from forge import stageflow


def state(**answered):
    """Every step answered unless the test says otherwise."""
    base = {step.key: True for step in stageflow.STEPS}
    base.update(answered)
    return base


class NextStepTest(unittest.TestCase):
    def test_fresh_scene_asks_for_the_folders(self):
        self.assertEqual(stageflow.next_step({}).key, "setup")

    def test_order_follows_the_workflow(self):
        self.assertEqual(stageflow.next_step(state(build=False)).key, "build")
        self.assertEqual(stageflow.next_step(state(extract=False)).key, "extract")
        self.assertEqual(stageflow.next_step(state(**{"import": False})).key, "import")
        self.assertEqual(stageflow.next_step(state(weights=False)).key, "weights")
        self.assertEqual(stageflow.next_step(state(compile=False)).key, "compile")

    def test_first_gap_wins_not_the_last(self):
        step = stageflow.next_step(state(hero=False, compile=False))
        self.assertEqual(step.key, "hero")

    def test_every_step_has_a_panel_to_go_to(self):
        for step in stageflow.STEPS:
            self.assertTrue(step.detail, step.key)
            self.assertTrue(step.icon, step.key)
            self.assertTrue(step.label, step.key)

    def test_complete_state_reports_done(self):
        self.assertEqual(stageflow.next_step(state()).key, "done")

    def test_progress_counts_answered_steps(self):
        self.assertEqual(stageflow.progress({}), (0, len(stageflow.STEPS)))
        self.assertEqual(stageflow.progress(state()), (len(stageflow.STEPS), len(stageflow.STEPS)))
        answered, total = stageflow.progress(state(compile=False, stage=False))
        self.assertEqual(answered, total - 2)


if __name__ == "__main__":
    unittest.main()
