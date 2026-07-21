import json
import unittest
from xml.etree import ElementTree as ET

from scripts.generate_kml import (
    bearing_lateral_uncertainty,
    add_source_linked_provisional_overlays,
    cross_along_track,
    destination,
    image_rights_qualification,
    is_alignment_eligible_site,
    is_actual_site,
    likely_same_event_alias,
    location_role,
    orientation_qualification,
    orientation_evidence_qualification,
    parse_control_points,
    q,
    temporal_relation,
)


class GeodesyTests(unittest.TestCase):
    def test_destination_due_north(self):
        lat, lon = destination(0.0, 0.0, 0.0, 1000.0)
        self.assertAlmostEqual(lat, 8.9932, places=3)
        self.assertAlmostEqual(lon, 0.0, places=6)

    def test_cross_and_along_track(self):
        target = destination(40.0, -100.0, 90.0, 250.0)
        cross, along, _ = cross_along_track((40.0, -100.0), target, 90.0)
        self.assertLess(abs(cross), 1e-6)
        self.assertAlmostEqual(along, 250.0, places=5)

    def test_cross_track_detects_off_axis_point(self):
        on_axis = destination(40.0, -100.0, 90.0, 250.0)
        target = destination(*on_axis, 0.0, 10.0)
        cross, along, _ = cross_along_track((40.0, -100.0), target, 90.0)
        self.assertAlmostEqual(abs(cross), 10.0, delta=0.05)
        self.assertAlmostEqual(along, 250.0, delta=0.5)

    def test_bearing_uncertainty_expands_with_distance(self):
        self.assertAlmostEqual(bearing_lateral_uncertainty(500, 22.5), 191.2, delta=0.5)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.formation = {
            "latitude": "40",
            "longitude": "-100",
            "geocode_method": "geonames_locality_centroid",
            "assertion_ids": "test_assertion",
        }
        self.observation = {
            "assertion_id": "test_assertion",
            "azimuth_true_deg": "42.5",
            "azimuth_uncertainty_deg": "2.1",
            "orientation_method": "georeferenced_photo",
            "directionality": "bidirectional",
            "evidence_sha256": "a" * 64,
            "reviewer": "test reviewer",
            "reviewed_at": "2026-07-21",
            "origin_latitude": "40.01",
            "origin_longitude": "-100.02",
            "origin_coordinate_method": "registered_component_midpoint",
            "origin_uncertainty_m": "20",
            "max_range_km": "500",
            "corridor_km": "2",
        }

    def test_documented_true_bearing_qualifies(self):
        result = orientation_qualification(self.observation, self.formation)
        self.assertTrue(result["qualified"])
        self.assertEqual(result["origin_method"], "registered_component_midpoint")

    def test_diagram_angle_cannot_qualify(self):
        result = orientation_qualification(
            {
                "diagram_angle_deg": "42.5",
                "orientation_method": "diagram_detection",
            },
            self.formation,
        )
        self.assertFalse(result["qualified"])
        self.assertIn("invalid_or_missing_true_azimuth", result["reasons"])
        self.assertIn("unsupported_orientation_method", result["reasons"])

    def test_locality_centroid_cannot_be_a_ray_origin(self):
        observation = dict(self.observation)
        observation.pop("origin_latitude")
        observation.pop("origin_longitude")
        self.formation["coordinate_uncertainty_km"] = "5"
        result = orientation_qualification(observation, self.formation)
        self.assertFalse(result["qualified"])
        self.assertIn("coarse_origin_requires_registered_coordinate", result["reasons"])

    def test_orphan_assertion_cannot_generate_a_ray(self):
        observation = dict(self.observation, assertion_id="not_attached")
        result = orientation_qualification(observation, self.formation)
        self.assertFalse(result["qualified"])
        self.assertIn("orientation_assertion_not_attached_to_formation", result["reasons"])


