import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IdParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids = []; self.scripts = []; self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"): self.ids.append(values["id"])
        if tag == "script" and values.get("src"): self.scripts.append((values["src"], values.get("type")))
        if tag == "a" and values.get("href"): self.links.append(values["href"])


class GeolocationReviewerContractTests(unittest.TestCase):
    def test_reviewer_has_complete_human_gate_and_no_browser_credentials(self):
        html = (ROOT / "web" / "geolocation-review.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "geolocation-review.mjs").read_text(encoding="utf-8")
        css = (ROOT / "web" / "geolocation-review.css").read_text(encoding="utf-8")
        parser = IdParser(); parser.feed(html)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        referenced = set(re.findall(r'\$\("([A-Za-z][A-Za-z0-9_-]*)"\)', js))
        self.assertEqual(set(), referenced - set(parser.ids))
        self.assertTrue(any(
            src.partition("?")[0] == "geolocation-review.mjs" and script_type == "module"
            for src, script_type in parser.scripts
        ))
        self.assertIn("georef.html", parser.links)
        for required in (
            "formationId", "jobId", "searchPolygon", "candidateSheet", "imageryVintage",
            "correspondences", "homographyJson", "cornerJson", "controlsJson", "checkpointsJson",
            "registrationMetrics", "uncertainty", "saveReview", "exportReview", "generateKmz",
            "rightsStatus", "publicationEligible",
        ):
            self.assertIn(required, parser.ids)
        for decision in ("accepted", "downgraded", "rejected", "deferred", "unresolved"):
            self.assertIn(f'value="{decision}"', html)
        self.assertIn("resize:horizontal", css)
        self.assertIn("Control residuals and independent checkpoint errors", html)
        self.assertIn("locality search area", html)
        self.assertIn("fail closed", js)
        for forbidden in ("apiKey", "accessToken", "USGS_M2M_TOKEN", "USGS_M2M_USERNAME"):
            self.assertNotIn(forbidden, html)
            self.assertNotIn(forbidden, js)

    def test_atlas_links_to_reviewer(self):
        atlas = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        georef = (ROOT / "web" / "georef.html").read_text(encoding="utf-8")
        self.assertIn('href="geolocation-review.html"', atlas)
        self.assertIn('href="geolocation-review.html"', georef)


if __name__ == "__main__":
    unittest.main()
