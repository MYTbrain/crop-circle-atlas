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

try:
    from .verify_registered_overlay import validate_registered_overlay
except ImportError:
    from verify_registered_overlay import validate_registered_overlay


ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_COORDINATE_METHODS = {
    "report_source_degree_decimal_minutes_converted",
    "source_decimal_degrees",
    "source_degree_decimal_minutes_converted",
}
FIELD_SITE_STATUSES = {"candidate_field", "corroborated_field", "registered_site"}


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
assert (len(assertions), len(formations), summary["geocoded"], summary["us_formations"]) == (8391, 7745, 4302, 949)
assert summary["formation_aliases"] == {"accepted_reviews": 4, "merged_alias_entities": 4}
assert summary["site_resolutions"]["status_counts"] == {
    "locality_reference": 3894,
    "unresolved": 3443,
    "corroborated_field": 4,
    "candidate_field": 398,
    "registered_site": 6,
}
assert summary["site_resolutions"]["reviewed_overrides"] == 20

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
assert expansion_yield["exact_overlap_normalized_keys"] == 190
assert expansion_yield["new_normalized_source_keys_vs_baseline"] == 449
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
site_resolution_rows = rows("site_resolutions.csv")
unique((row["formation_id"] for row in site_resolution_rows), "site-resolution formation_id")
site_resolution_by_id = {row["formation_id"]: row for row in site_resolution_rows}
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
    status = row["site_status"]
    if status == "locality_reference":
        assert method == "geonames_locality_centroid", (row["formation_id"], method)
        assert row["geoname_id"] and uncertainty >= 5
        assert row["geocode_admin1"]
        if row["country_code"] == "US" and row["region"]:
            assert normalized(row["geocode_admin1"]) == normalized(row["region"]), (
                row["formation_id"], row["region"], row["geocode_admin1"]
            )
    else:
        assert status in FIELD_SITE_STATUSES, (row["formation_id"], status)
        assert method == row["site_coordinate_method"] and row["site_resolution_source"]
        assert float(row["site_coordinate_uncertainty_m"]) / 1000 == uncertainty
        assert row["site_review_status"] and row["site_rights_status"]
        assert not row["geoname_id"]
        if row["site_resolution_source"] == "automatic_source_coordinate":
            assert method in SOURCE_COORDINATE_METHODS
            assert status == "registered_site"
            assert row["site_alignment_eligible"] == "false"
            assert row["site_review_status"] == "source_report_not_independently_reviewed"
            assert row["site_rights_status"] == "coordinate_metadata_only"
        elif row["site_resolution_source"] == "global_source_map_candidate_queue":
            assert status == "candidate_field"
            assert row["site_alignment_eligible"] == "false"
            assert row["site_directly_visible"] == "false"
            assert row["site_review_status"] == "source_map_target_not_landmark_validated"
            assert row["site_rights_status"].startswith("coordinate_metadata_only")
            assert row["site_evidence_artifact_ids"].startswith("gsite_")
            assert HEX64.fullmatch(row["site_evidence_artifact_sha256s"])
        else:
            assert row["site_resolution_source"] == "reviewed_override"
            assert row["formation_id"] in site_resolution_by_id
            reviewed = site_resolution_by_id[row["formation_id"]]
            expected = {
                "site_status": reviewed["site_status"],
                "latitude": reviewed["latitude"],
                "longitude": reviewed["longitude"],
                "site_coordinate_uncertainty_m": reviewed["coordinate_uncertainty_m"],
                "site_coordinate_method": reviewed["coordinate_method"],
                "site_directly_visible": reviewed["directly_visible"].lower(),
                "site_alignment_eligible": reviewed["alignment_eligible"].lower(),
                "site_cluster_id": reviewed["site_cluster_id"],
                "site_search_aliases": reviewed["search_aliases"],
                "site_evidence_source_url": reviewed["evidence_source_url"],
                "site_evidence_artifact_ids": reviewed["evidence_artifact_ids"],
                "site_evidence_artifact_sha256s": reviewed["evidence_artifact_sha256s"],
                "site_imagery_provider": reviewed["imagery_provider"],
                "site_imagery_acquisition_date": reviewed["imagery_acquisition_date"],
                "site_review_status": reviewed["review_status"],
                "site_reviewer": reviewed["reviewer"],
                "site_reviewed_at": reviewed["reviewed_at"],
                "site_rights_status": reviewed["rights_status"],
                "site_notes": reviewed["notes"],
            }
            for field, value in expected.items():
                if field in {"latitude", "longitude", "site_coordinate_uncertainty_m"}:
                    assert float(row[field]) == float(value), (row["formation_id"], field)
                else:
                    assert row[field] == value, (row["formation_id"], field)
            artifact_ids = [value.strip() for value in row["site_evidence_artifact_ids"].split(";") if value.strip()]
            artifact_hashes = [value.strip() for value in row["site_evidence_artifact_sha256s"].split(";") if value.strip()]
            assert len(artifact_ids) == len(artifact_hashes) > 0
            assert all(HEX64.fullmatch(value) for value in artifact_hashes)
    coordinate_methods[method] += 1

