import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import source_expansion as sx


class SourceExpansionParserTests(unittest.TestCase):
    def test_connector_emits_metadata_only_and_parses_near_alias(self):
        body = b"""
        <html><body>
          <a href='waden/waden2026a.html'><img src='photo.jpg'></a>
          <a href='waden/waden2026a.html'>Waden Hill, Nr Avebury, Wiltshire. Reported 29th April</a>
          <a href='z/z2026a.html'>Zurcher Weinland, Switzerland. Reported 23rd June</a>
        </body></html>
        """
        rows = sx.parse_connector_page(body, "https://cropcircleconnector.com/2026/May2026.html")
        self.assertEqual(2, len(rows))
        self.assertEqual("2026-04-29", rows[0]["date_iso"])
        self.assertEqual("Avebury", rows[0]["alternate_place"])
        self.assertEqual("Switzerland", rows[1]["country"])
        self.assertTrue(all(not row["thumbnail_url"] for row in rows))
        self.assertTrue(all(row["assertion_id"].startswith("sx_connector_") for row in rows))

    def test_dcca_numbered_anchor(self):
        body = b"<a href='hoeven/hoeven-uk.htm'>Hoeven (2), Noord-Brabant, 16-05-2012</a>"
        rows = sx.parse_dcca_page(body, "https://www.dcca.nl/2012/2012-uk.htm")
        self.assertEqual(1, len(rows))
        self.assertEqual("Hoeven (2)", rows[0]["place"])
        self.assertEqual("NL", rows[0]["country_code"])
        self.assertEqual("2012-05-16", rows[0]["date_iso"])

    def test_cccrn_never_substitutes_newsletter_date(self):
        undated = b"<h1>CCCRN NEWS - August 20, 2003</h1><p>Formation Reports #9 - 12 - Saskatchewan</p>"
        self.assertEqual([], sx.parse_cccrn_detail(undated, "https://www.ufobc.ca/x.htm"))
        exact = b"""
        <h1>FORMATION REPORT #18 (2003) - ST. PAUL, ALBERTA</h1>
        <p>The formation was originally first found by the farmer on September 10, 2003.</p>
        """
        rows = sx.parse_cccrn_detail(exact, "https://www.ufobc.ca/report.htm")
        self.assertEqual("2003-09-10", rows[0]["date_iso"])

    def test_reconciliation_records_alias_without_rewriting_source_geography(self):
        baseline = [{"assertion_id": "a_base", "year": "2026", "month": "5", "day": "22",
                     "place": "Mere", "region": "Wiltshire", "country": "England", "country_code": "GB"}]
        row = sx.assertion_template("connector", "https://example/index", "https://example/record", 1,
                                    2026, 5, 22, "2026-05-22", "day", "White Sheet Downs",
                                    "Wiltshire", "England", "GB", "White Sheet Downs, Nr Mere, Wiltshire. Reported 22nd May")
        row["alternate_place"] = "Mere"
        summary = sx.reconcile_rows([row], baseline)
        self.assertEqual("alias_overlap_not_merged", row["canonical_match_status"])
        self.assertEqual("White Sheet Downs", row["place"])
        self.assertEqual("Wiltshire", row["region"])
        self.assertEqual("a_base", row["matched_baseline_assertion_id"])
        self.assertEqual(0, summary["exact_overlap_normalized_keys"])

    def test_designators_and_explicit_non_gb_countries_are_preserved(self):
        dcca = sx.parse_dcca_page(
            b"<a href='a.htm'>Beilen (1), Drenthe, 10-07-1997</a><a href='b.htm'>Beilen (2), Drenthe, 10-07-1997</a>",
            "https://www.dcca.nl/1997/1997-uk.htm",
        )
        self.assertEqual({"Beilen (1)", "Beilen (2)"}, {row["place"] for row in dcca})
        connector = sx.parse_connector_page(
            b"<a href='a.htm'>Turija, Serbia. Reported 8th June.</a><a href='b.htm'>Sofia, Bulgaria. Reported 5th July.</a>",
            "https://cropcircleconnector.com/2017/June2017.html",
        )
        self.assertEqual({"RS", "BG"}, {row["country_code"] for row in connector})

    def test_connector_default_country_is_corrected_by_unique_baseline_geography(self):
        body = b"""
        <html><body><a href='Rauwiller/Rauwiller2015a.html'>
        Rauwiller, nr Sarrebourg, Alsace Bossue. Reported 11th June.
        </a></body></html>
        """
        rows = sx.parse_connector_page(
            body,
            "https://cropcircleconnector.com/2015/June2015.html",
        )
        self.assertEqual(1, len(rows))
        self.assertEqual("GB", rows[0]["country_code"])
        baseline = [{
            "assertion_id": "a_rauwiller_fr",
            "year": "2015",
            "month": "6",
            "day": "11",
            "place": "Rauwiller",
            "region": "Bas-Rhin",
            "country": "France",
            "country_code": "FR",
        }]
        sx.reconcile_rows(rows, baseline)
        self.assertEqual("France", rows[0]["country"])
        self.assertEqual("FR", rows[0]["country_code"])
        self.assertEqual("Bas-Rhin", rows[0]["region"])
        self.assertEqual(
            "baseline_geography_correction",
            rows[0]["canonical_match_status"],
        )
        self.assertEqual(
            "a_rauwiller_fr",
            rows[0]["matched_baseline_assertion_id"],
        )
        self.assertIn("Alsace Bossue", rows[0]["source_listing_text"])

    def test_committed_artifacts_are_internally_consistent(self):
        assertions_path = ROOT / "data" / "source_expansion_assertions.csv"
        reconciliation_path = ROOT / "data" / "source_expansion_reconciliation.json"
        if not assertions_path.exists() or not reconciliation_path.exists():
            self.skipTest("source-expansion artifacts have not been generated")
        with assertions_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), reconciliation["yield"]["expansion_assertions"])
        self.assertEqual(len(rows), len({row["assertion_id"] for row in rows}))
        self.assertTrue(all(not row.get("thumbnail_url") and not row.get("image_urls") for row in rows))
        self.assertTrue(all(row["source_record_url"] and row["rights_scope"] for row in rows))

    def test_private_cache_preflight_fails_closed_on_missing_or_tampered_input(self):
        sx.RAW.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=sx.RAW) as directory:
            path = Path(directory) / "page.html"
            relative = path.relative_to(sx.ROOT).as_posix()
            base = {
                "source_id": "connector",
                "fetch_kind": "season_event_index",
                "http_status": "200",
                "url": "https://example.test/season.html",
                "cache_path": relative,
                "bytes": "3",
                "sha256": hashlib.sha256(b"abc").hexdigest(),
            }
            with self.assertRaisesRegex(ValueError, "missing_cache_file"):
                sx.validate_manifest_cache([base])
            path.write_bytes(b"abc")
            sx.validate_manifest_cache([base])
            path.write_bytes(b"abd")
            with self.assertRaisesRegex(ValueError, "sha256_mismatch"):
                sx.validate_manifest_cache([base])


if __name__ == "__main__":
    unittest.main()
