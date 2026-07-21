import unittest

from scripts.verify_registered_overlay import validate_registered_overlay


class RegisteredOverlayObservationTests(unittest.TestCase):
    def test_hubbard_2000_display_geometry_is_reproducible_and_unqualified(self):
        observation = validate_registered_overlay()
        self.assertEqual(observation["classification"], "approximate_visual_registration")
        self.assertEqual(observation["affine_fit"]["independent_checkpoint_count"], 0)
        self.assertIn(
            "not a confidence interval",
            observation["detector_sensitivity_envelope"]["interpretation"],
        )


if __name__ == "__main__":
    unittest.main()
