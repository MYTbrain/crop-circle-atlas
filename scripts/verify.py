from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_COORDINATE_METHODS = {
    "report_source_degree_decimal_minutes_converted",
    "source_decimal_degrees",
    "source_degree_decimal_minutes_converted",
}


def rows(name: str):
    with (ROOT / "data" / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def unique(values, label: str):
    values = list(values)
    assert len(values) == len(set(values)), f"duplicate {label}"


def normalized(value: str):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_path(value: str):
    candidate = (ROOT / value).resolve()
    if candidate.is_file():
        return candidate
    candidate = (ROOT / "data" / "raw" / value).resolve()
    return candidate


formations = rows("formations.csv")
assertions = rows("source_assertions.csv")
snapshots = rows("source_snapshots.csv")
source_catalog = rows("source_catalog.csv")
summary = json.loads((ROOT / "data" / "build_summary.json").read_text(encoding="utf-8"))

assert len(formations) >= 5_000, len(formations)
assert len(assertions) >= len(formations), (len(assertions), len(formations))
assert len(source_catalog) >= 10, len(source_catalog)
assert summary["formations"] == len(formations)
assert summary["assertions"]["total"] == len(assertions)
assert summary["assertions"]["iccra_mode"] == "exhaustive_reconciled"
assert (len(assertions), len(formations), summary["geocoded"], summary["us_formations"]) == (8390, 7749, 4027, 953)

expansion = rows("source_expansion_assertions.csv")
expansion_access = rows("source_expansion_access.csv")
expansion_manifest = rows("source_expansion_crawl_manifest.csv")
expansion_exclusions = rows("source_expansion_parse_exclusions.csv")
expansion_reconciliation = json.loads((ROOT / "data" / "source_expansion_reconciliation.json").read_text(encoding="utf-8"))
expansion_yield = expansion_reconciliation["yield"]
expansion_checks = expansion_reconciliation["completeness_checks"]
assert len(expansion) == expansion_yield["expansion_assertions"] == summary["assertions"]["source_expansion"]
assert len(expansion) == 639
unique((row["assertion_id"] for row in expansion), "source-expansion assertion_id")
assert {row["assertion_id"] for row in expansion}.issubset({row["assertion_id"] for row in assertions})
assert all(row["assertion_id"].startswith("sx_") for row in expansion)
assert all(row["source_url"] and row["source_record_url"] and row["rights_scope"] for row in expansion)
assert all(not row.get("thumbnail_url") and not row.get("image_urls") for row in expansion)
assert all(expansion_checks[name] is True for name in (
    "all_assertion_ids_unique", "all_rows_have_provenance", "all_rows_have_valid_dates", "no_image_urls_emitted",
))
assert expansion_yield["exact_overlap_normalized_keys"] == 189
assert expansion_yield["new_normalized_source_keys_vs_baseline"] == 450
assert expansion_yield["same_normalized_key_assertion_surplus"] == 0
assert Counter(row["expansion_source_id"] for row in expansion) == Counter({
    "connector": 442, "dcca": 184, "vigay": 12, "cccrn": 1,
})
assert len(expansion_manifest) == 127
assert sum(row["http_status"] != "200" for row in expansion_manifest) == 6
assert {row["url"] for row in expansion_manifest}.issubset({row["url"] for row in snapshots})
assert expansion_reconciliation["crawl"]["images_downloaded"] == 0
assert expansion_reconciliation["crawl"]["membership_or_api_requests"] == 0
assert expansion_reconciliation["parse_coverage"]["connector_assertions_emitted"] == 442
assert expansion_reconciliation["parse_coverage"]["connector_explicit_exclusions"] == len(expansion_exclusions) == 5
assert {row["source_id"] for row in expansion_access} == {"connector", "dcca", "cccrn", "vigay", "blt"}
catalog_status = {row["source_id"]: row["ingestion_status"] for row in source_catalog}
assert catalog_status["src_connector"] == "bounded_metadata_ingested"
assert catalog_status["src_dcca"] == "bounded_metadata_ingested"
assert catalog_status["src_vigay"] == "bounded_metadata_ingested"
assert catalog_status["src_cccrn"] == "bounded_metadata_ingested"
assert catalog_status["src_blt"] == "registered_fail_closed"

unique((row["formation_id"] for row in formations), "formation_id")
unique((row["assertion_id"] for row in assertions), "assertion_id")
assertion_ids = {row["assertion_id"] for row in assertions}
formation_by_id = {row["formation_id"]: row for row in formations}
for formation in formations:
    foreign_keys = [value for value in formation["assertion_ids"].split("; ") if value]
    assert foreign_keys and all(value in assertion_ids for value in foreign_keys), formation["formation_id"]
    assert int(formation["source_count"]) == len(foreign_keys)

geocoded = [row for row in formations if row["latitude"]]
assert len(geocoded) >= 2_000, len(geocoded)
coordinate_methods = Counter()
for row in geocoded:
    latitude, longitude = float(row["latitude"]), float(row["longitude"])
    uncertainty = float(row["coordinate_uncertainty_km"])
    confidence = float(row["geocode_confidence"])
    assert -90 <= latitude <= 90 and -180 <= longitude <= 180
    assert math.isfinite(uncertainty) and uncertainty > 0
    assert 0 <= confidence <= 1
    method = row["geocode_method"]
    assert method == "geonames_locality_centroid" or method in SOURCE_COORDINATE_METHODS, method
    if method == "geonames_locality_centroid":
        assert row["geoname_id"] and uncertainty >= 5
        assert row["geocode_admin1"]
        if row["country_code"] == "US" and row["region"]:
            assert normalized(row["geocode_admin1"]) == normalized(row["region"]), (
                row["formation_id"], row["region"], row["geocode_admin1"]
            )
    else:
        assert not row["geoname_id"]
    coordinate_methods[method] += 1

geojson = json.loads((ROOT / "web" / "data" / "formations.geojson").read_text(encoding="utf-8"))
assert len(geojson["features"]) == len(geocoded)
assert Counter(geojson["metadata"]["coordinate_methods"]) == coordinate_methods
assert all(feature["properties"]["geocode_method"] for feature in geojson["features"])

# ICCRA index coverage is distinct from availability of every linked detail page.
iccra = rows("iccra_assertions_full.csv")
iccra_index = rows("iccra_index_entries_full.csv")
iccra_images = rows("iccra_image_links.csv")
iccra_image_candidates = rows("iccra_image_straight_candidates.csv")
iccra_snapshots = rows("iccra_snapshots_full.csv")
reconciliation = json.loads((ROOT / "data" / "iccra_reconciliation.json").read_text(encoding="utf-8"))
totals = reconciliation["totals"]
checks = reconciliation["completeness_checks"]
assert checks["all_core_indexes_http_success"] is True
assert checks["every_parsed_index_slot_accounted"] is True
assert checks["index_inventory_complete"] is True
assert checks["scope_inventory_complete"] is True
assert checks["all_report_historical_news_documents_http_success"] is True
assert reconciliation["status"] == "index_inventory_complete_with_unavailable_detail_pages"
assert totals["canonical_assertions"] == len(iccra)
assert totals["all_index_occurrences"] == len(iccra_index)
assert totals["image_references"] == len(iccra_images)
assert totals["unique_image_urls"] == len({row["image_url"] for row in iccra_images})
assert checks["detail_pages_available"] == (totals["formation_detail_urls_failed"] == 0)
assert checks["public_image_redistribution_cleared"] is False
unique((row["assertion_id"] for row in iccra), "ICCRA assertion_id")
unique((row["index_entry_id"] for row in iccra_index), "ICCRA index_entry_id")
unique((row["image_link_id"] for row in iccra_images), "ICCRA image_link_id")
iccra_ids = {row["assertion_id"] for row in iccra}
assert all(row["assertion_id"] in iccra_ids for row in iccra_index)
assert all(row["year"] and row["place"] and row["date_iso"] for row in iccra)
assert all(row["public_redistribution_status"] == "not_cleared" for row in iccra_images)
assert not any("mbcc" in row["image_url"].lower() for row in iccra_images)
assert {row["assertion_id"] for row in assertions if row["source_name"] == "ICCRA"} == iccra_ids
snapshot_urls = {row["url"] for row in snapshots}
assert {row["url"] for row in iccra_snapshots}.issubset(snapshot_urls)
for row in iccra_snapshots:
    if row["http_status"].startswith("2"):
        cached = cache_path(row["cache_path"])
        assert cached.is_file(), row["url"]
        assert sha256_file(cached) == row["sha256"], row["url"]
for row in iccra_images:
    if str(row["http_status"]).startswith("2"):
        cached = cache_path(row["cache_path"])
        assert cached.is_file(), row["image_url"]
        assert sha256_file(cached) == row["sha256"], row["image_url"]

image_metrics = json.loads((ROOT / "outputs" / "straight-components" / "iccra_image_metrics.json").read_text(encoding="utf-8"))
assert len(iccra_image_candidates) == len(iccra_images) == image_metrics["input_inventory_rows"]
unique((row["candidate_id"] for row in iccra_image_candidates), "ICCRA image candidate_id")
assert {row["image_link_id"] for row in iccra_image_candidates} == {row["image_link_id"] for row in iccra_images}
assert image_metrics["analyzed_rows"] == totals["iccra_hosted_image_references_http_success"]
assert image_metrics["qualification_boundary"]["true_north_bearing_created"] is False
assert image_metrics["qualification_boundary"]["source_pixel_output"] is False
assert all(row["geographic_azimuth_qualified"] == "false" for row in iccra_image_candidates)

# Every supplied-PDF diagram was analyzed; thresholds have measured performance.
candidates = rows("straight_component_candidates.csv")
metrics = json.loads((ROOT / "outputs" / "straight-components" / "qa_metrics.json").read_text(encoding="utf-8"))
pdf_assertion_ids = {row["assertion_id"] for row in assertions if row["source_name"] == "Crop Circle Center PDF catalog"}
assert len(candidates) == metrics["pdf_assertions_processed"] == summary["pdf"]["assertions"]
unique((row["candidate_id"] for row in candidates), "straight candidate_id")
unique((row["assertion_id"] for row in candidates), "straight candidate assertion_id")
assert {row["assertion_id"] for row in candidates} == pdf_assertion_ids
assert sum(metrics["tier_counts"].values()) == len(candidates)
validated = metrics["validated_thresholds"]["high_or_medium"]
assert validated["n"] >= 100 and validated["precision"] >= 0.85 and validated["recall"] >= 0.60
assert metrics["angle_semantics"]["geographic_interpretation"] == "none"

# Reviewed true-north orientations must join to both their formation and source assertion.
orientations = rows("orientation_observations.csv")
reviews = rows("orientation_evidence_review.csv")
assert len(orientations) == 5
unique((row["observation_id"] for row in orientations), "orientation observation_id")
for row in orientations:
    assert row["formation_id"] in formation_by_id
    assert row["assertion_id"] in assertion_ids
    assert row["assertion_id"] in formation_by_id[row["formation_id"]]["assertion_ids"].split("; ")
    assert HEX64.fullmatch(row["evidence_sha256"])
    evidence = cache_path(row["evidence_cache_path"])
    assert evidence.is_file(), row["observation_id"]
    assert sha256_file(evidence) == row["evidence_sha256"], row["observation_id"]
    assert row["reviewer"] and row["reviewed_at"]
for row in reviews:
    if row["formation_id"]:
        assert row["formation_id"] in formation_by_id
        assert row["assertion_id"] in formation_by_id[row["formation_id"]]["assertion_ids"].split("; ")
assert summary["orientations"]["observations"] == len(orientations)
assert summary["orientations"]["qualified_formations"] == len({row["formation_id"] for row in orientations})
assert summary["orientations"]["invalid_foreign_keys"] == 0

ray_audit = rows("orientation_ray_audit.csv")
rays = json.loads((ROOT / "web" / "data" / "orientation_rays.geojson").read_text(encoding="utf-8"))
assert len(ray_audit) == len(orientations)
assert all(row["status"] == "qualified" and not row["reasons"] for row in ray_audit)
assert len(rays["features"]) == len(orientations)
for feature in rays["features"]:
    properties = feature["properties"]
    assert properties["observation_id"] and properties["assertion_id"]
    assert properties["origin_method"] and float(properties["origin_uncertainty_m"]) >= 0
    assert properties["reviewer"] and properties["reviewed_at"]
    assert HEX64.fullmatch(properties["evidence_sha256"])
    assert properties["projection_status"] == "experimental_extension_of_documented_local_orientation"
    assert properties["predictive_validity"] == "none_demonstrated"
assert "no demonstrated predictive validity" in rays["metadata"]["notice"]
hits = rows("alignment_hits.csv")
assert len(hits) == 16
for row in hits:
    assert row["eligible_for_statistical_test"] in {"yes", "no"}
    assert row["spatial_quality_status"]
    assert row["hit_geometry"] == "centerline_corridor"
    assert row["temporal_relation"] in {"earlier", "later", "overlap_or_indeterminate"}
    if row["eligible_for_statistical_test"] == "yes":
        assert float(row["combined_spatial_uncertainty_km"]) <= float(row["corridor_km"])
assert not any(row["eligible_for_statistical_test"] == "yes" for row in hits)

kml_path = ROOT / "exports" / "crop_circle_atlas.kml"
kml_tree = ET.parse(kml_path)
kml_root = kml_tree.getroot()
kml_ns = {"k": "http://www.opengis.net/kml/2.2"}
assert len(kml_root.findall(".//k:Point", kml_ns)) == len(geocoded)
assert len(kml_root.findall(".//k:LineString", kml_ns)) == len(orientations)
assert len(kml_root.findall(".//k:GroundOverlay", kml_ns)) == 0
kml_text = kml_path.read_text(encoding="utf-8")
assert "Experimental projections from documented orientations" in kml_text
assert "no demonstrated predictive validity" in kml_text
kmz_path = ROOT / "exports" / "crop_circle_atlas.kmz"
with zipfile.ZipFile(kmz_path) as archive:
    assert archive.testzip() is None
    assert archive.read("doc.kml") == kml_path.read_bytes()
assert (ROOT / "web" / "downloads" / "crop_circle_atlas.kmz").read_bytes() == kmz_path.read_bytes()

workbook = ROOT / "outputs" / "initial-build" / "crop_circle_atlas.xlsx"
with zipfile.ZipFile(workbook) as archive:
    assert archive.testzip() is None
    workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
    for sheet_name in (
        "Summary", "Formations", "Source Assertions", "Straight Candidates",
        "Reviewed Orientations", "Alignment Hits", "ICCRA Index Entries",
        "ICCRA Image Links", "ICCRA Image Straight Review", "Orientation Evidence", "Read Me",
        "Expansion Assertions", "Expansion Access", "Expansion Manifest",
        "Expansion Exclusions",
    ):
        assert f'name="{sheet_name}"' in workbook_xml, sheet_name

for needed in (
    "index.html", "app.js", "styles.css", "methodology.html", "georef.html",
    "georef.css", "georef.js", "georef-core.mjs", "georef-atlas-adapter.mjs",
    "atlas-georef-integration.mjs", "atlas-geodesy.mjs",
):
    assert (ROOT / "web" / needed).exists(), needed
assert "GeoNames CC BY 4.0" in (ROOT / "web" / "index.html").read_text(encoding="utf-8")
assert "GeoNames under CC BY 4.0" in kml_path.read_text(encoding="utf-8")
web_index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
web_app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
georef_html = (ROOT / "web" / "georef.html").read_text(encoding="utf-8")
assert "Current public overlays: 0" in web_index
assert "Export unqualified hypothesis KML" in web_index
assert 'id="resultsList"' in web_index
assert "unqualified_manual_hypothesis" in web_app
assert "Experimental projection from documented orientation" in web_app
assert "image/tiff" not in georef_html
readme = (ROOT / "README.md").read_text(encoding="utf-8")
source_register_text = (ROOT / "docs" / "SOURCE_REGISTER.md").read_text(encoding="utf-8")
for phrase in ("8,390 source assertions", "7,749 conservative catalog entities", "450 new normalized source keys"):
    assert phrase in readme
    assert phrase in source_register_text
for needed in (
    "SOURCE_REGISTER.md", "METHODOLOGY.md", "IMAGE_GEOREFERENCING.md", "ICCRA_RECONCILIATION.md",
    "SOURCE_EXPANSION.md",
):
    assert (ROOT / "docs" / needed).exists(), needed

print(
    "PASS "
    f"formations={len(formations)} assertions={len(assertions)} geocoded={len(geocoded)} "
    f"snapshots={len(snapshots)} iccra={len(iccra)} index_entries={len(iccra_index)} "
    f"image_links={len(iccra_images)} image_reviews={len(iccra_image_candidates)} "
    f"candidates={len(candidates)} rays={len(orientations)} hits={len(hits)}"
)
