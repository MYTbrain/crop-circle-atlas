import re
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

from scripts.georeference_image import PUBLIC_RIGHTS


ROOT = Path(__file__).resolve().parents[1]


class IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.scripts = []
        self.stylesheets = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag == "script" and attributes.get("src"):
            self.scripts.append((attributes.get("src"), attributes.get("type")))
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.stylesheets.append(attributes.get("href"))


class GeorefPageContractTests(unittest.TestCase):
    def test_dom_contract_and_local_only_image_processing(self):
        html = (ROOT / "web" / "georef.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "georef.js").read_text(encoding="utf-8")
        parser = IdParser()
        parser.feed(html)
        self.assertEqual(len(parser.ids), len(set(parser.ids)), "duplicate HTML ids")
        referenced_ids = set(re.findall(r'\$\("([A-Za-z][A-Za-z0-9_-]*)"\)', javascript))
        self.assertEqual(set(), referenced_ids - set(parser.ids), "JavaScript references missing DOM ids")
        self.assertIn(("georef.js?v=20260722.4", "module"), parser.scripts)
        self.assertIn("georef.css?v=20260722.4", parser.stylesheets)
        self.assertIn("crop-circle-atlas:orientation-ready", javascript)
        self.assertIn("local_browser_only", javascript)
        self.assertNotIn("image/tiff", html)
        self.assertIn('Data name="rights_holder"', javascript)
        self.assertIn('Data name="rights_proof"', javascript)
        self.assertIn("unreviewed_local_registration", javascript)
        self.assertIn("no demonstrated predictive validity", javascript)
        for required_orientation_field in (
            "observation_id", "origin_latitude", "origin_longitude",
            "origin_uncertainty_m", "origin_coordinate_method", "evidence_sha256",
        ):
            self.assertIn(f'"{required_orientation_field}"', javascript)
        registry_header = (ROOT / "data" / "orientation_observations.csv").read_text(
            encoding="utf-8-sig"
        ).splitlines()[0].split(",")
        exported_header_source = re.search(r"const headers = \[(.*?)\];", javascript)
        self.assertIsNotNone(exported_header_source)
        exported_header = re.findall(r'"([A-Za-z0-9_]+)"', exported_header_source.group(1))
        self.assertEqual(registry_header, exported_header)
        self.assertIn('state.orientation.directionality === "bidirectional" ? "bidirectional" : "forward"', javascript)
        rights_select = re.search(r'<select id="rightsStatus">(.*?)</select>', html, re.DOTALL)
        self.assertIsNotNone(rights_select)
        browser_rights = set(re.findall(r'<option value="([a-z0-9_]+)"', rights_select.group(1)))
        expected_rights = PUBLIC_RIGHTS | {"local_analysis_only", "permission_pending"}
        self.assertEqual(browser_rights, expected_rights)
        schema = json.loads((ROOT / "schemas" / "georeference-registration-v1.schema.json").read_text(encoding="utf-8"))
        schema_rights = set(schema["properties"]["asset"]["properties"]["rights"]["properties"]["status"]["enum"])
        self.assertEqual(schema_rights, expected_rights)
        for forbidden in ("XMLHttpRequest", "navigator.sendBeacon", "new FormData", 'method: "POST"'):
            self.assertNotIn(forbidden, javascript)

    def test_atlas_manual_export_is_unambiguously_unqualified(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        stylesheet = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("Export unqualified hypothesis KML", html)
        self.assertIn("Show rough locality references on map", html)
        self.assertIn("Load and zoom to registered image", html)
        self.assertIn("Mapped source-image overlays", html)
        self.assertIn('id="overlayChoice"', html)
        self.assertIn("Source image archive", html)
        self.assertIn('id="sourceImageGallery"', html)
        self.assertIn('id="toggleSourceImages"', html)
        self.assertIn("Reviewed image footprints", javascript)
        self.assertIn("renderSourceImageGallery", javascript)
        self.assertIn("sourceImagesByFormation", javascript)
        self.assertIn("sourcePhotoLayer", javascript)
        self.assertIn("renderSourcePhotoAvailability(visibleIds)", javascript)
        self.assertIn("sourcePhotoCoordinates", javascript)
        self.assertIn("record.latitude == null || record.latitude === ''", javascript)
        self.assertIn("mappedOverlayIds.has(formationId)", javascript)
        self.assertIn("window.showSourceImagesForFormation(record.formation_id)", javascript)
        self.assertIn("Source-photo availability", javascript)
        self.assertIn("clustered green availability dots", javascript)
        self.assertIn("source-photo-cluster-marker", stylesheet)
        self.assertIn("source-photo-marker", stylesheet)
        self.assertIn(
            ".source-photo-marker { position:absolute!important;",
            stylesheet,
        )
        self.assertNotIn(
            ".source-photo-marker { position:relative!important;",
            stylesheet,
        )
        self.assertIn("source-photo availability", html)
        self.assertIn("reviewed display placements", html)
        self.assertIn("Source-photo availability only; not a registered image placement.", html)
        self.assertIn("sitePointPane", javascript)
        self.assertIn("const localityRenderer = L.canvas({ pane: 'localityPointPane', padding: 0.5, tolerance: 12 })", javascript)
        self.assertIn("const siteRenderer = L.canvas({ pane: 'sitePointPane', padding: 0.5, tolerance: 12 })", javascript)
        self.assertIn("map.getPane('sourcePhotoPane').style.zIndex = '440'", javascript)
        self.assertIn("map.getPane('overlayFootprintPane').style.zIndex = '520'", javascript)
        self.assertIn("const overlayFootprintRenderer = L.svg", javascript)
        self.assertIn("renderer: overlayFootprintRenderer", javascript)
        self.assertIn(".map-marker-legend", stylesheet)
        self.assertIn(">Open report details</button>", javascript)
        self.assertIn("void selectFormation(records[0].formation_id)", javascript)
        self.assertIn("localityPointPane", javascript)
        self.assertIn("radius: 6, color: '#ffd84d', weight: 2.5, opacity: 1, dashArray: '3 2'", javascript)
        self.assertIn("fillColor: '#ffd84d', fillOpacity: 0.08, renderer: localityRenderer", javascript)
        self.assertIn("fillColor: '#ffd84d'", javascript)
        self.assertIn("renderRegisteredFootprints(visibleIds)", javascript)
        self.assertIn("activeOverlayRecord && !visibleIds.has(activeOverlayRecord.formation_id)", javascript)
        self.assertIn("setRegisteredFootprintVisible(record, false)", javascript)
        self.assertIn("maxZoom: 18", javascript)
        self.assertIn("approximate", html)
        self.assertIn("Hollow yellow dots are rough locality references", html)
        self.assertIn('href="styles.css?v=20260722.7"', html)
        self.assertIn('src="app.js?v=20260722.7"', html)
        self.assertIn("source-photo-clustering.mjs?v=20260722.2", javascript)
        self.assertIn("Availability dots are clustered when zoomed out.", html)
        self.assertIn("formation_index.json?v=20260722.6", javascript)
        self.assertIn("formation_sites.geojson?v=20260722.6", javascript)
        self.assertIn("registered_overlays.json?v=20260722.6", javascript)
        self.assertIn("formation_images.json?v=20260722.6", javascript)
        self.assertIn('id="localityPhotoCoverage"', html)
        self.assertIn("usLocalityPhotoReports", javascript)
        self.assertIn("LINK ONLY", javascript)
        self.assertIn("sourcePixelsMayDisplay", javascript)
        self.assertIn("overlayPixelsMayDisplay", javascript)
        self.assertIn("function overlaysFor", javascript)
        self.assertIn("function selectedOverlayRecord", javascript)
        self.assertIn("records.length > 1 ? ` (${records.length} mapped images)`", javascript)
        self.assertIn("rights-gated footprints remain link-only", html)
        self.assertIn("Mapped source-image overlays", html)
        self.assertIn("overlayRecords.length.toLocaleString()", javascript)
        self.assertIn("mapped placements covering ${overlayRecords.length} reviewed frames", javascript)
        self.assertIn("activeOverlay?.remove()", javascript)
        self.assertIn("activeOverlayRecord = null", javascript)
        self.assertRegex(html, r'<input id="showLocalities" type="checkbox">')
        self.assertIn("await selectFormation(id, true)", javascript)
        self.assertIn("map.closePopup()", javascript)
        self.assertIn('id="resultsList"', html)
        self.assertIn("unqualified_manual_hypothesis", javascript)
        self.assertIn("predictive_validity: 'none'", javascript)
        self.assertIn("Accepted experimental axes", javascript)
        self.assertIn("Locality centroids and unresolved reports are excluded", javascript)
        self.assertNotIn("Documented projection ray", javascript)
        self.assertRegex(
            stylesheet,
            r"\.source-image-gallery\[hidden\]\s*\{\s*display\s*:\s*none\s*;\s*\}",
            "the author-level grid rule must not override the native hidden attribute",
        )
        self.assertIn("#overlayChoiceLabel[hidden] { display:none; }", stylesheet)
        self.assertIn("#overlayOpacityLabel[hidden] { display:none; }", stylesheet)
        self.assertIn('id="panelResizer"', html)
        self.assertIn('role="separator"', html)
        self.assertIn("PANEL_WIDTH_STORAGE_KEY", javascript)
        self.assertIn("setPointerCapture", javascript)
        self.assertIn("window.addEventListener('pointermove', move)", javascript)
        self.assertIn("window.addEventListener('pointerup', finish)", javascript)
        self.assertIn("map.invalidateSize", javascript)
        self.assertIn("html: ''", javascript)
        self.assertIn("className: `source-photo-dot ${markerClass}", javascript)
        self.assertIn(".setContent(sourcePhotoChoicePopup(records))", javascript)
        self.assertNotIn("registered-image-marker", javascript)
        self.assertNotIn("key-image-badge", html)
        self.assertIn("Source-photo availability only; not a registered image placement.", javascript)
        self.assertIn("Rough locality reference; not the formation site.", javascript)
        self.assertIn("--panel-width:370px", stylesheet)
        self.assertIn("cursor:col-resize", stylesheet)

    def test_source_photo_dot_coverage_uses_only_available_coordinates(self):
        index_payload = json.loads((ROOT / "web" / "data" / "formation_index.json").read_text(encoding="utf-8"))
        image_payload = json.loads((ROOT / "web" / "data" / "formation_images.json").read_text(encoding="utf-8"))
        site_payload = json.loads((ROOT / "web" / "data" / "formation_sites.geojson").read_text(encoding="utf-8"))
        overlay_payload = json.loads((ROOT / "web" / "data" / "registered_overlays.json").read_text(encoding="utf-8"))
        records = {record["formation_id"]: record for record in index_payload["formations"]}
        image_ids = set(image_payload["images_by_formation"])
        site_ids = {feature["properties"]["formation_id"] for feature in site_payload["features"]}
        located_ids = {
            formation_id for formation_id in image_ids
            if formation_id in site_ids or (
                records[formation_id].get("latitude") not in (None, "")
                and records[formation_id].get("longitude") not in (None, "")
            )
        }
        overlay_ids = {overlay["formation_id"] for overlay in overlay_payload["overlays"]}
        self.assertTrue(overlay_ids <= located_ids)
        self.assertGreater(len(located_ids - overlay_ids), 0, "the source-photo layer should contain coordinate-referenced reports")
        self.assertGreater(len(image_ids - located_ids), 0, "unlocated image reports must remain off-map")
        self.assertEqual(len(image_ids), len(located_ids) + len(image_ids - located_ids))

    def test_same_flight_overlays_remain_provisional_and_alignment_excluded(self):
        overlay_payload = json.loads(
            (ROOT / "web" / "data" / "registered_overlays.json").read_text(
                encoding="utf-8"
            )
        )
        transfers = [
            record
            for record in overlay_payload["overlays"]
            if record["registration_status"]
            == "provisional_same_flight_similarity_transfer"
        ]
        self.assertEqual(len(transfers), 8)
        self.assertEqual(len({record["source_image_url"] for record in transfers}), 8)
        self.assertTrue(all(record["embedding_allowed"] for record in transfers))
        self.assertTrue(
            all(
                record["formal_alignment_status"]
                == "excluded_pending_independent_ground_control"
                for record in transfers
            )
        )
        self.assertTrue(
            all(
                record["source_registration"]["quality_gate"][
                    "independent_ground_checkpoint_count"
                ]
                == 0
                for record in transfers
            )
        )

    def test_five_event_coordinate_geometry_batch_fails_closed(self):
        expected_ids = {
            "cc_270dae67472f",  # Etchilhampton
            "cc_e1045cdcfe11",  # Ridgeway / Hackpen
            "cc_a24651bbc437",  # Roundway Hill
            "cc_d165b4ccc092",  # Ansty
            "cc_d6b8ded1f85e",  # Ranscomb Bottom
        }
        overlay_payload = json.loads(
            (ROOT / "web" / "data" / "registered_overlays.json").read_text(
                encoding="utf-8"
            )
        )
        batch = [
            record
            for record in overlay_payload["overlays"]
            if record["formation_id"] in expected_ids
        ]
        self.assertEqual({record["formation_id"] for record in batch}, expected_ids)
        self.assertEqual(len(batch), 5)
        for record in batch:
            self.assertEqual(
                record["registration_status"],
                "coordinate_size_geometry_provisional",
            )
            self.assertEqual(
                record["source_registration"]["kind"],
                "coordinate_size_orientation_constrained_display_placement",
            )
            self.assertEqual(
                record["formal_alignment_status"],
                "excluded_pending_independent_ground_control",
            )
            self.assertFalse(record["embedding_allowed"])
            self.assertEqual(record["rights_status"], "not_cleared_for_redistribution")
            self.assertIn(
                "not an independently validated image-to-ground registration",
                record["quality_disclosure"],
            )
            self.assertIn(
                "not a real-world accuracy benchmark",
                record["quality_disclosure"],
            )

    def test_rockville_uses_skew_capable_three_control_registration(self):
        overlay_payload = json.loads(
            (ROOT / "web" / "data" / "registered_overlays.json").read_text(
                encoding="utf-8"
            )
        )
        rockville = next(
            record
            for record in overlay_payload["overlays"]
            if record["overlay_id"] == "rockville-1-2003-landmark-scene-placement"
        )
        self.assertEqual(
            rockville["registration_status"],
            "provisional_three_control_affine_road_registration",
        )
        self.assertEqual(
            rockville["display_geometry_status"],
            "four_corner_affine_road_control_scene_placement",
        )
        self.assertEqual(
            rockville["source_registration"]["kind"],
            "manual_three_control_affine_scene_registration",
        )
        self.assertEqual(rockville["source_registration"]["control_count"], 3)
        self.assertEqual(rockville["source_registration"]["independent_checkpoint_count"], 0)
        self.assertEqual(len(rockville["corners"]), 4)
        self.assertEqual(rockville["coordinate_uncertainty_m"], 75)

    def test_darfield_legacy_coordinate_scale_placement_is_rights_gated(self):
        overlay_payload = json.loads(
            (ROOT / "web" / "data" / "registered_overlays.json").read_text(
                encoding="utf-8"
            )
        )
        darfield = next(
            record
            for record in overlay_payload["overlays"]
            if record["overlay_id"]
            == "darfield-2002-legacy-coordinate-scale-north-up-placement"
        )
        self.assertEqual(darfield["formation_id"], "cc_d777276e6710")
        self.assertEqual(
            darfield["registration_status"],
            "coordinate_size_geometry_provisional",
        )
        self.assertEqual(
            darfield["source_registration"]["kind"],
            "legacy_coordinate_scale_north_up_display_placement",
        )
        self.assertEqual(darfield["source_registration"]["control_count"], 0)
        self.assertEqual(
            darfield["source_registration"]["independent_checkpoint_count"], 0
        )
        self.assertEqual(darfield["coordinate_uncertainty_m"], 50)
        self.assertFalse(darfield["embedding_allowed"])
        self.assertEqual(
            darfield["formal_alignment_status"],
            "excluded_pending_independent_ground_control",
        )
        self.assertIn(
            "not an independently validated image-to-ground registration",
            darfield["quality_disclosure"],
        )

    def test_legacy_coordinate_display_placements_fail_closed(self):
        overlay_payload = json.loads(
            (ROOT / "web" / "data" / "registered_overlays.json").read_text(
                encoding="utf-8"
            )
        )
        overlays = {
            record["overlay_id"]: record for record in overlay_payload["overlays"]
        }
        expected = {
            "hexton-barton-hills-2002-legacy-coordinate-scale-north-up-placement": (
                "cc_96878ba19702",
                "coordinate_size_geometry_provisional",
                "legacy_coordinate_scale_north_up_display_placement",
                30,
            ),
            "waden-hill-2002-legacy-coordinate-scale-north-up-placement": (
                "cc_9275734c8913",
                "coordinate_size_geometry_provisional",
                "legacy_coordinate_scale_north_up_display_placement",
                40,
            ),
            "dodworth-st-john-2002-legacy-coordinate-scale-north-up-placement": (
                "cc_6f84d7030b21",
                "coordinate_size_geometry_provisional",
                "legacy_coordinate_scale_north_up_display_placement",
                40,
            ),
            "panocchia-2004-legacy-coordinate-reported-size-north-up-placement": (
                "cc_69e673eaab9f",
                "coordinate_size_north_up_provisional",
                "legacy_coordinate_reported_size_north_up_display_placement",
                75,
            ),
            "hackpen-hill-2003-legacy-coordinate-scale-north-up-placement": (
                "cc_ff64c3c47cb1",
                "coordinate_size_geometry_provisional",
                "legacy_coordinate_scale_north_up_display_placement",
                40,
            ),
        }
        for overlay_id, (
            formation_id,
            classification,
            registration_kind,
            uncertainty_m,
        ) in expected.items():
            overlay = overlays[overlay_id]
            self.assertEqual(overlay["formation_id"], formation_id)
            self.assertEqual(overlay["registration_status"], classification)
            self.assertEqual(overlay["source_registration"]["kind"], registration_kind)
            self.assertEqual(overlay["source_registration"]["control_count"], 0)
            self.assertEqual(
                overlay["source_registration"]["independent_checkpoint_count"], 0
            )
            self.assertEqual(overlay["coordinate_uncertainty_m"], uncertainty_m)
            self.assertFalse(overlay["embedding_allowed"])
            self.assertEqual(
                overlay["formal_alignment_status"],
                "excluded_pending_independent_ground_control",
            )
            self.assertIn(
                "not an independently validated image-to-ground registration",
                overlay["quality_disclosure"],
            )


if __name__ == "__main__":
    unittest.main()
