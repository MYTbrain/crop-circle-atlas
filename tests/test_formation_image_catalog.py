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
        self.assertGreaterEqual(metadata["unique_image_count"], 475)
        self.assertGreaterEqual(metadata["formation_count"], 260)
        for formation_id, image in relationships:
            self.assertTrue(formation_id.startswith("cc_"))
            self.assertTrue(image["image_url"].startswith("https://iccra.org/"))
            self.assertNotIn("cache_path", image)
            self.assertNotIn("local_path", image)
            self.assertEqual(image["rights_status"], "not_cleared")


if __name__ == "__main__":
    unittest.main()
