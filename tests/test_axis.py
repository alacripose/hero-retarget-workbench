from fractions import Fraction
import unittest

from forge.axis import AxisError, AxisTransform, PRESETS, determinant


class AxisTests(unittest.TestCase):
    def test_presets_are_handed_and_invert(self):
        for name in ("blender-to-source2", "source2-to-blender", "gltf-to-source2", "source2-to-gltf"):
            transform = AxisTransform.preset(name)
            self.assertEqual(transform.determinant, 1)
            inverse = AxisTransform.preset(
                {
                    "blender-to-source2": "source2-to-blender",
                    "source2-to-blender": "blender-to-source2",
                    "gltf-to-source2": "source2-to-gltf",
                    "source2-to-gltf": "gltf-to-source2",
                }[name]
            )
            point = (1.25, -2.5, 3.75)
            round_trip = inverse.point(*transform.point(*point))
            for got, want in zip(round_trip, point):
                self.assertAlmostEqual(got, want, places=5)

    def test_forward_maps_to_source_x(self):
        transform = AxisTransform.preset("blender-to-source2")
        self.assertEqual(transform.point(0, 1, 0), (1.0, 0.0, 0.0))
        self.assertEqual(transform.point(1, 0, 0), (0.0, -1.0, 0.0))
        self.assertEqual(transform.point(0, 0, 1), (0.0, 0.0, 1.0))

    def test_mirror_is_named_not_implicit(self):
        with self.assertRaises(AxisError):
            AxisTransform.preset("mirror-x")
        mirrored = AxisTransform.preset("mirror-x", allow_mirror=True)
        self.assertEqual(mirrored.determinant, -1)
        self.assertEqual(mirrored.point(2, 3, 4), (-2.0, 3.0, 4.0))

    def test_weights_are_not_in_the_transform(self):
        transform = AxisTransform.preset("blender-to-source2")
        self.assertEqual(transform.witness()["touches_weights"], False)
        self.assertEqual(set(transform.witness()), {"name", "matrix", "determinant", "scale", "touches_weights"})

    def test_scale_is_exact_before_float(self):
        transform = AxisTransform.preset("identity", scale=Fraction(1, 4))
        self.assertEqual(transform.point(4, -8, 0), (1.0, -2.0, 0.0))
        self.assertEqual(transform.matrix4()[0], (0.25, 0.0, 0.0, 0.0))
        self.assertEqual(transform.matrix4()[3], (0.0, 0.0, 0.0, 1.0))

    def test_unknown_preset_is_refused(self):
        with self.assertRaises(AxisError):
            AxisTransform.preset("made-up-axis")

    def test_determinant_helper(self):
        self.assertEqual(determinant(PRESETS["identity"]), 1)
        self.assertEqual(determinant(PRESETS["mirror-x"]), -1)


if __name__ == "__main__":
    unittest.main()
