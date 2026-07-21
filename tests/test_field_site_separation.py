from __future__ import annotations

import csv
import json
import math
import unittest
from pathlib import Path

from scripts.build_dataset import automatic_site_status


ROOT = Path(__file__).resolve().parents[1]
SITE_STATUSES = {
    "unresolved", "locality_reference", "candidate_field",
    "corroborated_field", "registered_site",
}
FIELD_SITE_STATUSES = {"candidate_field", "corroborated_field", "registered_site"}


def csv_rows(name: str) -> list[dict[str, str]]:
    with (ROOT / "data" / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 6371.0088
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


class FieldSiteSeparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.formations = csv_rows("formations.csv")
        cls.by_id = {row["formation_id"]: row for row in cls.formations}
        cls.queue = csv_rows("location_work_queue.csv")
        cls.index = json.loads((ROOT / "web" / "data" / "formation_index.json").read_text(encoding="utf-8"))
        cls.sites = json.loads((ROOT / "web" / "data" / "formation_sites.geojson").read_text(encoding="utf-8"))
        cls.localities = json.loads((ROOT / "web" / "data" / "locality_references.geojson").read_text(encoding="utf-8"))

    def test_every_canonical_entity_is_classified_indexed_and_queued(self):
        formation_ids = [row["formation_id"] for row in self.formations]
        index_ids = [row["formation_id"] for row in self.index["formations"]]
        queue_ids = [row["formation_id"] for row in self.queue]
        self.assertEqual(len(formation_ids), len(set(formation_ids)))
        self.assertEqual(set(index_ids), set(formation_ids))
        self.assertEqual(set(queue_ids), set(formation_ids))
        self.assertEqual(self.index["metadata"]["record_count"], len(formation_ids))
        self.assertTrue(all(row["site_status"] in SITE_STATUSES for row in self.formations))
        self.assertTrue(any(row["site_status"] == "unresolved" for row in self.index["formations"]))

    def test_location_queue_priority_is_total_and_deterministic(self):
        self.assertEqual([int(row["priority_rank"]) for row in self.queue], list(range(1, len(self.queue) + 1)))
        ordering = [(-int(row["priority_score"]), row["formation_id"]) for row in self.queue]
        self.assertEqual(ordering, sorted(ordering))
        first_non_us = next(index for index, row in enumerate(self.queue) if row["us_priority"] == "no")
        self.assertTrue(all(row["us_priority"] == "yes" for row in self.queue[:first_non_us]))
        self.assertTrue(all(row["us_priority"] == "no" for row in self.queue[first_non_us:]))

    def test_whiskey_hill_1998_is_in_full_index_and_field_site_layer(self):
        formation = self.by_id["cc_e5724a3476de"]
        self.assertEqual(formation["site_status"], "corroborated_field")
        self.assertAlmostEqual(float(formation["site_latitude"]), 45.1714056, places=7)
        self.assertAlmostEqual(float(formation["site_longitude"]), -122.7264972, places=7)
        self.assertIn("a_07151793fc35f4", formation["assertion_ids"].split("; "))
        self.assertIn("cc_d85d5c118449", formation["merged_alias_formation_ids"].split("; "))
        self.assertIn("cc_e5724a3476de", {row["formation_id"] for row in self.index["formations"]})
        self.assertIn(
            "cc_e5724a3476de",
            {feature["properties"]["formation_id"] for feature in self.sites["features"]},
        )

    def test_whiskey_hill_2000_replaces_centroid_and_merges_alias_sources(self):
        formation = self.by_id["cc_80f4a64d3689"]
        corrected = (float(formation["latitude"]), float(formation["longitude"]))
        old_hubbard_centroid = (45.18234, -122.80787)
        self.assertGreater(haversine_km(corrected, old_hubbard_centroid), 6.0)
        self.assertEqual(formation["site_status"], "corroborated_field")
        self.assertEqual(formation["site_coordinate_method"], "direct_historical_imagery_match")
        self.assertEqual(formation["site_directly_visible"], "true")
        self.assertEqual(
            set(formation["merged_alias_formation_ids"].split("; ")),
            {"cc_19fdee41af91", "cc_6ab089f895ba"},
        )
        self.assertTrue({"a_cf84a25d4ce632", "sx_vigay_6607ed8489280db3"}.issubset(
            set(formation["assertion_ids"].split("; "))
        ))

    def test_false_california_aliases_are_absent_from_primary_outputs(self):
        aliases = {"cc_d85d5c118449", "cc_19fdee41af91", "cc_6ab089f895ba", "cc_969282bc2775"}
        self.assertTrue(aliases.isdisjoint(self.by_id))
        self.assertTrue(aliases.isdisjoint(row["formation_id"] for row in self.index["formations"]))
        self.assertTrue(aliases.isdisjoint(
            feature["properties"]["formation_id"] for feature in self.sites["features"]
        ))
        self.assertTrue(aliases.isdisjoint(
            feature["properties"]["formation_id"] for feature in self.localities["features"]
        ))

    def test_locality_references_never_enter_field_site_layer(self):
        site_features = self.sites["features"]
        self.assertEqual(len(site_features), len({
            feature["properties"]["formation_id"] for feature in site_features
        }))
        site_ids = {feature["properties"]["formation_id"] for feature in site_features}
        locality_ids = {feature["properties"]["formation_id"] for feature in self.localities["features"]}
        self.assertTrue(site_ids.isdisjoint(locality_ids))
        self.assertTrue(all(
            feature["properties"]["site_status"] in FIELD_SITE_STATUSES
            for feature in self.sites["features"]
        ))
        self.assertTrue(all(
            feature["properties"]["site_status"] == "locality_reference"
            for feature in self.localities["features"]
        ))
        self.assertEqual(
            locality_ids,
            {row["formation_id"] for row in self.formations if row["site_status"] == "locality_reference"},
        )
        self.assertEqual(
            site_ids,
            {row["formation_id"] for row in self.formations if row["site_status"] in FIELD_SITE_STATUSES},
        )
        for feature in site_features:
            row = self.by_id[feature["properties"]["formation_id"]]
            longitude, latitude = feature["geometry"]["coordinates"]
            self.assertAlmostEqual(latitude, float(row["latitude"]), places=7)
            self.assertAlmostEqual(longitude, float(row["longitude"]), places=7)

    def test_review_and_rights_are_separate_site_resolution_fields(self):
        rows = {row["formation_id"]: row for row in csv_rows("site_resolutions.csv")}
        for formation_id in ("cc_e5724a3476de", "cc_69ae8f9bae18", "cc_80f4a64d3689"):
            self.assertTrue(rows[formation_id]["review_status"])
            self.assertTrue(rows[formation_id]["rights_status"])
            self.assertNotEqual(rows[formation_id]["review_status"], rows[formation_id]["rights_status"])
            self.assertEqual(rows[formation_id]["imagery_provider"], "Google Earth/USGS")
            self.assertEqual(rows[formation_id]["imagery_acquisition_date"], "2000-07-28")
            self.assertEqual(rows[formation_id]["reviewed_at"], "2026-07-21")
            self.assertIn("Coordinates digitized from the user-supplied screenshot/status bar", rows[formation_id]["notes"])
            self.assertIn("uncertainty is conservative", rows[formation_id]["notes"])
        self.assertEqual(rows["cc_e5724a3476de"]["directly_visible"], "false")
        self.assertEqual(rows["cc_69ae8f9bae18"]["site_status"], "candidate_field")
        self.assertEqual(rows["cc_69ae8f9bae18"]["coordinate_method"], "same_field_source_statement")
        self.assertEqual(rows["cc_69ae8f9bae18"]["coordinate_uncertainty_m"], "200")
        self.assertEqual(rows["cc_80f4a64d3689"]["directly_visible"], "true")

    def test_whiskey_cluster_aliases_and_alignment_eligibility_are_explicit(self):
        expected_aliases = "Whiskey Hill; Hubbard; Woodburn"
        for formation_id in ("cc_e5724a3476de", "cc_69ae8f9bae18", "cc_80f4a64d3689"):
            row = self.by_id[formation_id]
            self.assertEqual(row["site_cluster_id"], "whiskey_hill_oregon_field")
            self.assertEqual(row["site_search_aliases"], expected_aliases)
        self.assertEqual(self.by_id["cc_e5724a3476de"]["site_alignment_eligible"], "true")
        self.assertEqual(self.by_id["cc_69ae8f9bae18"]["site_alignment_eligible"], "false")
        self.assertEqual(self.by_id["cc_80f4a64d3689"]["site_alignment_eligible"], "true")

        indexed = {row["formation_id"]: row for row in self.index["formations"]}
        self.assertTrue(all(expected_aliases in indexed[formation_id]["site_search_aliases"] for formation_id in (
            "cc_e5724a3476de", "cc_69ae8f9bae18", "cc_80f4a64d3689",
        )))

    def test_site_evidence_hashes_and_subjects_are_not_url_hashes(self):
        resolutions = {row["formation_id"]: row for row in csv_rows("site_resolutions.csv")}
        self.assertIn(
            "b90a07196d559328b74e9f31cd0f12ea1cedf6bdb6e1d36f7811d2ac32f42cc0",
            resolutions["cc_e5724a3476de"]["evidence_artifact_sha256s"],
        )
        self.assertEqual(
            resolutions["cc_80f4a64d3689"]["evidence_artifact_sha256s"],
            "07fc1139cd325aaadb787c10457cddc7fb9bc8eb24fbed227c4f2307d1dc39bd",
        )
        provisional = csv_rows("provisional_orientation_observations.csv")
        self.assertEqual(len(provisional), 1)
        self.assertEqual(provisional[0]["evidence_kind"], "user_supplied_registration_screenshot")
        self.assertEqual(provisional[0]["evidence_sha256_subject"], "user_supplied_pic5_registration_screenshot")
        self.assertIn("not a hash of evidence_url", provisional[0]["notes"])

    def test_aloha_source_coordinate_is_a_non_target_site_not_a_locality(self):
        formation_id = "cc_8a68d8a0471b"
        site_ids = {feature["properties"]["formation_id"] for feature in self.sites["features"]}
        locality_ids = {feature["properties"]["formation_id"] for feature in self.localities["features"]}
        row = self.by_id[formation_id]
        self.assertIn(formation_id, site_ids)
        self.assertNotIn(formation_id, locality_ids)
        self.assertEqual(row["site_status"], "registered_site")
        self.assertEqual(row["site_coordinate_method"], "source_report_degrees_minutes")
        self.assertEqual(row["site_alignment_eligible"], "false")
        self.assertEqual(row["site_coordinate_uncertainty_m"], "1500.0")
        self.assertEqual(row["source_count"], "2")
        self.assertIn("cc_969282bc2775", row["merged_alias_formation_ids"].split("; "))
        self.assertEqual(
            set(row["assertion_ids"].split("; ")),
            {"a_bb14f2ae43a320", "iccra_c100c7083922d347"},
        )

    def test_automatic_coordinate_methods_fail_closed(self):
        self.assertEqual(automatic_site_status({
            "formation_id": "allowed", "latitude": 1, "longitude": 2,
            "geocode_method": "source_decimal_degrees",
        }), "registered_site")
        with self.assertRaisesRegex(ValueError, "unsupported automatic source-coordinate method"):
            automatic_site_status({
                "formation_id": "unsupported", "latitude": 1, "longitude": 2,
                "geocode_method": "unreviewed_scraper_guess",
            })


if __name__ == "__main__":
    unittest.main()
