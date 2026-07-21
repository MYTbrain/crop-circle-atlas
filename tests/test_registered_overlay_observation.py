import json
import unittest
from pathlib import Path

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

    def test_non_hubbard_source_coordinate_placements_are_persisted_and_reproducible(self):
        validate_registered_overlay()
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "data" / "registered_overlay_observations.json").read_text(
                encoding="utf-8"
            )
        )
        observations = {row["observation_id"]: row for row in payload["observations"]}
        self.assertEqual(len(observations), 5)
        self.assertEqual(
            observations["regobs_mayville_2003_source_gps_v1"]["quality"]["status"],
            "useful_provisional_geometry_registration",
        )
        self.assertEqual(
            observations["regobs_howell_2003_source_gps_v1"]["quality"]["status"],
            "useful_provisional_geometry_registration",
        )
        self.assertEqual(
            observations["regobs_jupiter_2005_source_gps_v1"][
                "local_display_transform"
            ]["orientation_status"],
            "unresolved_display_assumption",
        )
        self.assertEqual(
            observations["regobs_wausau_1997_usgs_followup_v1"]["quality"]["status"],
            "useful_provisional_landmark_registration",
        )


if __name__ == "__main__":
    unittest.main()
