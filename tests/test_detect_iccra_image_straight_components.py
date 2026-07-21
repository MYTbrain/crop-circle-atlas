import hashlib
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from scripts.detect_iccra_image_straight_components import (
    AXIS_REFERENCE,
    analyze_image,
    analyze_inventory,
    candidate_score,
)


class ConservativeTierTests(unittest.TestCase):
    def test_same_features_are_stricter_for_photograph_than_diagram(self):
        inputs = (0.34, 1.0, 0.25, 4, 10.0)
        diagram_score, diagram_tier = candidate_score("diagram", *inputs)
        photo_score, photo_tier = candidate_score("photograph_or_unspecified", *inputs)
        self.assertAlmostEqual(diagram_score, photo_score)
        self.assertEqual(diagram_tier, "medium")
        self.assertEqual(photo_tier, "low")

    def test_synthetic_horizontal_line_reports_image_axis_only(self):
        image = np.full((256, 256), 255, dtype=np.uint8)
        cv2.line(image, (20, 128), (236, 128), 0, 5)
        result = analyze_image(image, "diagram")
        self.assertEqual(result["analysis_status"], "analyzed_private_cache")
        axis = float(result["dominant_axis_image_deg"])
        self.assertLess(min(abs(axis), abs(axis - 180)), 2.0)
        self.assertIn(result["straight_component_tier"], {"high", "medium"})
        self.assertNotIn("azimuth", result)


class InventoryCoverageTests(unittest.TestCase):
    def test_cached_and_external_rows_are_both_accounted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "private.png"
            image = np.full((128, 128), 255, dtype=np.uint8)
            cv2.line(image, (10, 64), (118, 64), 0, 4)
            self.assertTrue(cv2.imwrite(str(source), image))
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            common = {
                "assertion_ids": "iccra_test",
                "source_page_url": "https://iccra.example/report",
                "image_kind": "diagram",
                "fetch_policy": "robots_allowed_private_raw_cache",
                "public_redistribution_status": "not_cleared",
            }
            rows = [
                {
                    **common,
                    "image_link_id": "cached",
                    "image_url": "https://iccra.example/private.png",
                    "is_iccra_hosted": "True",
                    "http_status": "200",
                    "sha256": digest,
                    "cache_path": "private.png",
                },
                {
                    **common,
                    "image_link_id": "external",
                    "image_url": "https://external.example/image.jpg",
                    "is_iccra_hosted": "False",
                    "http_status": "",
                    "sha256": "",
                    "cache_path": "",
                },
            ]
            output, metrics = analyze_inventory(rows, root=root)
            self.assertEqual(len(output), 2)
            self.assertEqual(output[0]["analysis_status"], "analyzed_private_cache")
            self.assertEqual(output[1]["analysis_status"], "external_not_fetched")
            self.assertEqual(output[0]["axis_reference"], AXIS_REFERENCE)
            self.assertEqual(output[0]["geographic_azimuth_qualified"], "false")
            self.assertNotIn("cache_path", output[0])
            self.assertEqual(metrics["successfully_cached_hosted_rows"], 1)
            self.assertEqual(metrics["analyzed_rows"], 1)
            self.assertEqual(metrics["cached_row_coverage"], 1.0)
            self.assertFalse(metrics["qualification_boundary"]["source_pixel_output"])
            self.assertFalse(metrics["qualification_boundary"]["derived_pixel_output"])


if __name__ == "__main__":
    unittest.main()