class OverlayTests(unittest.TestCase):
    def test_corner_payload(self):
        raw = json.dumps(
            {
                "corners": {
                    "nw": {"lat": 40.1, "lon": -100.1},
                    "ne": {"lat": 40.1, "lon": -99.9},
                    "se": {"lat": 39.9, "lon": -99.9},
                    "sw": {"lat": 39.9, "lon": -100.1},
                }
            }
        )
        self.assertEqual(
            parse_control_points(raw),
            [(40.1, -100.1), (40.1, -99.9), (39.9, -99.9), (39.9, -100.1)],
        )

    def test_public_derivative_boolean_fails_closed(self):
        valid, reasons = image_rights_qualification({
            "rights_status": "permission_granted",
            "public_derivative_export_allowed": "false",
            "rights_proof": "written permission record",
            "rights_holder": "Example holder",
            "reviewer": "Reviewer",
            "reviewed_at": "2026-07-21",
        })
        self.assertFalse(valid)
        self.assertIn("public_derivative_export_not_allowed", reasons)

    def test_remote_overlay_is_opt_in_at_folder_level_and_preserves_transparency(self):
        document = ET.Element(q("Document"))
        payload = {"overlays": [{
            "overlay_id": "remote-test",
            "formation_id": "formation-test",
            "source_image_url": "https://example.org/source.jpg",
            "default_opacity": 0.68,
            "corners": [[40.1, -100.1], [40.1, -99.9], [39.9, -99.9], [39.9, -100.1]],
        }]}
        count, rejected, included = add_source_linked_provisional_overlays(
            document, payload, {"formation-test"}
        )
        self.assertEqual((count, rejected, included), (1, [], {"remote-test"}))
        folder = document.find(q("Folder"))
        overlay = folder.find(q("GroundOverlay"))
        self.assertEqual(folder.find(q("visibility")).text, "0")
        self.assertEqual(overlay.find(q("visibility")).text, "1")
        self.assertEqual(overlay.find(q("color")).text, "adffffff")

    def test_folded_remote_overlay_is_rejected_and_not_audited_as_included(self):
        document = ET.Element(q("Document"))
        payload = {"overlays": [{
            "overlay_id": "folded-test",
            "formation_id": "formation-test",
            "source_image_url": "https://example.org/source.jpg",
            "corners": [[40.1, -100.1], [39.9, -99.9], [40.1, -99.9], [39.9, -100.1]],
        }]}
        count, rejected, included = add_source_linked_provisional_overlays(
            document, payload, {"formation-test"}
        )
        self.assertEqual(count, 0)
        self.assertEqual(included, set())
        self.assertEqual(rejected[0]["reason"], "invalid_remote_overlay_corners")


class LocationRoleTests(unittest.TestCase):
    def test_formation_site_role_uses_evidence_status(self):
        candidate = {"location_role": "formation_site", "location_status": "candidate_field"}
        accepted = {"location_role": "formation_site", "location_status": "corroborated_field"}
        self.assertEqual(location_role(candidate), "candidate_field")
        self.assertEqual(location_role(accepted), "corroborated_field")
        self.assertFalse(is_actual_site(candidate))
        self.assertTrue(is_actual_site(accepted))

    def test_alignment_eligibility_is_explicit_not_implied_by_registered_status(self):
        self.assertFalse(is_alignment_eligible_site({"site_status": "registered_site"}))
        self.assertTrue(is_alignment_eligible_site({"site_alignment_eligible": "true"}))


class EntityAliasTests(unittest.TestCase):
    def test_same_date_place_qualifier_is_an_alias_candidate(self):
        source = {"date_iso": "1994-06-14", "country_code": "US", "place": "Aloha [Sunset Hwy.]"}
        target = {"date_iso": "1994-06-14", "country_code": "US", "place": "Aloha"}
        self.assertTrue(likely_same_event_alias(source, target))

    def test_different_dates_are_not_collapsed(self):
        source = {"date_iso": "2003-07-04", "country_code": "US", "place": "Mayville / Kekoskee"}
        target = {"date_iso": "2003-08-04", "country_code": "US", "place": "Mayville"}
        self.assertFalse(likely_same_event_alias(source, target))


class TemporalRelationTests(unittest.TestCase):
    def test_day_precision_orders_same_year_events(self):
        self.assertEqual(temporal_relation("2003-07-04", "2003-08-08"), "later")
        self.assertEqual(temporal_relation("1994-06-14", "1994-06-08"), "earlier")

    def test_overlapping_precision_is_indeterminate(self):
        self.assertEqual(temporal_relation("2003-07", "2003-07-24"), "overlap_or_indeterminate")
        self.assertEqual(temporal_relation("2003", "2003-08-08"), "overlap_or_indeterminate")


class EvidenceIntegrityTests(unittest.TestCase):
    def test_missing_evidence_cache_fails_closed(self):
        valid, reason = orientation_evidence_qualification(
            {"evidence_sha256": "a" * 64, "evidence_cache_path": "missing.html"}
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "evidence_cache_file_missing")


if __name__ == "__main__":
    unittest.main()
