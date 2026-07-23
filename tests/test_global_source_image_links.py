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
        generated_rows = [row for row in rows if row["source_id"] in GLOBAL.SOURCE_NAMES]
        self.assertEqual(
            {row["image_sha256_status"] for row in generated_rows},
            {GLOBAL.IMAGE_SHA256_STATUS},
        )
        self.assertEqual(
            {row["image_fetch_policy"] for row in generated_rows},
            {GLOBAL.IMAGE_FETCH_POLICY},
        )
        self.assertEqual(
            {row["placement_status"] for row in generated_rows},
            {GLOBAL.PLACEMENT_STATUS},
        )

        legacy_expected = {
            "gimg_76c0a68f0d54c95d9786": (
                "cc_96878ba19702",
                "be35cfff95a8b909c5cd529df2021fc10ed41160a242c8d1d0212cd03c5002ab",
                "reviewed_footprint_rights_gated",
            ),
            "gimg_bd24fa34504e24f4cdc8": (
                "cc_9275734c8913",
                "65d1a3725f6d0df19554060a6c11575b982133bb3e6cddfd80b037f6743cf13a",
                "reviewed_footprint_rights_gated",
            ),
            "gimg_f424af5205b5f4c976be": (
                "cc_6f84d7030b21",
                "764a884c34f9f46cc92c6dbe20990b271726e5e81fc59998a50ea07cbb54fc87",
                "reviewed_footprint_rights_gated",
            ),
            "gimg_d9a1273754ef503e0d4e": (
                "cc_d777276e6710",
                "6da12427612e6949683d713a851a42dcd2bee8d716cb15bb1a8d12acca477ed3",
                "reviewed_footprint_rights_gated",
            ),
            "gimg_5e0dc51aa8d7b1f8ef9a": (
                "cc_69e673eaab9f",
                "989cdf3ecd98dfdac5da2dbed4d0258a12202a30d7c0dee9c13029e8e3317c2f",
                "reviewed_footprint_rights_gated",
            ),
            "gimg_596ea5ce4715a4fb8eb2": (
                "cc_863c8e5d3833",
                "81ac915513b0a3cd34242895aad5c990af60f7531e1f5fa9385ce40a5f08e8ba",
                "source_link_only_not_georegistered",
            ),
            "gimg_fc03b48166290429fcfc": (
                "cc_721e4b7f87f1",
                "44df5d73d112236849bb4990e25c7b3212300a061f2fe2a81947f08b82a88df1",
                "source_link_only_not_georegistered",
            ),
            "gimg_1a2e42f230099885d180": (
                "cc_ff64c3c47cb1",
                "c06d03f31cb22359860f671d9f1e78a3d88f6bd52cf957e83c7439ffb1e6dbba",
                "reviewed_footprint_rights_gated",
            ),
            "gimg_dc845a0e9f104fa45e1b": (
                "cc_ff64c3c47cb1",
                "7015f10d5e10f839d1deab4d73c4deba3eb099d68c1f1cf00faf61ed690d9279",
                "source_link_only_not_georegistered",
            ),
            "gimg_efc65ed459ed8472833c": (
                "cc_b976f6d9a82c",
                "f82d6c1450519d0b00159158822dea62728488cd2cd9dd03b2aba13936598de1",
                "source_link_only_not_georegistered",
            ),
        }
        legacy_rows = {
            row["image_link_id"]: row
            for row in rows
            if row["image_link_id"] in legacy_expected
        }
        self.assertEqual(set(legacy_rows), set(legacy_expected))
        for image_link_id, (formation_id, sha256, placement_status) in legacy_expected.items():
            row = legacy_rows[image_link_id]
            self.assertEqual(row["source_id"], "legacy_kml_review")
            self.assertEqual(row["formation_id"], formation_id)
            self.assertEqual(row["image_sha256"], sha256)
            self.assertEqual(
                row["image_sha256_status"], "case_specific_sha256_verified"
            )
            self.assertEqual(row["placement_status"], placement_status)
            self.assertEqual(row["embedding_allowed"], "false")

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
