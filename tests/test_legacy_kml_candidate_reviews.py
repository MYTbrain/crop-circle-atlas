import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.validate_legacy_kml_candidate_reviews import validate_reviews


ROOT = Path(__file__).resolve().parents[1]


class LegacyKmlCandidateReviewTests(unittest.TestCase):
    def setUp(self):
        self.reviews = json.loads(
            (ROOT / "data" / "legacy_kml_candidate_reviews.json").read_text(encoding="utf-8")
        )
        self.candidates = json.loads(
            (ROOT / "data" / "legacy_kml_candidates.json").read_text(encoding="utf-8")
        )

    def test_house_springs_is_a_fail_closed_candidate_field(self):
        self.assertEqual(validate_reviews(self.reviews, self.candidates), {"candidate_field": 4})
        record = next(
            item
            for item in self.reviews["records"]
            if item["legacy_candidate_id"] == "lkml_8045474ba5b89fbf"
        )
        self.assertEqual(record["legacy_candidate_id"], "lkml_8045474ba5b89fbf")
        self.assertEqual(record["outcome"], "candidate_field")
        self.assertEqual(record["source_photo_status"], "no independent formation photograph preserved")
        self.assertFalse(record["alignment_eligible"])
        self.assertFalse(record["overlay_eligible"])
        self.assertFalse(record["publication_eligible"])

    def test_review_cannot_promote_or_reference_an_unknown_candidate(self):
        for field in ("alignment_eligible", "overlay_eligible", "publication_eligible"):
            changed = deepcopy(self.reviews)
            changed["records"][0][field] = True
            with self.assertRaises(ValueError):
                validate_reviews(changed, self.candidates)
        changed = deepcopy(self.reviews)
        changed["records"][0]["legacy_candidate_id"] = "lkml_unknown"
        with self.assertRaises(ValueError):
            validate_reviews(changed, self.candidates)

    def test_bounded_batch_records_distinct_fail_closed_outcomes(self):
        reviewed = {
            item["legacy_candidate_id"]: item for item in self.reviews["records"]
        }
        expected = {
            "lkml_8045474ba5b89fbf",
            "lkml_2581ddcf6d36fefd",
            "lkml_9da2ff67b695b8e2",
            "lkml_0652bc310cbdd4b1",
        }
        self.assertEqual(set(reviewed), expected)
        self.assertEqual({reviewed[item]["outcome"] for item in expected}, {"candidate_field"})
        for item in expected:
            self.assertFalse(reviewed[item]["alignment_eligible"])
            self.assertFalse(reviewed[item]["overlay_eligible"])
            self.assertFalse(reviewed[item]["publication_eligible"])


if __name__ == "__main__":
    unittest.main()
