import csv
import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw

from scripts import generate_kml
from scripts.georeference_image import PUBLIC_RIGHTS, RegistrationError, export_registration
from scripts.ingest_georeference import ingest_registration


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_registration.json"


def make_source(path: Path) -> None:
    image = Image.new("RGB", (320, 240), "#10231f")
    draw = ImageDraw.Draw(image)
    for x in range(0, 321, 20):
        draw.line((x, 0, x, 239), fill=(60, 180, 150))
    for y in range(0, 241, 20):
        draw.line((0, y, 319, y), fill=(220, 100, 70))
    image.save(path, format="PNG", compress_level=9)


def write_registration(path: Path, asset_id: str, rights: dict) -> None:
    metadata = json.loads(FIXTURE.read_text(encoding="utf-8"))
    metadata["asset"]["asset_id"] = asset_id
    metadata["asset"]["rights"] = rights
    metadata["review"] = {
        "reviewer": "Synthetic QA reviewer",
        "reviewed_at": "2026-07-21T12:00:00Z",
        "visual_basemap_review_required": True,
    }
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


class GeoreferenceIngestTests(unittest.TestCase):
    def test_rights_enum_matches_combined_generator(self):
        self.assertEqual(PUBLIC_RIGHTS, generate_kml.AUTHORIZED_IMAGE_RIGHTS)

    def test_authorized_overlay_enters_combined_kmz_private_overlay_does_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "atlas"
            (repo / "data").mkdir(parents=True)
            (repo / "data" / "formations.csv").write_text(
                "formation_id,latitude,longitude\nsynthetic-formation,,\n", encoding="utf-8"
            )
            source = base / "source.png"
            make_source(source)

            authorized_input = base / "authorized.json"
            write_registration(authorized_input, "authorized-overlay", {
                "status": "cc_by",
                "holder": "Synthetic fixture creator",
                "license": "CC BY 4.0",
                "proof": "https://example.invalid/synthetic-license-proof",
                "public_derivative_export_allowed": True,
            })
            authorized_export = export_registration(
                authorized_input, source, base / "authorized-export",
                max_dimension=256, public_export=True,
            )
            authorized_row = ingest_registration(
                Path(authorized_export["paths"]["registration"]),
                Path(authorized_export["paths"]["png"]),
                repo_root=repo,
            )
            # Re-ingest is deterministic and idempotent.
            self.assertEqual(
                authorized_row,
                ingest_registration(
                    Path(authorized_export["paths"]["registration"]),
                    Path(authorized_export["paths"]["png"]),
                    repo_root=repo,
                ),
            )
            self.assertTrue((repo / authorized_row["local_path"]).is_file())
            self.assertEqual(authorized_row["rights_proof"], "https://example.invalid/synthetic-license-proof")

            private_input = base / "private.json"
            write_registration(private_input, "private-overlay", {
                "status": "local_analysis_only",
                "holder": "Synthetic fixture creator",
                "license": "",
                "proof": "",
                "public_derivative_export_allowed": False,
            })
            private_export = export_registration(
                private_input, source, base / "private-export", max_dimension=256,
            )
            private_row = ingest_registration(
                Path(private_export["paths"]["registration"]),
                Path(private_export["paths"]["png"]),
                repo_root=repo,
            )
            self.assertEqual(private_row["local_path"], "")

            with (repo / "data" / "image_assets.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["asset_id"] for row in rows], ["authorized-overlay", "private-overlay"])

            # Run the real combined generator against the ingested registry.
            (repo / "data" / "orientation_observations.csv").write_text("formation_id\n", encoding="utf-8")
            (repo / "web" / "data").mkdir(parents=True)
            previous_root = generate_kml.ROOT
            try:
                generate_kml.ROOT = repo
                with contextlib.redirect_stdout(io.StringIO()):
                    generate_kml.main()
            finally:
                generate_kml.ROOT = previous_root
            combined_from_generator = repo / "exports" / "crop_circle_atlas.kmz"
            with zipfile.ZipFile(combined_from_generator) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("doc.kml", archive.namelist())
                self.assertIn("assets/authorized-overlay.png", archive.namelist())
                self.assertFalse(any("private-overlay" in name for name in archive.namelist()))
                generated_kml = ET.fromstring(archive.read("doc.kml"))
            generated_overlays = generated_kml.findall(f".//{{{generate_kml.NS}}}GroundOverlay")
            self.assertEqual(len(generated_overlays), 1)
            self.assertEqual(generated_overlays[0].find(generate_kml.q("name")).text, "authorized-overlay")
            generated_description = generated_overlays[0].find(generate_kml.q("description")).text
            self.assertIn("Synthetic fixture creator", generated_description)
            self.assertIn("CC BY 4.0", generated_description)
            self.assertIn("https://example.invalid/synthetic-license-proof", generated_description)
            generated_rights = {
                node.get("name"): node.find(generate_kml.q("value")).text or ""
                for node in generated_overlays[0].findall(f".//{{{generate_kml.NS}}}Data")
            }
            self.assertEqual(generated_rights["rights_holder"], "Synthetic fixture creator")
            self.assertEqual(generated_rights["license"], "CC BY 4.0")
            self.assertEqual(generated_rights["rights_proof"], "https://example.invalid/synthetic-license-proof")
            self.assertEqual(generated_rights["source_url"], "https://example.invalid/synthetic-test-only")
            with (repo / "data" / "image_overlay_audit.csv").open(encoding="utf-8-sig", newline="") as handle:
                audit_rows = list(csv.DictReader(handle))
            self.assertIn({"asset_id": "authorized-overlay", "status": "included", "reason": ""}, audit_rows)
            self.assertIn({"asset_id": "private-overlay", "status": "excluded", "reason": "rights_not_publication_authorized"}, audit_rows)

            previous_root = generate_kml.ROOT
            try:
                generate_kml.ROOT = repo
                kml_root = ET.Element(generate_kml.q("kml"))
                document = ET.SubElement(kml_root, generate_kml.q("Document"))
                overlay_files, rejected = generate_kml.add_rights_cleared_overlays(document, rows, {"synthetic-formation"})
            finally:
                generate_kml.ROOT = previous_root
            self.assertEqual(len(overlay_files), 1)
            self.assertEqual(overlay_files[0][2], "authorized-overlay")
            self.assertEqual(rejected, [{
                "asset_id": "private-overlay",
                "status": "excluded",
                "reason": "rights_not_publication_authorized",
            }])

            kml_bytes = io.BytesIO()
            ET.ElementTree(kml_root).write(kml_bytes, encoding="utf-8", xml_declaration=True)
            combined = base / "combined.kmz"
            with zipfile.ZipFile(combined, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("doc.kml", kml_bytes.getvalue())
                for source_path, archive_name, _ in overlay_files:
                    archive.write(source_path, archive_name)
            with zipfile.ZipFile(combined) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("doc.kml", archive.namelist())
                self.assertIn(overlay_files[0][1], archive.namelist())
                self.assertFalse(any("private-overlay" in name for name in archive.namelist()))
                packaged_kml = ET.fromstring(archive.read("doc.kml"))
            overlays = packaged_kml.findall(f".//{{{generate_kml.NS}}}GroundOverlay")
            self.assertEqual(len(overlays), 1)
            self.assertEqual(overlays[0].find(generate_kml.q("name")).text, "authorized-overlay")
            self.assertIsNotNone(overlays[0].find(f".//{{{generate_kml.GX_NS}}}LatLonQuad"))

            invalid_rmse = dict(authorized_row)
            invalid_rmse["transform_rmse_m"] = ""
            previous_root = generate_kml.ROOT
            try:
                generate_kml.ROOT = repo
                invalid_files, invalid_audit = generate_kml.add_rights_cleared_overlays(
                    ET.Element(generate_kml.q("Document")), [invalid_rmse], {"synthetic-formation"}
                )
            finally:
                generate_kml.ROOT = previous_root
            self.assertEqual(invalid_files, [])
            self.assertEqual(invalid_audit[0]["reason"], "missing_or_invalid_transform_rmse_m")

            excessive_rmse = dict(authorized_row)
            excessive_rmse["transform_rmse_m"] = "25.01"
            previous_root = generate_kml.ROOT
            try:
                generate_kml.ROOT = repo
                excessive_files, excessive_audit = generate_kml.add_rights_cleared_overlays(
                    ET.Element(generate_kml.q("Document")), [excessive_rmse], {"synthetic-formation"}
                )
            finally:
                generate_kml.ROOT = previous_root
            self.assertEqual(excessive_files, [])
            self.assertEqual(excessive_audit[0]["reason"], "transform_rmse_exceeds_public_limit")

            unverified_registration = dict(authorized_row)
            unverified_registration["notes"] = "{}"
            previous_root = generate_kml.ROOT
            try:
                generate_kml.ROOT = repo
                unverified_files, unverified_audit = generate_kml.add_rights_cleared_overlays(
                    ET.Element(generate_kml.q("Document")), [unverified_registration], {"synthetic-formation"}
                )
            finally:
                generate_kml.ROOT = previous_root
            self.assertEqual(unverified_files, [])
            self.assertEqual(unverified_audit[0]["reason"], "unverified_transform_distance_units")

            # The combined generator independently verifies the ingested content hash.
            (repo / authorized_row["local_path"]).write_bytes(b"tampered")
            previous_root = generate_kml.ROOT
            try:
                generate_kml.ROOT = repo
                tampered_root = ET.Element(generate_kml.q("Document"))
                tampered_files, tampered_audit = generate_kml.add_rights_cleared_overlays(
                    tampered_root, [authorized_row], {"synthetic-formation"}
                )
            finally:
                generate_kml.ROOT = previous_root
            self.assertEqual(tampered_files, [])
            self.assertEqual(tampered_audit[0]["reason"], "image_sha256_mismatch")

            previous_root = generate_kml.ROOT
            try:
                generate_kml.ROOT = repo
                orphan_files, orphan_audit = generate_kml.add_rights_cleared_overlays(
                    ET.Element(generate_kml.q("Document")), [authorized_row], set()
                )
            finally:
                generate_kml.ROOT = previous_root
            self.assertEqual(orphan_files, [])
            self.assertEqual(orphan_audit[0]["reason"], "formation_not_found")

    def test_authorized_status_without_proof_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source.png"
            make_source(source)
            registration = base / "missing-proof.json"
            write_registration(registration, "missing-proof", {
                "status": "cc_by",
                "holder": "Synthetic fixture creator",
                "license": "CC BY 4.0",
                "proof": "",
                "public_derivative_export_allowed": False,
            })
            with self.assertRaisesRegex(RegistrationError, "missing_license_or_permission_proof"):
                export_registration(
                    registration, source, base / "public-export",
                    max_dimension=128, public_export=True,
                )
            local = export_registration(registration, source, base / "local-export", max_dimension=128)
            stale_metadata = json.loads(Path(local["paths"]["registration"]).read_text(encoding="utf-8"))
            stale_metadata["transform"].pop("distance_measurement")
            stale_registration = base / "stale-units.registration.json"
            stale_registration.write_text(json.dumps(stale_metadata), encoding="utf-8")
            with self.assertRaisesRegex(RegistrationError, "not verified physical ground metres"):
                ingest_registration(
                    stale_registration, Path(local["paths"]["png"]), repo_root=base / "stale-atlas"
                )
            tampered_metadata = json.loads(Path(local["paths"]["registration"]).read_text(encoding="utf-8"))
            tampered_metadata["transform"]["image_pixel_to_web_mercator"][0][2] += 100
            tampered_registration = base / "tampered-transform.registration.json"
            tampered_registration.write_text(json.dumps(tampered_metadata), encoding="utf-8")
            with self.assertRaisesRegex(RegistrationError, "transform does not match control points"):
                ingest_registration(
                    tampered_registration, Path(local["paths"]["png"]), repo_root=base / "tampered-atlas"
                )
            with self.assertRaisesRegex(RegistrationError, "publication-authorized status is incomplete"):
                ingest_registration(
                    Path(local["paths"]["registration"]), Path(local["paths"]["png"]),
                    repo_root=base / "atlas",
                )
            qualified, reasons = generate_kml.image_rights_qualification({
                "rights_status": "open_license",
                "license": "CC BY 4.0",
                "rights_proof": "legacy value",
            })
            self.assertFalse(qualified)
            self.assertEqual(reasons, ["rights_not_publication_authorized"])


if __name__ == "__main__":
    unittest.main()
