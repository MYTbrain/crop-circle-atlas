import json
from copy import deepcopy
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.import_legacy_kml_candidates import build_payload, validate_payload


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA256 = "7f4d8fff89a59afb995c78ef82481439ace8ab5eb77e9e708a9a25b222724be8"
RELEVANT_KML_HASHES = {
    "4685872076905d54474dad7256e5e5e297ebea82e1e3eb93b13edf457533f9c7",
    "bbe92b750c5124d2be310695de1ae17bbfd55451210ca26bcffc983d6e902b53",
    "7f370023b5b0919d1801fedf0df184a05aba80b6756acea4fa38de56c0384b54",
    "ec948104c4e51f4881fc3cdd0ca4ee36a58338cb17b1b2281a47f5b52b6047e5",
}


def kml_document(placemarks: str, extra: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <name>Crop Circle Collection</name>
  {placemarks}
  {extra}
</Document></kml>"""


def placemark(name: str, longitude: float, latitude: float, description: str) -> str:
    return f"""<Placemark>
  <name>{name}</name>
  <description><![CDATA[{description}]]></description>
  <LookAt><longitude>{longitude + 0.001}</longitude><latitude>{latitude}</latitude>
    <heading>12</heading><range>800</range><tilt>25</tilt></LookAt>
  <Point><coordinates>{longitude},{latitude},0</coordinates></Point>
</Placemark>"""


class LegacyKmlImporterTests(unittest.TestCase):
    def test_synthetic_archive_is_inert_bounded_and_fail_closed(self):
        first = placemark(
            "Darfield crop circle",
            -1.356902,
            53.531366,
            '<img src="https://example.invalid/remote.jpg"> Source '
            '<a href="https://example.invalid/report">report</a>',
        )
        second = placemark(
            "Alien Crop Circles! (3 of 4)",
            -1.356884,
            53.531784,
            "Nearby legacy point",
        )
        irrelevant = placemark("Ordinary landmark", 10.0, 20.0, "Not crop evidence")
        network_link = (
            "<NetworkLink><name>remote</name><Link>"
            "<href>https://example.invalid/live.kml</href></Link>"
            + placemark("Crop Circle hidden in NetworkLink", 11.0, 21.0, "must skip")
            + "</NetworkLink>"
        )
        ambiguous = """<Placemark><name>Ambiguous Crop Circle</name>
  <Point><coordinates>-2,52,0</coordinates></Point>
  <Point><coordinates>-3,53,0</coordinates></Point></Placemark>"""
        nested = kml_document(
            placemark("Firefox Crop Circles", -123.0, 44.0, "Constructed browser logo")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "fixture.kml.zip"
            nested_path = Path(temp_dir) / "nested.kmz"
            with zipfile.ZipFile(nested_path, "w") as nested_archive:
                nested_archive.writestr("doc.kml", nested)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "132_CropCircleCollection.kml",
                    kml_document(first + second + ambiguous, network_link),
                )
                archive.writestr(
                    "unrelated.kml",
                    kml_document(irrelevant).replace(
                        "Crop Circle Collection", "Ordinary Landmark Collection"
                    ),
                )
                archive.writestr("TopTenFindsinGoogleEarth.kmz", nested_path.read_bytes())
                archive.writestr("remote.url", "URL=https://example.invalid/shortcut")
                archive.writestr("../unsafe.kml", kml_document(first))

            payload = build_payload(archive_path)

        self.assertEqual(payload["summary"]["candidate_count"], 3)
        self.assertEqual(payload["summary"]["possible_duplicate_group_count"], 1)
        self.assertEqual(payload["audit"]["network_links_skipped"], 1)
        self.assertEqual(payload["audit"]["url_shortcut_entries_skipped"], 1)
        self.assertEqual(payload["audit"]["unsafe_archive_paths_skipped"], 1)
        self.assertEqual(payload["audit"]["irrelevant_placemarks_skipped"], 1)
        self.assertEqual(
            payload["audit"]["crop_related_nonpoint_or_invalid_placemarks_skipped"],
            1,
        )
        self.assertFalse(payload["security_policy"]["archive_extraction_performed"])
        self.assertFalse(payload["security_policy"]["external_urls_visited"])
        self.assertFalse(payload["candidate_policy"]["automatic_site_promotion"])
        self.assertTrue(
            payload["candidate_policy"]["possible_duplicate_groups_are_not_automatic_merges"]
        )

        records = {record["placemark_name"]: record for record in payload["candidates"]}
        self.assertNotIn("<img", records["Darfield crop circle"]["description_inert_text"].lower())
        self.assertIn(
            "https://example.invalid/report",
            records["Darfield crop circle"]["original_url_strings"],
        )
        self.assertIn(
            "https://example.invalid/remote.jpg",
            records["Darfield crop circle"]["original_url_strings"],
        )
        self.assertNotIn("Ordinary landmark", records)
        self.assertNotIn("Crop Circle hidden in NetworkLink", records)
        self.assertNotIn("Ambiguous Crop Circle", records)
        self.assertFalse(
            any(
                "opengis.net" in url or "earth.google.com/kml" in url
                for record in records.values()
                for url in record["original_url_strings"]
            )
        )
        self.assertEqual(records["Darfield crop circle"]["source_archive_filename"], "fixture.kml.zip")
        self.assertEqual(records["Darfield crop circle"]["look_at"]["heading"], 12.0)
        self.assertEqual(records["Darfield crop circle"]["look_at"]["altitude"], None)
        self.assertTrue(records["Darfield crop circle"]["look_at_children"])
        self.assertEqual(records["Firefox Crop Circles"]["confidence_tier"], "tier_3_known_constructed_or_promotional")
        for record in payload["candidates"]:
            self.assertEqual(record["legacy_location_status"], "legacy_exact_field_candidate")
            self.assertEqual(record["review_status"], "queued_unverified")
            self.assertEqual(record["site_status"], "candidate_field_only")
            self.assertFalse(record["alignment_eligible"])
            self.assertFalse(record["overlay_eligible"])
            self.assertFalse(record["publication_eligible"])
            self.assertFalse(record["remote_content_executed"])
            self.assertFalse(record["network_links_executed"])

        mutations = (
            lambda changed: changed["candidates"][0].__setitem__("site_status", "accepted"),
            lambda changed: changed["candidates"][0].__setitem__("review_status", "accepted"),
            lambda changed: changed["candidate_policy"].__setitem__("automatic_site_promotion", True),
            lambda changed: changed["security_policy"].__setitem__("external_urls_visited", True),
            lambda changed: changed["summary"].__setitem__("overlay_count", 1),
        )
        for mutate in mutations:
            changed = deepcopy(payload)
            mutate(changed)
            with self.assertRaises(ValueError):
                validate_payload(changed)

    def test_cumulative_expanded_byte_limit_applies_across_nested_archives(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "bounded.kml.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("132_CropCircleCollection.kml", kml_document(""))
                archive.writestr("padding.bin", b"x" * 512)
            with patch(
                "scripts.import_legacy_kml_candidates.MAX_CUMULATIVE_EXPANDED_BYTES",
                100,
            ):
                with self.assertRaisesRegex(ValueError, "cumulative expanded-byte safety cap"):
                    build_payload(archive_path)

            with patch(
                "scripts.import_legacy_kml_candidates.MAX_SOURCE_ARCHIVE_BYTES",
                100,
            ):
                with self.assertRaisesRegex(ValueError, "source archive exceeds safety cap"):
                    build_payload(archive_path)

    def test_utf16_dtd_and_entity_document_is_rejected_before_parsing(self):
        malicious = """<?xml version="1.0" encoding="UTF-16"?>
<!DOCTYPE kml [<!ENTITY injected "Crop Circle">]>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <name>Crop Circle Collection</name><Placemark><name>&injected;</name>
  <Point><coordinates>-1,51,0</coordinates></Point></Placemark>
</Document></kml>""".encode("utf-16")
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "utf16.kml.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("132_CropCircleCollection.kml", malicious)
            payload = build_payload(archive_path)
        self.assertEqual(payload["summary"]["candidate_count"], 0)
        self.assertEqual(payload["audit"]["active_xml_documents_rejected"], 1)
        document = next(
            item for item in payload["kml_documents"] if item["active_xml_rejected"]
        )
        self.assertEqual(document["candidates_imported"], 0)

    def test_committed_archive_import_matches_audited_source_and_cannot_publish(self):
        payload = json.loads(
            (ROOT / "data" / "legacy_kml_candidates.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["source"]["archive_sha256"], ARCHIVE_SHA256)
        self.assertEqual(payload["source"]["archive_filename"], "Anomalies_.kml.zip")
        self.assertEqual(payload["source"]["archive_size_bytes"], 235329)
        self.assertEqual(payload["summary"]["candidate_count"], 27)
        self.assertEqual(payload["summary"]["possible_duplicate_group_count"], 4)
        self.assertEqual(payload["summary"]["possible_duplicate_member_count"], 8)
        for count_name in (
            "accepted_site_count",
            "overlay_count",
            "alignment_eligible_count",
            "publication_eligible_count",
        ):
            self.assertEqual(payload["summary"][count_name], 0)

        imported_documents = {
            document["kml_filename"]: document["kml_sha256"]
            for document in payload["kml_documents"]
            if document["candidates_imported"]
        }
        self.assertEqual(set(imported_documents.values()), RELEVANT_KML_HASHES)
        self.assertEqual(
            imported_documents,
            {
                "Anomalies_.kml/132_CropCircleCollection.kml": "4685872076905d54474dad7256e5e5e297ebea82e1e3eb93b13edf457533f9c7",
                "Anomalies_.kml/TopTenFindsinGoogleEarth.kmz!doc.kml": "7f370023b5b0919d1801fedf0df184a05aba80b6756acea4fa38de56c0384b54",
                "Anomalies_.kml/alien-crop-circles.kml": "bbe92b750c5124d2be310695de1ae17bbfd55451210ca26bcffc983d6e902b53",
                "Anomalies_.kml/crop-circles.kml": "ec948104c4e51f4881fc3cdd0ca4ee36a58338cb17b1b2281a47f5b52b6047e5",
            },
        )
        self.assertEqual(payload["audit"]["candidates_imported"], 27)
        self.assertEqual(payload["audit"]["network_links_skipped"], 21)
        self.assertGreaterEqual(payload["audit"]["url_shortcut_entries_skipped"], 2)
        self.assertEqual(payload["audit"]["url_strings_preserved_inert"], 56)

        priority_labels = {
            record["priority_label"]
            for record in payload["candidates"]
            if not record["priority_inherited_from_duplicate_group"]
        }
        for label in (
            "darfield",
            "panocchia",
            "house_springs_missouri",
            "hexton",
            "windmill_hill",
            "hackpen_hill",
            "waden_hill",
            "south_yorkshire_cluster",
        ):
            self.assertIn(label, priority_labels)

        records = {record["placemark_name"]: record for record in payload["candidates"]}
        exact_priority_records = {
            "Nice crop circle in Darfield, UK": (1, 53.53136557047451, -1.356902390606507),
            "Crop Circle Panocchia, Italy": (2, 44.68159555459062, 10.31721852521929),
            "Crop Circle near Hexton": (4, 51.94603793928447, -0.3915778131514003),
            "windmillhill cropcircle ghost from 2004": (5, 51.43459499120964, -1.874343072026605),
            "cropcircle cutted Hackpen Hill": (6, 51.47345414989942, -1.825380364348547),
            "jingjang cropcircle": (7, 51.42454302630362, -1.855548044334824),
        }
        for name, expected in exact_priority_records.items():
            record = records[name]
            self.assertEqual(
                (record["priority_rank"], record["latitude"], record["longitude"]),
                expected,
            )
        self.assertEqual(
            records["Nice crop circle in Darfield, UK"]["coordinate_original"],
            "-1.356902390606507,53.53136557047451,0",
        )
        firefox_modes = [
            (child["namespace"], child["text"])
            for child in records["Firefox Crop Circles"]["look_at_children"]
            if child["tag"] == "altitudeMode"
        ]
        self.assertEqual(
            firefox_modes,
            [
                ("http://www.opengis.net/kml/2.2", "relativeToGround"),
                ("http://www.google.com/kml/ext/2.2", "relativeToSeaFloor"),
            ],
        )

        groups = payload["possible_duplicate_groups"]
        grouped_names = [set(group["member_names"]) for group in groups]
        self.assertIn(
            {"Nice crop circle in Darfield, UK", "Alien Crop Circles! (3 of 4)"},
            grouped_names,
        )
        self.assertIn(
            {"Crop Circle Panocchia, Italy", "Alien Crop Circles! (2 of 4)"},
            grouped_names,
        )
        self.assertIn(
            {"Crop Circle #1 South of Barnsley", "Crop Circle #2 South of Barnsley"},
            grouped_names,
        )
        self.assertIn(
            {"Crop Circles ?", "Alien Crop Circles! (1 of 4)"},
            grouped_names,
        )
        for group in groups:
            self.assertEqual(group["review_status"], "unreviewed_do_not_merge")

        for record in payload["candidates"]:
            self.assertEqual(record["legacy_location_status"], "legacy_exact_field_candidate")
            self.assertEqual(record["coordinate_accuracy_status"], "legacy_point_precision_not_validated_accuracy")
            self.assertFalse(record["alignment_eligible"])
            self.assertFalse(record["overlay_eligible"])
            self.assertFalse(record["publication_eligible"])
            self.assertFalse(record["remote_content_executed"])
            self.assertFalse(record["network_links_executed"])
            self.assertNotIn("<img", record["description_inert_text"].lower())
            self.assertFalse(
                any(
                    "opengis.net" in url or "earth.google.com/kml" in url
                    for url in record["original_url_strings"]
                )
            )
            self.assertFalse(
                any("&lt;br&gt" in url or "&amp;" in url for url in record["original_url_strings"])
            )


if __name__ == "__main__":
    unittest.main()
