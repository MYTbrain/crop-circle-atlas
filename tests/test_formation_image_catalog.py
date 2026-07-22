import csv
import json
import unittest
from pathlib import Path

from scripts.build_formation_image_catalog import build_catalog


ROOT = Path(__file__).resolve().parents[1]


class FormationImageCatalogTests(unittest.TestCase):
    def test_generated_catalog_matches_the_committed_public_catalog(self):
        expected = build_catalog()
        actual = json.loads(
            (ROOT / "web" / "data" / "formation_images.json").read_text(encoding="utf-8")
        )
        self.assertEqual(actual, expected)

    def test_catalog_exposes_remote_links_without_private_cache_paths(self):
        payload = build_catalog()
        metadata = payload["metadata"]
        relationships = [
            (formation_id, image)
            for formation_id, images in payload["images_by_formation"].items()
            for image in images
        ]
        unique_urls = {image["image_url"] for _, image in relationships}

        self.assertEqual(metadata["unique_image_count"], len(unique_urls))
        self.assertEqual(metadata["formation_image_link_count"], len(relationships))
        self.assertEqual(metadata["formation_count"], len(payload["images_by_formation"]))
        self.assertGreaterEqual(metadata["unique_image_count"], 3000)
        self.assertGreaterEqual(metadata["formation_count"], 1800)
        self.assertGreaterEqual(metadata["non_us_unique_image_count"], 2500)
        self.assertGreater(metadata["unknown_country_unique_image_count"], 0)
        self.assertGreater(metadata["unverified_unique_image_link_count"], 0)
        self.assertGreaterEqual(metadata["rights_gated_unique_image_count"], 2500)
        self.assertGreaterEqual(
            metadata["source_link_counts"].get("Wikimedia Commons", 0), 11
        )
        for formation_id, image in relationships:
            self.assertTrue(formation_id.startswith("cc_"))
            self.assertTrue(image["image_url"].startswith("https://"))
            self.assertNotIn("cache_path", image)
            self.assertNotIn("local_path", image)
            self.assertFalse(image["pixel_bytes_packaged"])

        commons = [
            image for _, image in relationships
            if image["source_name"] == "Wikimedia Commons"
        ]
        self.assertGreaterEqual(len(commons), 2)
        self.assertTrue(all(image["embedding_allowed"] for image in commons))
        self.assertTrue(all(image["license_url"].startswith("https://") for image in commons))
        diessenhofen = payload["images_by_formation"]["cc_2deeb6879ebf"]
        self.assertEqual(len(diessenhofen), 9)
        self.assertEqual(
            sum(image["placement_status"] == "mapped_overlay" for image in diessenhofen),
            1,
        )

        rights_gated = [
            image for _, image in relationships
            if image["pixel_display_policy"] == "link_only_rights_gated"
        ]
        self.assertGreaterEqual(len(rights_gated), 2500)
        self.assertTrue(all(not image["embedding_allowed"] for image in rights_gated))

    def test_public_entity_image_counts_include_global_archive_relationships(self):
        payload = build_catalog()
        with (ROOT / "data" / "formations.csv").open(
            newline="", encoding="utf-8-sig"
        ) as handle:
            formations = {row["formation_id"]: row for row in csv.DictReader(handle)}
        for formation_id, images in payload["images_by_formation"].items():
            self.assertGreaterEqual(
                int(formations[formation_id]["source_image_count"]), len(images)
            )
            self.assertEqual(
                formations[formation_id]["has_source_images"],
                "yes_linked_rights_unverified",
            )


if __name__ == "__main__":
    unittest.main()
