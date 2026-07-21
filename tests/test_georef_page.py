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
        self.assertIn(("georef.js", "module"), parser.scripts)
        self.assertIn("georef.css", parser.stylesheets)
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
        self.assertIn("Export unqualified hypothesis KML", html)
        self.assertIn("Show rough locality references on map", html)
        self.assertIn("Load and zoom to registered image", html)
        self.assertIn("Registered aerial imagery", html)
        self.assertIn("Source image archive", html)
        self.assertIn('id="sourceImageGallery"', html)
        self.assertIn('id="toggleSourceImages"', html)
        self.assertIn("Registered aerial-photo footprints", javascript)
        self.assertIn("renderSourceImageGallery", javascript)
        self.assertIn("sourceImagesByFormation", javascript)
        self.assertIn("sitePointPane", javascript)
        self.assertIn("localityPointPane", javascript)
        self.assertIn("radius: 5, color: '#ffd84d', weight: 2.25, opacity: 1, dashArray: '3 2'", javascript)
        self.assertIn("fillColor: '#ffd84d', fillOpacity: 0.08, renderer: localityRenderer", javascript)
        self.assertIn("fillColor: verified ? '#2d9e91' : '#ffd84d'", javascript)
        self.assertIn("renderRegisteredFootprints(visibleIds)", javascript)
        self.assertIn("activeOverlayRecord && !visibleIds.has(activeOverlayRecord.formation_id)", javascript)
        self.assertIn("setRegisteredFootprintVisible(record, false)", javascript)
        self.assertIn("maxZoom: 18", javascript)
        self.assertIn("approximate", html)
        self.assertIn("hollow dashed yellow markers are rough locality references", html)
        self.assertIn('href="styles.css?v=20260721.5"', html)
        self.assertIn('src="app.js?v=20260721.5"', html)
        self.assertIn("registered_overlays.json?v=20260721.5", javascript)
        self.assertIn("formation_images.json?v=20260721.5", javascript)
        self.assertIn("Six reviewed source-image placements are mapped", html)
        self.assertIn("activeOverlay?.remove()", javascript)
        self.assertIn("activeOverlayRecord = null", javascript)
        self.assertRegex(html, r'<input id="showLocalities" type="checkbox">')
        self.assertIn("await selectFormation(id, true)", javascript)
        self.assertIn("map.closePopup()", javascript)
        self.assertIn('id="resultsList"', html)
        self.assertIn("unqualified_manual_hypothesis", javascript)
        self.assertIn("predictive_validity: 'none'", javascript)
        self.assertIn("Accepted local axes extended experimentally", javascript)
        self.assertIn("Locality centroids and unresolved reports are excluded", javascript)
        self.assertNotIn("Documented projection ray", javascript)


if __name__ == "__main__":
    unittest.main()
