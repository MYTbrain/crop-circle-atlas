import json
import unittest
from pathlib import Path

from scripts.build_formation_image_catalog import (
    load_reviewed_us_archive_images,
)


ROOT = Path(__file__).resolve().parents[1]


class ReviewedUsArchiveImageTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(
            (ROOT / "data" / "reviewed_us_archive_image_links.json").read_text(
                encoding="utf-8"
            )
        )
        self.rows = load_reviewed_us_archive_images()

    def test_seed_contains_only_reviewed_link_only_relationships(self):
        self.assertGreaterEqual(len(self.payload["reports"]), 20)
        self.assertGreaterEqual(len(self.rows), 50)
        self.assertEqual(len(self.rows), len({row["image_url"] for row in self.rows}))
        self.assertTrue(all(row["formation_id"].startswith("cc_") for row in self.rows))
        self.assertTrue(all(row["assertion_id"] for row in self.rows))
        self.assertTrue(all(row["image_url"].startswith("https://") for row in self.rows))
        self.assertTrue(all(row["image_http_status"] == "200" for row in self.rows))
        self.assertTrue(all(row["embedding_allowed"] == "false" for row in self.rows))
        self.assertTrue(all(row["pixel_bytes_packaged"] == "false" for row in self.rows))
        self.assertTrue(
            all(row["placement_status"] == "source_link_only_not_georegistered" for row in self.rows)
        )

    def test_seed_formation_ids_are_canonical_us_reports(self):
        import csv

        with (ROOT / "data" / "formations.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            formations = {row["formation_id"]: row for row in csv.DictReader(handle)}
        for report in self.payload["reports"]:
            formation = formations[report["formation_id"]]
            self.assertEqual(formation["country_code"], "US")
            self.assertIn(report["assertion_id"], formation["assertion_ids"].split("; "))

    def test_known_newly_recovered_galleries_are_present(self):
        by_id = {report["formation_id"]: report for report in self.payload["reports"]}
        self.assertEqual(len(by_id["cc_cee3a40aace5"]["image_urls"]), 8)
        self.assertEqual(len(by_id["cc_d77797cdea69"]["image_urls"]), 6)
        self.assertEqual(len(by_id["cc_74854ad00686"]["image_urls"]), 3)


if __name__ == "__main__":
    unittest.main()
