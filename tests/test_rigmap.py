from __future__ import annotations

import unittest

from forge import rigmap


def bone(name, parent, head, tail):
    return rigmap.Bone(name=name, parent=parent, head=head, tail=tail)


SPINE = [
    bone("root", None, (0.0, 0.0, 0.0), (0.0, 0.0, 4.0)),
    bone("spine_0", "root", (0.0, 0.0, 4.0), (0.0, 0.0, 10.0)),
    bone("neck", "spine_0", (0.0, 0.0, 10.0), (0.0, 0.0, 14.0)),
    bone("head", "neck", (0.0, 0.0, 14.0), (0.0, 0.0, 20.0)),
    bone("arm_l", "spine_0", (-6.0, 0.0, 10.0), (-12.0, 0.0, 10.0)),
]


class ProjectTest(unittest.TestCase):
    def test_planes_keep_their_two_axes(self):
        point = (1.0, 2.0, 3.0)
        self.assertEqual(rigmap.project(point, "FRONT"), (1.0, 3.0))
        self.assertEqual(rigmap.project(point, "SIDE"), (2.0, 3.0))
        self.assertEqual(rigmap.project(point, "TOP"), (1.0, 2.0))


class DepthTest(unittest.TestCase):
    def test_depth_counts_ancestors(self):
        level = rigmap.depths(SPINE)
        self.assertEqual(level["root"], 0)
        self.assertEqual(level["spine_0"], 1)
        self.assertEqual(level["head"], 3)

    def test_cycle_and_orphan_both_stop_at_zero(self):
        bones = [
            bone("a", "b", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            bone("b", "a", (0.0, 0.0, 1.0), (0.0, 0.0, 2.0)),
            bone("lost", "missing", (0.0, 0.0, 2.0), (0.0, 0.0, 3.0)),
        ]
        level = rigmap.depths(bones)
        self.assertEqual(level["lost"], 0)
        self.assertLessEqual(level["a"], 1)
        self.assertLessEqual(level["b"], 1)


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.rect = (100.0, 50.0, 400.0, 300.0)
        self.placed = rigmap.layout(SPINE, "FRONT", self.rect)

    def test_empty_rig_has_no_points(self):
        self.assertEqual(rigmap.layout([], "FRONT", self.rect), {})

    def test_every_point_stays_inside_the_rect(self):
        x, y, width, height = self.rect
        for item in self.placed.values():
            for point in (item.head, item.tail):
                self.assertGreaterEqual(point[0], x - 0.001)
                self.assertLessEqual(point[0], x + width + 0.001)
                self.assertGreaterEqual(point[1], y - 0.001)
                self.assertLessEqual(point[1], y + height + 0.001)

    def test_child_sits_above_its_parent(self):
        self.assertGreater(self.placed["head"].head[1], self.placed["neck"].head[1])
        self.assertGreater(self.placed["neck"].head[1], self.placed["spine_0"].head[1])

    def test_aspect_is_kept(self):
        # The spine is 20 units tall and the arm reaches 6 units sideways; the
        # diagram must not stretch one axis, so both use one pixels-per-unit.
        spine_pixels = self.placed["head"].tail[1] - self.placed["root"].head[1]
        arm_pixels = abs(self.placed["arm_l"].head[0] - self.placed["spine_0"].head[0])
        self.assertAlmostEqual(spine_pixels / 20.0, arm_pixels / 6.0, places=3)

    def test_side_plane_drops_the_sideways_axis(self):
        # Every bone here sits at y=0, so a side view collapses the horizontal
        # spread the front view shows; that is the plane doing its job.
        front = self.placed["arm_l"].head[0] - self.placed["spine_0"].head[0]
        side = (
            rigmap.layout(SPINE, "SIDE", self.rect)["arm_l"].head[0]
            - rigmap.layout(SPINE, "SIDE", self.rect)["spine_0"].head[0]
        )
        self.assertNotAlmostEqual(front, side, places=3)
        self.assertAlmostEqual(side, 0.0, places=6)


class NearestTest(unittest.TestCase):
    def test_picks_the_closest_head_inside_the_limit(self):
        placed = rigmap.layout(SPINE, "FRONT", (0.0, 0.0, 400.0, 400.0))
        target = placed["neck"].head
        found = rigmap.nearest(placed, target[0] + 2.0, target[1] - 2.0, limit=10.0)
        self.assertEqual(found, "neck")

    def test_returns_nothing_outside_the_limit(self):
        placed = rigmap.layout(SPINE, "FRONT", (0.0, 0.0, 400.0, 400.0))
        target = placed["neck"].head
        self.assertIsNone(rigmap.nearest(placed, target[0], target[1] + 200.0, limit=8.0))


class ChainTest(unittest.TestCase):
    def test_chain_runs_to_the_root(self):
        placed = rigmap.layout(SPINE, "FRONT", (0.0, 0.0, 400.0, 400.0))
        self.assertEqual(rigmap.chain(placed, "head"), ["head", "neck", "spine_0", "root"])

    def test_children_are_direct_only(self):
        placed = rigmap.layout(SPINE, "FRONT", (0.0, 0.0, 400.0, 400.0))
        self.assertEqual(sorted(rigmap.children(placed, "spine_0")), ["arm_l", "neck"])


if __name__ == "__main__":
    unittest.main()
