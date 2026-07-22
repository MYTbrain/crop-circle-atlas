import csv
import re
import unittest
from pathlib import Path

from scripts.build_commons_crop_circle_images import (
    ASSERTION_FIELDS,
    IMAGE_FIELDS,
    classify_image,
    parse_capture_date,
)
from scripts.build_dataset import load_commons_event_assertions


ROOT = Path(__file__).resolve().parents[1]
IMAGES_PATH = ROOT / "data" / "commons_crop_circle_images.csv"
ASSERTIONS_PATH = ROOT / "data" / "commons_crop_circle_assertions.csv"
FORMATIONS_PATH = ROOT / "data" / "formations.csv"


def load_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


class CommonsCropCircleImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image_fields, cls.images = load_csv(IMAGES_PATH)
        cls.assertion_fields, cls.assertions = load_csv(ASSERTIONS_PATH)
        _, cls.formations = load_csv(FORMATIONS_PATH)

    def test_snapshot_has_documented_schemas_and_material_non_us_coverage(self):
        self.assertEqual(self.image_fields, list(IMAGE_FIELDS))
        self.assertEqual(self.assertion_fields, list(ASSERTION_FIELDS))
        self.assertGreaterEqual(len(self.images), 30)
        self.assertGreaterEqual(len({row["country_code"] for row in self.images}), 8)
        self.assertNotIn("US", {row["country_code"] for row in self.images})
        self.assertNotIn("", {row["country_code"] for row in self.images})

    def test_every_image_has_remote_provenance_rights_dimensions_and_hash(self):
        ids = set()
        urls = set()
        for row in self.images:
            self.assertNotIn(row["commons_image_id"], ids)
            ids.add(row["commons_image_id"])
            self.assertNotIn(row["original_file_url"], urls)
            urls.add(row["original_file_url"])
            self.assertRegex(row["commons_image_id"], r"^commons_img_[0-9a-f]{16}$")
            self.assertTrue(row["commons_page_url"].startswith("https://commons.wikimedia.org/wiki/File:"))
            self.assertTrue(row["original_file_url"].startswith("https://upload.wikimedia.org/"))
            self.assertGreater(int(row["width_px"]), 0)
            self.assertGreater(int(row["height_px"]), 0)
            self.assertGreater(int(row["byte_size"]), 0)
            self.assertRegex(row["sha1"], r"^[0-9a-f]{40}$")
            self.assertEqual(row["hash_algorithm"], "SHA-1 (Wikimedia original-file revision)")
            self.assertTrue(row["author"])
            self.assertTrue(row["license_short_name"])
            self.assertEqual(row["open_license_verified"], "true")
            self.assertEqual(row["embedding_allowed"], "true")
            self.assertEqual(row["pixel_storage_policy"], "remote_link_only_no_pixels_packaged")

    def test_assertion_matches_resolve_to_committed_images_and_formations(self):
        image_ids = {row["commons_image_id"] for row in self.images}
        formation_ids = {row["formation_id"] for row in self.formations}
        matched_image_ids = set()
        for row in self.assertions:
            self.assertIn(row["commons_image_id"], image_ids)
            self.assertTrue(row["commons_page_url"].startswith("https://commons.wikimedia.org/wiki/File:"))
            if row["matched_formation_id"]:
                self.assertIn(row["matched_formation_id"], formation_ids)
                matched_image_ids.add(row["commons_image_id"])
                self.assertIn(
                    row["match_method"],
                    {
                        "exact_place_and_date",
                        "place_and_year_candidate",
                        "coordinate_and_date_candidate",
                        "reviewed_same_event_later_documentation",
                    },
                )
            else:
                self.assertEqual(row["match_status"], "no_defensible_existing_formation_match")
        self.assertGreaterEqual(len(matched_image_ids), 20)

    def test_snapshot_exposes_geotagged_aerial_registration_candidates(self):
        candidates = [
            row for row in self.images
            if row["overlay_readiness"] == "geotagged_aerial_landmark_candidate"
        ]
        self.assertGreaterEqual(len(candidates), 10)
        for row in candidates:
            self.assertEqual(row["image_kind"], "aerial_photograph")
            self.assertTrue(row["latitude"])
            self.assertTrue(row["longitude"])
            self.assertGreaterEqual(float(row["latitude"]), -90)
            self.assertLessEqual(float(row["latitude"]), 90)
            self.assertGreaterEqual(float(row["longitude"]), -180)
            self.assertLessEqual(float(row["longitude"]), 180)

    def test_approximate_year_in_title_overrides_later_scan_metadata(self):
        metadata = {"DateTimeOriginal": {"value": "2019-01-30"}}
        value, precision, source = parse_capture_date(
            metadata,
            "File:Alton Barnes crop circle c. 1995-1.jpg",
        )
        self.assertEqual((value, precision), ("1995", "year"))
        self.assertEqual(source, "commons_file_title_approximate_year")

    def test_diagrams_and_derived_art_are_not_classified_as_photographs(self):
        self.assertEqual(
            classify_image(
                "File:Barbury Crop Circle es2.png",
                "Map of the crop circle; made in Paint; Agricultural diagrams",
                "image/png",
            ),
            "diagram_or_illustration",
        )
        forbidden = re.compile(r"diagram|coloring book|barnstar|microscopy", flags=re.I)
        for row in self.images:
            self.assertIsNone(forbidden.search(f"{row['description']} {row['commons_categories']}"))

    def test_distinct_diessenhofen_event_is_not_merged_with_the_june_report(self):
        assertions = load_commons_event_assertions()
        self.assertEqual(len(assertions), 1)
        event = assertions[0]
        self.assertEqual(event["assertion_id"], "commons_event_diessenhofen_20080715")
        self.assertEqual(event["date_iso"], "2008-07-15")
        self.assertEqual(event["place"], "Diessenhofen")
        self.assertEqual(len(event["image_urls"].split(";")), 9)


if __name__ == "__main__":
    unittest.main()