geojson = json.loads((ROOT / "web" / "data" / "formations.geojson").read_text(encoding="utf-8"))
assert len(geojson["features"]) == len(geocoded)
assert Counter(geojson["metadata"]["coordinate_methods"]) == coordinate_methods
assert all(feature["properties"]["geocode_method"] for feature in geojson["features"])

formation_index = json.loads((ROOT / "web" / "data" / "formation_index.json").read_text(encoding="utf-8"))
site_geojson = json.loads((ROOT / "web" / "data" / "formation_sites.geojson").read_text(encoding="utf-8"))
locality_geojson = json.loads((ROOT / "web" / "data" / "locality_references.geojson").read_text(encoding="utf-8"))
work_queue = rows("location_work_queue.csv")
assert formation_index["metadata"]["record_count"] == len(formation_index["formations"]) == len(formations)
assert len(work_queue) == len(formations)
assert len(site_geojson["features"]) == summary["site_resolutions"]["field_site_features"] == 408
assert len(locality_geojson["features"]) == summary["site_resolutions"]["locality_reference_features"] == 3894
assert not ({feature["properties"]["formation_id"] for feature in site_geojson["features"]} &
            {feature["properties"]["formation_id"] for feature in locality_geojson["features"]})
assert all(feature["properties"]["site_status"] in FIELD_SITE_STATUSES for feature in site_geojson["features"])
assert all(feature["properties"]["site_status"] == "locality_reference" for feature in locality_geojson["features"])
site_feature_ids = [feature["properties"]["formation_id"] for feature in site_geojson["features"]]
unique(site_feature_ids, "field-site GeoJSON formation_id")
assert set(site_feature_ids) == {
    row["formation_id"] for row in formations if row["site_status"] in FIELD_SITE_STATUSES
}
for feature in site_geojson["features"]:
    row = formation_by_id[feature["properties"]["formation_id"]]
    longitude, latitude = feature["geometry"]["coordinates"]
    assert float(latitude) == float(row["latitude"])
    assert float(longitude) == float(row["longitude"])
