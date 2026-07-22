import csv
import importlib.util
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_global_source_image_links",
    ROOT / "scripts" / "build_global_source_image_links.py",
)
GLOBAL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = GLOBAL
SPEC.loader.exec_module(GLOBAL)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class GlobalSourceImageLinkTests(unittest.TestCase):
    def test_british_grid_conversion_matches_hackpen_source_coordinate(self):
        easting, northing, resolution = GLOBAL.os_grid_ref_to_easting_northing(
            "SU1251075303"
        )
        latitude, longitude = GLOBAL.bng_to_wgs84(easting, northing)
        self.assertEqual(resolution, 1)
        self.assertAlmostEqual(latitude, 51.476556, delta=0.00002)
        self.assertAlmostEqual(longitude, -1.821250, delta=0.00002)

    def test_country_year_tokens_are_not_grid_references(self):
        body = b'<html><body><img src="TV2010.jpg"> HU2020 NL2018</body></html>'
        self.assertEqual(
            GLOBAL.page_coordinate_candidates(
                "https://example.test/report.html",
                body,
                "GB",
            ),
            [],
        )

    def test_explicit_grid_reference_is_accepted_for_gb_only(self):
        body = b"<html><body>Map Ref: SU1251075303</body></html>"
        gb_candidates = GLOBAL.page_coordinate_candidates(
            "https://example.test/report.html",
            body,
            "GB",
        )
        self.assertEqual(len(gb_candidates), 1)
        self.assertEqual(
            gb_candidates[0]["method"],
            "reported_os_grid_reference_to_wgs84",
        )
        self.assertTrue(
            GLOBAL.is_within_gb(
                float(gb_candidates[0]["latitude"]),
                float(gb_candidates[0]["longitude"]),
            )
        )
        self.assertEqual(
            GLOBAL.page_coordinate_candidates(
                "https://example.test/report.html",
                body,
                "BR",
            ),
            [],
        )

    def test_exact_google_coordinate_remains_available_outside_gb(self):
        body = (
            b'<html><body><a href="https://www.google.com/maps/@-26.6305,-51.6708,17z">'
            b"map</a></body></html>"
        )
        candidates = GLOBAL.page_coordinate_candidates(
            "https://example.test/report.html",
            body,
            "BR",
        )
        self.assertEqual(len(candidates), 1)
        self.assertAlmostEqual(float(candidates[0]["latitude"]), -26.6305)
        self.assertAlmostEqual(float(candidates[0]["longitude"]), -51.6708)
        self.assertEqual(candidates[0]["method"], "google_maps_view_center_review_needed")

    def test_gb_tagged_google_dms_coordinate_in_france_fails_closed(self):
        body = (
            b'<html><body><a href="https://www.google.co.uk/maps/place/'
            b'48%C2%B048%2719.9%22N+7%C2%B005%2758.4%22E">map</a></body></html>'
        )
        self.assertEqual(
            [],
            GLOBAL.page_coordinate_candidates(
                "https://example.test/rauwiller.html",
                body,
                "GB",
            ),
        )
        candidates = GLOBAL.page_coordinate_candidates(
            "https://example.test/rauwiller.html",
            body,
            "FR",
        )
        self.assertEqual(1, len(candidates))
        self.assertEqual("google_maps_dms_target", candidates[0]["method"])
        self.assertTrue(
            GLOBAL.candidate_is_geographically_plausible(
                {"country_code": "FR", "region": "Bas-Rhin"},
                candidates[0],
            )
        )

    def test_same_country_remote_coordinate_fails_independent_locality_gate(self):
        assertion = {"country_code": "FR", "region": "Grand Est"}
        locality = {
            "cc_test": {
                "latitude": 48.8055,
                "longitude": 7.0996,
                "country_code": "FR",
                "admin1": "Grand Est",
                "uncertainty_km": 5,
            }
        }
        remote_candidate = {"latitude": 43.5, "longitude": 2.3}
        nearby_candidate = {"latitude": 48.81, "longitude": 7.10}
        self.assertFalse(
            GLOBAL.candidate_is_geographically_plausible(
                assertion,
                remote_candidate,
                "cc_test",
                locality,
            )
        )
        self.assertTrue(
            GLOBAL.candidate_is_geographically_plausible(
                assertion,
                nearby_candidate,
                "cc_test",
                locality,
            )
        )

    def test_corrected_rauwiller_assertion_links_to_french_baseline_formation(self):
        formation_by_assertion = GLOBAL.formation_index()
        self.assertEqual(
            formation_by_assertion["a_3072099b1a18be"],
            formation_by_assertion["sx_connector_92bc2feab960f36e"],
        )
        self.assertEqual(
            "cc_a924832e6d3c",
            formation_by_assertion["sx_connector_92bc2feab960f36e"],
        )

    def test_offline_index_baseline_covers_every_source_assertion(self):
        rows, pages = GLOBAL.build_rows(live_details=False)
        self.assertEqual(pages, {})
        expected = {"ccc": 1166, "connector": 442, "dcca": 184}
        assertion_counts = {
            source_id: len(assertions)
            for source_id, assertions in GLOBAL.source_rows().items()
        }
        self.assertEqual(assertion_counts, expected)
        covered = {
            source_id: len({row["assertion_id"] for row in rows if row["source_id"] == source_id})
            for source_id in expected
        }
        self.assertEqual(covered, expected)
        self.assertEqual(len(rows), 1792)

    def test_generated_image_inventory_is_link_only_and_deterministic(self):
        rows = read_csv(ROOT / "data" / "global_source_image_links.csv")
        self.assertTrue(rows)
        self.assertEqual(list(rows[0]), GLOBAL.FIELDNAMES)
        keys = [(row["assertion_id"], row["image_url"]) for row in rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(
            rows,
            sorted(
                rows,
                key=lambda row: (
                    row["source_id"],
                    row["country_code"],
                    row["date_iso"],
                    row["assertion_id"],
                    row["image_url"],
                ),
            ),
        )
        self.assertEqual({row["embedding_allowed"] for row in rows}, {"false"})
        self.assertEqual({row["pixel_bytes_packaged"] for row in rows}, {"false"})
        self.assertEqual({row["local_cache_path"] for row in rows}, {""})
        self.assertEqual(
            {row["image_sha256_status"] for row in rows},
            {GLOBAL.IMAGE_SHA256_STATUS},
        )
        self.assertEqual(
            {row["image_fetch_policy"] for row in rows},
            {GLOBAL.IMAGE_FETCH_POLICY},
        )
        self.assertEqual(
            {row["placement_status"] for row in rows},
            {GLOBAL.PLACEMENT_STATUS},
        )

    def test_generated_site_candidates_fail_closed_for_british_grid(self):
        rows = read_csv(ROOT / "data" / "global_source_site_candidates.csv")
        self.assertEqual(list(rows[0]), GLOBAL.SITE_FIELDNAMES)
        suspicious = {"TV2010", "HU2020", "NL2018"}
        self.assertFalse(
            suspicious.intersection(row["coordinate_reference_text"] for row in rows)
        )
        method_counts = Counter(row["coordinate_method"] for row in rows)
        self.assertTrue(method_counts)
        for row in rows:
            method = row["coordinate_method"].lower()
            if "bng" not in method and "os_grid" not in method:
                continue
            self.assertEqual(row["country_code"], "GB")
            self.assertTrue(
                GLOBAL.is_within_gb(
                    float(row["latitude"]),
                    float(row["longitude"]),
                ),
                row,
            )


if __name__ == "__main__":
    unittest.main()
