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

        rockville = observations["regobs_rockville_1_2003_landmark_v1"]
        self.assertEqual(
            rockville["classification"],
            "provisional_three_control_affine_road_registration",
        )
        self.assertEqual(
            rockville["source_registration"]["kind"],
            "manual_three_control_affine_scene_registration",
        )
        self.assertEqual(len(rockville["landmark_controls"]["controls"]), 3)
        self.assertEqual(
            rockville["computed_corners_wgs84_lat_lon"],
            [
                [38.244922841631, -122.123978339737],
                [38.244609172775, -122.120924952978],
                [38.241855798216, -122.125254354862],
                [38.242169478951, -122.128307741621],
            ],
        )

        commons = observations["regobs_commons_diessenhofen_20080715_v1"]
        self.assertEqual(commons["classification"], "provisional_four_control_landmark_scene_placement")
        self.assertEqual(commons["source_evidence"]["sha256"], "67c44d76a64373becbab575f92bb3f44213c2b77a4c96b5c4d4c4af11dd930f0")
        self.assertEqual(commons["projective_display_transform"]["independent_ground_checkpoint_count"], 0)

        horhausen = observations["regobs_commons_horhausen_20090712_geometry_v1"]
        self.assertEqual(
            horhausen["classification"],
            "provisional_documented_size_crop_geometry_rectification",
        )
        self.assertEqual(
            horhausen["source_evidence"]["sha256"],
            "3ad01ee7895475c756069090904e162b81860bf93e5efdb02c682ba81f94279c",
        )
        self.assertEqual(
            horhausen["projective_display_transform"][
                "independent_ground_checkpoint_count"
            ],
            0,
        )
        self.assertEqual(
            horhausen["formal_alignment_status"],
            "excluded_pending_independent_ground_control",
        )
        self.assertIn("zero independent", horhausen["quality"]["limitations"])

        darfield = observations["regobs_darfield_2002_legacy_coordinate_scale_v1"]
        self.assertEqual(
            darfield["classification"], "coordinate_size_geometry_provisional"
        )
        self.assertEqual(
            darfield["source_registration"]["kind"],
            "legacy_coordinate_scale_north_up_display_placement",
        )
        self.assertEqual(darfield["source_registration"]["control_count"], 0)
        self.assertEqual(
            darfield["local_display_transform"][
                "independent_ground_checkpoint_count"
            ],
            0,
        )
        self.assertEqual(
            darfield["computed_corners_wgs84_lat_lon"],
            [
                [53.532226751785, -1.358078415213],
                [53.532226751785, -1.355205354314],
                [53.53126618142, -1.355205354314],
                [53.53126618142, -1.358078415213],
            ],
        )

        legacy_expected = {
            "regobs_hexton_barton_hills_2002_legacy_coordinate_scale_v1": (
                "coordinate_size_geometry_provisional",
                "legacy_coordinate_scale_north_up_display_placement",
                [
                    [51.94641024513, -0.392701146675],
                    [51.94641024513, -0.390275049526],
                    [51.945569052006, -0.390275049526],
                    [51.945569052006, -0.392701146675],
                ],
            ),
            "regobs_waden_hill_2002_legacy_coordinate_scale_v1": (
                "coordinate_size_geometry_provisional",
                "legacy_coordinate_scale_north_up_display_placement",
                [
                    [51.425019054448, -1.856643925105],
                    [51.425019054448, -1.854279777825],
                    [51.424189844132, -1.854279777825],
                    [51.424189844132, -1.856643925105],
                ],
            ),
            "regobs_dodworth_st_john_2002_legacy_coordinate_scale_v1": (
                "coordinate_size_geometry_provisional",
                "legacy_coordinate_scale_north_up_display_placement",
                [
                    [53.542131113279, -1.536875940351],
                    [53.542131113279, -1.534284446279],
                    [53.541264884646, -1.534284446279],
                    [53.541264884646, -1.536875940351],
                ],
            ),
            "regobs_panocchia_2004_legacy_coordinate_reported_size_v1": (
                "coordinate_size_north_up_provisional",
                "legacy_coordinate_reported_size_north_up_display_placement",
                [
                    [44.6814292798, 10.31669709193],
                    [44.6814292798, 10.318449770799],
                    [44.680494620774, 10.318449770799],
                    [44.680494620774, 10.31669709193],
                ],
            ),
            "regobs_hackpen_hill_2003_legacy_coordinate_scale_v1": (
                "coordinate_size_geometry_provisional",
                "legacy_coordinate_scale_north_up_display_placement",
                [
                    [51.473784060641, -1.826643881513],
                    [51.473784060641, -1.824193423982],
                    [51.472925497748, -1.824193423982],
                    [51.472925497748, -1.826643881513],
                ],
            ),
        }
        for observation_id, (classification, kind, corners) in legacy_expected.items():
            observation = observations[observation_id]
            self.assertEqual(observation["classification"], classification)
            self.assertEqual(observation["source_registration"]["kind"], kind)
            self.assertEqual(observation["source_registration"]["control_count"], 0)
            self.assertEqual(
                observation["local_display_transform"][
                    "independent_ground_checkpoint_count"
                ],
                0,
            )
            self.assertEqual(observation["computed_corners_wgs84_lat_lon"], corners)


if __name__ == "__main__":
    unittest.main()