whiskey_1998 = formation_by_id["cc_e5724a3476de"]
whiskey_2000 = formation_by_id["cc_80f4a64d3689"]
aloha_1994 = formation_by_id["cc_8a68d8a0471b"]
assert whiskey_1998["site_status"] == "corroborated_field"
assert abs(float(whiskey_1998["latitude"]) - 45.1714056) < 1e-7
assert whiskey_2000["site_status"] == "corroborated_field"
assert abs(float(whiskey_2000["longitude"]) - (-122.7260611)) < 1e-7
assert aloha_1994["site_status"] == "registered_site"
assert aloha_1994["site_coordinate_method"] == "source_report_degrees_minutes"
assert aloha_1994["site_alignment_eligible"] == "false"
assert {row["formation_id"] for row in formations if row["site_alignment_eligible"] == "true"} == {
    "cc_e5724a3476de", "cc_80f4a64d3689",
}
assert {"a_07151793fc35f4", "iccra_03aa54e9073ccbd8"}.issubset(set(whiskey_1998["assertion_ids"].split("; ")))
assert {"a_cf84a25d4ce632", "sx_vigay_6607ed8489280db3", "iccra_a8eeec8432699614"}.issubset(
    set(whiskey_2000["assertion_ids"].split("; "))
)
assert {"a_bb14f2ae43a320", "iccra_c100c7083922d347"} == set(aloha_1994["assertion_ids"].split("; "))
assert "cc_969282bc2775" in aloha_1994["merged_alias_formation_ids"].split("; ")
assert not {"cc_d85d5c118449", "cc_19fdee41af91", "cc_6ab089f895ba", "cc_969282bc2775"} & set(formation_by_id)

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
    site = formation_by_id[row["formation_id"]]
    assert site["site_status"] in {"corroborated_field", "registered_site"}
    assert float(row["origin_uncertainty_m"]) >= float(site["site_coordinate_uncertainty_m"])
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
    assert properties["formation_id"] in {
        feature["properties"]["formation_id"] for feature in site_geojson["features"]
    }
    assert float(properties["origin_uncertainty_m"]) >= float(
        formation_by_id[properties["formation_id"]]["site_coordinate_uncertainty_m"]
    )
assert "no demonstrated predictive validity" in rays["metadata"]["notice"]
hits = rows("alignment_hits.csv")
assert len(hits) == 0
for row in hits:
    assert row["eligible_for_statistical_test"] in {"yes", "no"}
    assert row["spatial_quality_status"]
    assert row["hit_geometry"] == "centerline_corridor"
    assert row["temporal_relation"] in {"earlier", "later", "overlap_or_indeterminate"}
    if row["eligible_for_statistical_test"] == "yes":
        assert float(row["combined_spatial_uncertainty_km"]) <= float(row["corridor_km"])
assert not any(row["eligible_for_statistical_test"] == "yes" for row in hits)

provisional_rows = rows("provisional_orientation_observations.csv")
provisional_rays = json.loads((ROOT / "web" / "data" / "provisional_orientation_rays.geojson").read_text(encoding="utf-8"))
assert len(provisional_rows) == len(provisional_rays["features"]) == 1
provisional = provisional_rays["features"][0]["properties"]
assert provisional["formation_id"] == "cc_e5724a3476de"
assert provisional["azimuth_true_deg"] == 110.0
assert provisional["azimuth_uncertainty_deg"] == 3.0
assert provisional["excluded_from_alignment_calculations"] == "yes"
assert provisional["predictive_validity"] == "none_demonstrated"
assert provisional["evidence_kind"] == "user_supplied_registration_screenshot"
assert provisional["evidence_sha256_subject"] == "user_supplied_pic5_registration_screenshot"
assert provisional["origin_uncertainty_m"] >= float(whiskey_1998["site_coordinate_uncertainty_m"])

