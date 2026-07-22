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
        self.assertGreaterEqual(len(observations), 8)
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
        placements = json.loads(
            (root / "data" / "provisional_image_scene_placements.json").read_text(
                encoding="utf-8"
            )
        )["placements"]
        for placement in placements:
            observation = observations[placement["observation_id"]]
            self.assertEqual(observation["overlay_id"], placement["overlay_id"])
            self.assertTrue(
                observation["formal_alignment_status"].startswith(
                    "excluded_pending_"
                )
            )
            self.assertEqual(
                observation["source_evidence"]["url"],
                placement["source_image_url"],
            )

        wavra = observations["regobs_wavra_farm_1997_landmark_v1"]
        registration = wavra["source_registration"]
        self.assertEqual(
            registration["artifact_sha256"],
            "8c435a670ff869efa9fa0907aa41eb51012a6edc599fa75b0a0df07ea4987970",
        )
        self.assertEqual(
            registration["lat_lon_box"]["rotation_ccw_deg"],
            121.6502227783203,
        )
        self.assertEqual(
            wavra["computed_corners_wgs84_lat_lon"],
            [
                [44.87153998909242, -122.89766937722305],
                [44.8737644058229, -122.89960432096206],
                [44.87584385168213, -122.89484428508177],
                [44.873619201401276, -122.89290932219285],
            ],
        )

        commons = observations["regobs_commons_diessenhofen_20080715_v1"]
        self.assertEqual(commons["classification"], "provisional_four_control_landmark_scene_placement")
        self.assertEqual(commons["source_evidence"]["sha256"], "67c44d76a64373becbab575f92bb3f44213c2b77a4c96b5c4d4c4af11dd930f0")
        self.assertEqual(commons["projective_display_transform"]["independent_ground_checkpoint_count"], 0)


if __name__ == "__main__":
    unittest.main()