registered_overlays = json.loads(
    (ROOT / "web" / "data" / "registered_overlays.json").read_text(encoding="utf-8")
)
formation_images = json.loads(
    (ROOT / "web" / "data" / "formation_images.json").read_text(encoding="utf-8")
)
validate_registered_overlay(ROOT)
overlays_by_id = {item["overlay_id"]: item for item in registered_overlays["overlays"]}
core_overlay_ids = {
    "whiskey-hill-1998-user-registration",
    "hubbard-2000-three-lobe-registration",
    "mayville-kekoskee-2003-source-gps-registration",
    "howell-township-2003-source-gps-registration",
    "jupiter-2005-source-gps-scene-placement",
    "wausau-1997-usgs-followup-registration",
}
scene_placement_specs = json.loads(
    (ROOT / "data" / "provisional_image_scene_placements.json").read_text(encoding="utf-8")
)["placements"]
scene_placement_ids = {item["overlay_id"] for item in scene_placement_specs}
commons_scene_specs = json.loads(
    (ROOT / "data" / "commons_scene_placements_draft.json").read_text(encoding="utf-8")
)["placements"]
commons_scene_ids = {
    item["overlay_id"].removesuffix("-draft") for item in commons_scene_specs
}
commons_same_flight_specs = json.loads(
    (ROOT / "data" / "commons_same_flight_scene_placements.json").read_text(
        encoding="utf-8"
    )
)["placements"]
commons_same_flight_ids = {
    item["overlay_id"] for item in commons_same_flight_specs
}
commons_reviewed_geometry_specs = json.loads(
    (ROOT / "data" / "commons_reviewed_geometry_placements.json").read_text(
        encoding="utf-8"
    )
)["placements"]
commons_reviewed_geometry_ids = {
    item["overlay_id"] for item in commons_reviewed_geometry_specs
}
assert set(overlays_by_id) == (
    core_overlay_ids | scene_placement_ids | commons_scene_ids
    | commons_same_flight_ids | commons_reviewed_geometry_ids
)
assert len(registered_overlays["overlays"]) >= 9
assert any(
    formation_by_id[item["formation_id"]]["country_code"] not in {"", "US"}
    for item in registered_overlays["overlays"]
)
image_relationships = [
    (formation_id, image)
    for formation_id, images in formation_images["images_by_formation"].items()
    for image in images
]
unique_source_image_urls = {image["image_url"] for _, image in image_relationships}
catalog_metadata = formation_images["metadata"]
assert catalog_metadata["schema_version"] == "crop-circle-atlas/formation-images/v2"
assert catalog_metadata["unique_image_count"] == len(unique_source_image_urls) >= 3000
assert catalog_metadata["formation_image_link_count"] == len(image_relationships) >= 3100
assert catalog_metadata["formation_count"] == len(formation_images["images_by_formation"]) >= 1800
assert catalog_metadata["us_unique_image_count"] >= 479
assert catalog_metadata["non_us_unique_image_count"] >= 2500
assert catalog_metadata["unknown_country_unique_image_count"] >= 0
assert catalog_metadata["unverified_unique_image_link_count"] >= 1
assert catalog_metadata["rights_gated_unique_image_count"] >= 2500
assert catalog_metadata["source_link_counts"]["Wikimedia Commons"] >= 11
assert catalog_metadata["overlay_placement_count"] == len(registered_overlays["overlays"])
source_image_rows = {(row["image_url"], row["sha256"]) for row in iccra_images}
overlay_image_pairs = {
    (item["formation_id"], item["source_image_url"])
    for item in registered_overlays["overlays"]
}
mapped_catalog_relationships = 0
for formation_id, image in image_relationships:
    assert formation_id in formation_by_id
    assert image["image_url"].startswith("https://")
    assert "cache_path" not in image and "local_path" not in image
    assert image["pixel_bytes_packaged"] is False
    expected_status = "mapped_overlay" if (formation_id, image["image_url"]) in overlay_image_pairs else "source_link_only_not_georegistered"
    assert image["placement_status"] == expected_status
    if image["source_name"] == "ICCRA":
        assert (image["image_url"], image["sha256"]) in source_image_rows
        assert image["rights_status"] == "not_cleared"
        assert image["pixel_display_policy"] == "remote_source_on_explicit_user_action"
    elif image["source_name"] == "Wikimedia Commons":
        assert image["embedding_allowed"] is True
        assert image["license_url"].startswith("https://")
    else:
        assert image["embedding_allowed"] is False
        assert image["pixel_display_policy"] == "link_only_rights_gated"
    mapped_catalog_relationships += expected_status == "mapped_overlay"
assert catalog_metadata["mapped_catalog_image_count"] == mapped_catalog_relationships
overlay = overlays_by_id["whiskey-hill-1998-user-registration"]
assert overlay["formation_id"] == provisional["formation_id"]
assert overlay["assertion_id"] == provisional["assertion_id"]
assert overlay["assertion_id"] in whiskey_1998["assertion_ids"].split("; ")
iccra_assertion = next(row for row in iccra if row["assertion_id"] == overlay["assertion_id"])
assert overlay["source_page_url"] == iccra_assertion["source_record_url"] == provisional["evidence_url"]
iccra_image = next(row for row in iccra_images if row["image_url"] == overlay["source_image_url"])
assert overlay["assertion_id"] in iccra_image["assertion_ids"].split("; ")
assert overlay["source_image_sha256"] == iccra_image["sha256"]
assert iccra_image["public_redistribution_status"] == "not_cleared"
assert overlay["source_photo_pixels"] == "remote_source_link_only"
assert overlay["rights_status"] == "not_cleared_for_redistribution"
assert overlay["show_by_default"] is False
assert abs(float(overlay["center"][0]) - float(whiskey_1998["latitude"])) < 1e-6
assert abs(float(overlay["center"][1]) - float(whiskey_1998["longitude"])) < 1e-6
assert float(overlay["coordinate_uncertainty_m"]) == float(whiskey_1998["site_coordinate_uncertainty_m"])
assert float(overlay["bearing_true_deg"]) == float(provisional["azimuth_true_deg"])
assert float(overlay["bearing_uncertainty_deg"]) == float(provisional["azimuth_uncertainty_deg"])

hubbard_overlay = overlays_by_id["hubbard-2000-three-lobe-registration"]
assert hubbard_overlay["formation_id"] == whiskey_2000["formation_id"]
assert hubbard_overlay["assertion_id"] in whiskey_2000["assertion_ids"].split("; ")
hubbard_assertion = next(row for row in iccra if row["assertion_id"] == hubbard_overlay["assertion_id"])
assert hubbard_overlay["source_page_url"] == hubbard_assertion["source_record_url"]
hubbard_image = next(row for row in iccra_images if row["image_url"] == hubbard_overlay["source_image_url"])
assert hubbard_overlay["source_image_sha256"] == hubbard_image["sha256"]
assert hubbard_image["public_redistribution_status"] == "not_cleared"
assert hubbard_overlay["source_photo_pixels"] == "remote_source_link_only"
assert hubbard_overlay["rights_status"] == "not_cleared_for_redistribution"
assert hubbard_overlay["show_by_default"] is False
assert "coordinate_uncertainty_m" not in hubbard_overlay
assert hubbard_overlay["coordinate_uncertainty_status"] == "not_independently_quantified"
assert hubbard_overlay["display_corner_sensitivity_envelope_m"] == 35
assert hubbard_overlay["registration_status"] == "approximate_visual_registration"
assert hubbard_overlay["display_geometry_status"] == "approximate_provisional_local_affine_placement"
assert hubbard_overlay["display_corner_sensitivity_kind"] == "conditional_detector_sensitivity_envelope_not_confidence_interval"
assert hubbard_overlay["registration_observation_id"] == "regobs_hubbard_2000_three_lobe_v1"
assert abs(float(hubbard_overlay["center"][0]) - float(whiskey_2000["latitude"])) < 0.0005
assert abs(float(hubbard_overlay["center"][1]) - float(whiskey_2000["longitude"])) < 0.0005
assert hubbard_overlay["formal_alignment_status"] == "excluded_pending_independent_ground_control"

new_overlay_expectations = {
    "mayville-kekoskee-2003-source-gps-registration": (
        "cc_af45ba1f38f5", "iccra_5f74cb1fb1dfed25",
        "provisional_source_gps_geometry_registration",
    ),
    "howell-township-2003-source-gps-registration": (
        "cc_801777bd00f0", "iccra_09278c2f8bfe83d8",
        "provisional_source_gps_geometry_registration",
    ),
    "jupiter-2005-source-gps-scene-placement": (
        "cc_380f14de702d", "iccra_8b50ef9c87fcc775",
        "provisional_source_gps_scene_placement",
    ),
    "wausau-1997-usgs-followup-registration": (
        "cc_5d10e918a4b4", "iccra_0f395c638d0a0d2c",
        "provisional_historical_ortho_landmark_registration",
    ),
}
for overlay_id, (formation_id, assertion_id, registration_status) in new_overlay_expectations.items():
    registered = overlays_by_id[overlay_id]
    formation = formation_by_id[formation_id]
    assert registered["formation_id"] == formation_id
    assert registered["assertion_id"] == assertion_id
    assert assertion_id in formation["assertion_ids"].split("; ")
    source_image = next(row for row in iccra_images if row["image_url"] == registered["source_image_url"])
    assert registered["source_image_sha256"] == source_image["sha256"]
    assert registered["source_page_url"] == source_image["source_page_url"]
    assert source_image["public_redistribution_status"] == "not_cleared"
    assert registered["source_photo_pixels"] == "remote_source_link_only"
    assert registered["rights_status"] == "not_cleared_for_redistribution"
    assert registered["show_by_default"] is False
    assert registered["registration_status"] == registration_status
    assert float(registered["coordinate_uncertainty_m"]) == float(
        formation["site_coordinate_uncertainty_m"]
    )
    # Site CSV coordinates are serialized to seven decimal places; require the
    # higher-precision overlay center to agree within a centimetre-scale bound.
    assert abs(float(registered["center"][0]) - float(formation["site_latitude"])) < 5e-8
    assert abs(float(registered["center"][1]) - float(formation["site_longitude"])) < 5e-8
    assert registered["formal_alignment_status"].startswith("excluded_pending_")

commons_overlay = overlays_by_id["commons-diessenhofen-20080715-164408"]
assert commons_overlay["formation_id"] == "cc_2deeb6879ebf"
assert commons_overlay["assertion_id"] == "commons_event_diessenhofen_20080715"
assert commons_overlay["source_image_sha256"] == "67c44d76a64373becbab575f92bb3f44213c2b77a4c96b5c4d4c4af11dd930f0"
assert commons_overlay["rights_status"] == "CC BY-SA 3.0"
assert commons_overlay["embedding_allowed"] is True
assert commons_overlay["license_url"] == "https://creativecommons.org/licenses/by-sa/3.0"
assert commons_overlay["formal_alignment_status"].startswith("excluded_pending_")
assert len(formation_images["images_by_formation"]["cc_2deeb6879ebf"]) == 9

kml_path = ROOT / "exports" / "crop_circle_atlas.kml"
kml_tree = ET.parse(kml_path)
kml_root = kml_tree.getroot()
kml_ns = {"k": "http://www.opengis.net/kml/2.2"}
assert len(kml_root.findall(".//k:Point", kml_ns)) == len(geocoded)
assert len(kml_root.findall(".//k:LineString", kml_ns)) == len(orientations) + len(provisional_rows)
linked_overlays = kml_root.findall(".//k:GroundOverlay", kml_ns)
expected_remote_overlays = [
    item for item in registered_overlays["overlays"] if item.get("embedding_allowed") is True
]
assert len(linked_overlays) == len(expected_remote_overlays)
assert all(item.find("k:visibility", kml_ns).text == "1" for item in linked_overlays)
assert all(
    re.fullmatch(r"[0-9a-f]{8}", item.find("k:color", kml_ns).text)
    for item in linked_overlays
)
kml_text = kml_path.read_text(encoding="utf-8")
assert "Experimental projections from documented orientations" in kml_text
assert "no demonstrated predictive validity" in kml_text
assert "Reference localities (not formation sites)" in kml_text
assert "Provisional user-demonstrated axes" in kml_text
assert "remote_source_link_only_not_packaged" in kml_text
assert "commons-diessenhofen-20080715-164408" in kml_text
assert "44.8737785" in kml_text
kmz_path = ROOT / "exports" / "crop_circle_atlas.kmz"
with zipfile.ZipFile(kmz_path) as archive:
    assert archive.testzip() is None
    assert archive.namelist() == ["doc.kml"]
    assert archive.read("doc.kml") == kml_path.read_bytes()
overlay_audit = rows("image_overlay_audit.csv")
assert overlay_audit == [
    {
        "asset_id": item["overlay_id"],
        "status": "included_remote_link",
        "reason": "pixels_not_packaged_provisional",
    }
    for item in registered_overlays["overlays"]
]
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
        "Expansion Exclusions", "Field Site Reviews", "Alias Reviews",
        "Provisional Orientations", "Overlay Audit",
    ):
        assert f'name="{sheet_name}"' in workbook_xml, sheet_name
    table_refs = {}
    for member in archive.namelist():
        if member.startswith("xl/tables/table") and member.endswith(".xml"):
            table = ET.fromstring(archive.read(member))
            table_refs[table.attrib["displayName"]] = table.attrib["ref"]
    assert table_refs["FormationsTable"] == "A1:AP7746"
    assert table_refs["FieldSiteReviewsTable"] == f"A1:T{len(site_resolution_rows) + 1}"
    assert table_refs["AliasReviewsTable"].endswith("5")
    assert table_refs["OverlayAuditTable"] == f"A1:C{len(overlay_audit) + 1}"

for needed in (
    "index.html", "app.js", "styles.css", "favicon.svg", "methodology.html", "georef.html",
    "georef.css", "georef.js", "georef-core.mjs", "georef-atlas-adapter.mjs",
    "atlas-georef-integration.mjs", "atlas-geodesy.mjs", "projective-image-overlay.mjs",
):
    assert (ROOT / "web" / needed).exists(), needed
assert "GeoNames CC BY 4.0" in (ROOT / "web" / "index.html").read_text(encoding="utf-8")
assert "GeoNames under CC BY 4.0" in kml_path.read_text(encoding="utf-8")
web_index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
web_app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
web_styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
georef_html = (ROOT / "web" / "georef.html").read_text(encoding="utf-8")
assert "Show rough locality references on map" in web_index
assert "Load and zoom to registered image" in web_index
assert "Mapped source-image overlays" in web_index
assert "Source image archive" in web_index
assert 'id="sourceImageGallery"' in web_index
assert 'id="toggleSourceImages"' in web_index
assert "Export unqualified hypothesis KML" in web_index
assert 'id="resultsList"' in web_index
assert "unqualified_manual_hypothesis" in web_app
assert "Provisional registered axes" in web_app
assert "Registered aerial-photo footprints" in web_app
assert "renderSourceImageGallery" in web_app
assert "sourceImagesByFormation" in web_app
assert "sitePointPane" in web_app and "localityPointPane" in web_app
assert "radius: 6, color: '#ffd84d', weight: 2.5, opacity: 1, dashArray: '3 2'" in web_app
assert "fillColor: '#ffd84d', fillOpacity: 0.08, renderer: localityRenderer" in web_app
assert "fillColor: verified ? '#2d9e91' : '#ffd84d'" in web_app
assert ".key-dot.reference { color:var(--candidate); background:transparent; border-style:dashed; }" in web_styles
assert "hollow dashed yellow markers are rough locality references" in web_index
assert 'href="styles.css?v=20260722.2"' in web_index
assert 'src="app.js?v=20260722.2"' in web_index
assert "registered_overlays.json?v=20260722.2" in web_app
assert "formation_images.json?v=20260722.2" in web_app
assert "overlayRecords.length.toLocaleString()" in web_app
assert "activeOverlay?.remove()" in web_app
assert "await selectFormation(id, true)" in web_app
assert "map.closePopup()" in web_app
assert "Locality centroids and unresolved reports are excluded" in web_app
assert "image/tiff" not in georef_html
readme = (ROOT / "README.md").read_text(encoding="utf-8")
source_register_text = (ROOT / "docs" / "SOURCE_REGISTER.md").read_text(encoding="utf-8")
for phrase in ("8,391 source assertions", "7,745", "449 new normalized source keys"):
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
