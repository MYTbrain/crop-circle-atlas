from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMATIONS_PATH = ROOT / "data" / "formations.csv"
ICCRA_IMAGES_PATH = ROOT / "data" / "iccra_image_links.csv"
GLOBAL_IMAGES_PATH = ROOT / "data" / "global_source_image_links.csv"
REVIEWED_US_ARCHIVE_IMAGES_PATH = ROOT / "data" / "reviewed_us_archive_image_links.json"
COMMONS_IMAGES_PATH = ROOT / "data" / "commons_crop_circle_images.csv"
COMMONS_ASSERTIONS_PATH = ROOT / "data" / "commons_crop_circle_assertions.csv"
COMMONS_EVENT_ASSERTIONS_PATH = ROOT / "data" / "commons_crop_circle_event_assertions.csv"
OVERLAYS_PATH = ROOT / "web" / "data" / "registered_overlays.json"
INDEX_PATH = ROOT / "web" / "data" / "formation_index.json"
OUTPUT_PATH = ROOT / "web" / "data" / "formation_images.json"


def split_ids(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(";") if item.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_reviewed_us_archive_images() -> list[dict[str, str]]:
    """Expand the human-reviewed U.S. archive seed into link-only image rows."""
    if not REVIEWED_US_ARCHIVE_IMAGES_PATH.is_file():
        return []
    payload = json.loads(REVIEWED_US_ARCHIVE_IMAGES_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for report in payload.get("reports", []):
        for image_url in report.get("image_urls", []):
            link_id = "rimg_" + hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:20]
            rows.append(
                {
                    "image_link_id": link_id,
                    "assertion_id": report.get("assertion_id", ""),
                    "formation_id": report.get("formation_id", ""),
                    "source_id": payload.get("source_id", "crop_circle_archives_us"),
                    "source_name": payload.get("source_name", "Crop Circle Archives"),
                    "source_record_url": report.get("source_record_url", ""),
                    "image_url": image_url,
                    "image_kind": "photograph_or_unspecified",
                    "alt_text": f"Source photograph for {report.get('place', 'U.S. crop-circle report')}",
                    "title_text": report.get("match_basis", ""),
                    "image_http_status": "200",
                    "rights_status": payload.get(
                        "rights_status", "link_only_archive_images_not_redistributed"
                    ),
                    "embedding_allowed": str(
                        bool(payload.get("embedding_allowed", False))
                    ).lower(),
                    "pixel_bytes_packaged": str(
                        bool(payload.get("pixel_bytes_packaged", False))
                    ).lower(),
                    "placement_status": "source_link_only_not_georegistered",
                }
            )
    return rows


def text_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def displayable(entry: dict) -> bool:
    return bool(entry.get("embedding_allowed")) or entry.get("pixel_display_policy") == (
        "remote_source_on_explicit_user_action"
    )


def public_image_entry(
    image: dict[str, str], assertion_id: str, overlay: dict | None = None, *, source_kind: str
) -> dict:
    if source_kind == "commons":
        entry = {
            "image_link_id": image.get("commons_image_id", ""),
            "assertion_id": assertion_id,
            "source_id": "wikimedia_commons",
            "source_name": "Wikimedia Commons",
            "source_page_url": image.get("commons_page_url", ""),
            "source_record_url": image.get("commons_page_url", ""),
            "image_url": image.get("original_file_url", ""),
            "image_kind": image.get("image_kind", "photograph_or_unspecified"),
            "alt_text": image.get("description", ""),
            "title_text": image.get("file_title", ""),
            "width": positive_int(image.get("width_px")),
            "height": positive_int(image.get("height_px")),
            "sha256": overlay.get("source_image_sha256", "") if overlay else "",
            "source_hash": image.get("sha1", ""),
            "source_hash_algorithm": image.get("hash_algorithm", ""),
            "rights_status": image.get("license_short_name", "open_license_verified"),
            "license_short_name": image.get("license_short_name", ""),
            "license_url": image.get("license_url", ""),
            "author": image.get("author", ""),
            "attribution_required": text_bool(image.get("attribution_required")),
            "embedding_allowed": text_bool(image.get("embedding_allowed")),
            "pixel_display_policy": "remote_open_license_on_explicit_user_action",
            "pixel_bytes_packaged": False,
            "link_verification_status": "commons_api_revision_verified",
            "placement_status": "mapped_overlay" if overlay else "source_link_only_not_georegistered",
        }
    elif source_kind == "global":
        source_pages = split_ids(image.get("source_page_urls", ""))
        entry = {
            "image_link_id": image.get("image_link_id", ""),
            "assertion_id": assertion_id,
            "source_id": image.get("source_id", ""),
            "source_name": image.get("source_name", ""),
            "source_page_url": image.get("source_record_url", "")
            or (source_pages[0] if source_pages else ""),
            "source_record_url": image.get("source_record_url", ""),
            "image_url": image.get("image_url", ""),
            "image_kind": image.get("image_kind", "photograph_or_unspecified"),
            "alt_text": image.get("alt_text", ""),
            "title_text": image.get("title_text", ""),
            "width": positive_int(image.get("width")),
            "height": positive_int(image.get("height")),
            "sha256": image.get("image_sha256", ""),
            "rights_status": image.get("rights_status", "link_only_not_cleared"),
            "embedding_allowed": text_bool(image.get("embedding_allowed")),
            "pixel_display_policy": (
                "remote_source_on_explicit_user_action"
                if text_bool(image.get("embedding_allowed"))
                else "link_only_rights_gated"
            ),
            "pixel_bytes_packaged": text_bool(image.get("pixel_bytes_packaged")),
            "link_verification_status": (
                "http_200"
                if image.get("image_http_status", "").strip() == "200"
                else "not_requested"
            ),
            "placement_status": "mapped_overlay" if overlay else image.get(
                "placement_status", "source_link_only_not_georegistered"
            ),
        }
    else:
        entry = {
            "image_link_id": image.get("image_link_id", ""),
            "assertion_id": assertion_id,
            "source_id": "iccra",
            "source_name": "ICCRA",
            "source_page_url": image.get("source_page_url", ""),
            "source_record_url": image.get("source_page_url", ""),
            "image_url": image.get("image_url", ""),
            "image_kind": image.get("image_kind", "photograph_or_unspecified"),
            "alt_text": image.get("alt_text", ""),
            "title_text": image.get("title_text", ""),
            "width": positive_int(image.get("width")),
            "height": positive_int(image.get("height")),
            "sha256": image.get("sha256", ""),
            "rights_status": image.get("public_redistribution_status", "not_cleared"),
            "embedding_allowed": False,
            "pixel_display_policy": "remote_source_on_explicit_user_action",
            "pixel_bytes_packaged": False,
            "link_verification_status": "http_200",
            "placement_status": "mapped_overlay" if overlay else "source_link_only_not_georegistered",
        }
    if overlay:
        entry["overlay_id"] = overlay.get("overlay_id", "")
        entry["registration_status"] = overlay.get("registration_status", "")
    return entry


def build_catalog() -> dict:
    formations = load_csv(FORMATIONS_PATH)
    iccra_images = load_csv(ICCRA_IMAGES_PATH)
    global_images = load_csv(GLOBAL_IMAGES_PATH) + load_reviewed_us_archive_images()
    commons_images = load_csv(COMMONS_IMAGES_PATH)
    commons_assertions = load_csv(COMMONS_ASSERTIONS_PATH)
    commons_event_assertions = load_csv(COMMONS_EVENT_ASSERTIONS_PATH)
    overlays = json.loads(OVERLAYS_PATH.read_text(encoding="utf-8"))
    index_payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    assertion_to_formation: dict[str, str] = {}
    country_by_formation: dict[str, str] = {}
    for formation in formations:
        formation_id = formation["formation_id"]
        canonical_id = formation.get("alias_of", "") or formation_id
        if not formation.get("alias_of", ""):
            country_by_formation[canonical_id] = formation.get("country_code", "")
        for assertion_id in split_ids(formation.get("assertion_ids", "")):
            assertion_to_formation[assertion_id] = canonical_id

    overlays_by_url_and_formation = {
        (item.get("source_image_url", ""), item.get("formation_id", "")): item
        for item in overlays.get("overlays", [])
        if item.get("source_image_url") and item.get("formation_id")
    }
    iccra_rows_by_url = {
        image.get("image_url", ""): image for image in iccra_images if image.get("image_url")
    }
    images_by_formation: dict[str, dict[str, dict]] = defaultdict(dict)

    for image in iccra_images:
        if image.get("http_status") != "200" or image.get("is_iccra_hosted", "").lower() != "true":
            continue
        for assertion_id in split_ids(image.get("assertion_ids", "")):
            formation_id = assertion_to_formation.get(assertion_id, "")
            image_url = image.get("image_url", "")
            if not formation_id or not image_url:
                continue
            overlay = overlays_by_url_and_formation.get((image_url, formation_id))
            images_by_formation[formation_id][image_url] = public_image_entry(
                image, assertion_id, overlay, source_kind="iccra"
            )

    for image in global_images:
        image_url = image.get("image_url", "")
        assertion_id = image.get("assertion_id", "")
        formation_id = image.get("formation_id", "") or assertion_to_formation.get(assertion_id, "")
        if not image_url or not formation_id or formation_id not in country_by_formation:
            continue
        status = image.get("image_http_status", "")
        if status and status not in {"200", "not_requested"}:
            continue
        overlay = overlays_by_url_and_formation.get((image_url, formation_id))
        images_by_formation[formation_id][image_url] = public_image_entry(
            image, assertion_id, overlay, source_kind="global"
        )

    commons_by_id = {
        row.get("commons_image_id", ""): row
        for row in commons_images
        if row.get("commons_image_id") and text_bool(row.get("open_license_verified"))
    }
    for event in commons_event_assertions:
        formation_id = event.get("formation_id", "")
        assertion_id = event.get("assertion_id", "")
        if not formation_id or formation_id not in country_by_formation:
            continue
        for image_id in split_ids(event.get("commons_image_ids", "")):
            image = commons_by_id.get(image_id)
            if not image:
                continue
            image_url = image.get("original_file_url", "")
            overlay = overlays_by_url_and_formation.get((image_url, formation_id))
            images_by_formation[formation_id][image_url] = public_image_entry(
                image, assertion_id, overlay, source_kind="commons"
            )
    for assertion in commons_assertions:
        # Publish only exact event links or a separately reviewed later photograph of
        # that event. Broader place/year candidates remain research-only.
        if assertion.get("match_status") not in {
            "exact_place_and_date",
            "reviewed_same_event_later_documentation",
        }:
            continue
        formation_id = assertion.get("matched_formation_id", "")
        image = commons_by_id.get(assertion.get("commons_image_id", ""))
        if not image or not formation_id or formation_id not in country_by_formation:
            continue
        image_url = image.get("original_file_url", "")
        overlay = overlays_by_url_and_formation.get((image_url, formation_id))
        images_by_formation[formation_id][image_url] = public_image_entry(
            image,
            assertion.get("commons_assertion_id", ""),
            overlay,
            source_kind="commons",
        )

    # Some report-document images lack assertion IDs at the crawl edge. A reviewed
    # overlay supplies the explicit relationship without packaging its pixels.
    for overlay in overlays.get("overlays", []):
        image_url = overlay.get("source_image_url", "")
        formation_id = overlay.get("formation_id", "")
        if not image_url or not formation_id or image_url in images_by_formation.get(formation_id, {}):
            continue
        image = iccra_rows_by_url.get(image_url)
        if not image:
            continue
        images_by_formation[formation_id][image_url] = public_image_entry(
            image, overlay.get("assertion_id", ""), overlay, source_kind="iccra"
        )

    normalized = {
        formation_id: sorted(
            entries.values(), key=lambda item: (item["source_name"], item["image_kind"], item["image_url"])
        )
        for formation_id, entries in sorted(images_by_formation.items())
    }
    relationships = [entry for entries in normalized.values() for entry in entries]
    unique_image_urls = {entry["image_url"] for entry in relationships}
    us_unique_image_urls = {
        entry["image_url"]
        for formation_id, entries in normalized.items()
        if country_by_formation.get(formation_id) == "US"
        for entry in entries
    }
    non_us_unique_image_urls = {
        entry["image_url"]
        for formation_id, entries in normalized.items()
        if country_by_formation.get(formation_id) not in {"", "US"}
        for entry in entries
    }
    unknown_country_unique_image_urls = {
        entry["image_url"]
        for formation_id, entries in normalized.items()
        if not country_by_formation.get(formation_id)
        for entry in entries
    }
    display_policy_by_url: dict[str, list[bool]] = defaultdict(list)
    for entry in relationships:
        display_policy_by_url[entry["image_url"]].append(displayable(entry))
    rights_gated_urls = {
        url for url, policies in display_policy_by_url.items() if not any(policies)
    }
    verification_by_url: dict[str, list[str]] = defaultdict(list)
    for entry in relationships:
        verification_by_url[entry["image_url"]].append(
            entry.get("link_verification_status", "not_requested")
        )
    unverified_urls = {
        url
        for url, statuses in verification_by_url.items()
        if not any(status in {"http_200", "commons_api_revision_verified"} for status in statuses)
    }
    source_link_counts = Counter(entry["source_name"] for entry in relationships)
    mapped_catalog_image_count = sum(
        entry["placement_status"] == "mapped_overlay" for entry in relationships
    )
    return {
        "metadata": {
            "schema_version": "crop-circle-atlas/formation-images/v2",
            "generated_at": index_payload.get("metadata", {}).get("generated_at", ""),
            "unique_image_count": len(unique_image_urls),
            "formation_image_link_count": len(relationships),
            "formation_count": len(normalized),
            "us_unique_image_count": len(us_unique_image_urls),
            "non_us_unique_image_count": len(non_us_unique_image_urls),
            "unknown_country_unique_image_count": len(unknown_country_unique_image_urls),
            "unverified_unique_image_link_count": len(unverified_urls),
            "rights_gated_unique_image_count": len(rights_gated_urls),
            "displayable_unique_image_count": len(unique_image_urls - rights_gated_urls),
            "mapped_catalog_image_count": mapped_catalog_image_count,
            "overlay_placement_count": len(overlays.get("overlays", [])),
            "source_link_counts": dict(sorted(source_link_counts.items())),
            "rights_notice": (
                "The atlas packages no source pixels. Openly licensed or explicitly enabled images load "
                "from their source host only after a user action; all other records remain link-only. "
                "An image link is not a georegistration or a publication-rights grant."
            ),
        },
        "images_by_formation": normalized,
    }


def main() -> None:
    payload = build_catalog()
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    metadata = payload["metadata"]
    print(
        f"unique_images={metadata['unique_image_count']} "
        f"links={metadata['formation_image_link_count']} "
        f"formations={metadata['formation_count']} "
        f"us_unique_images={metadata['us_unique_image_count']} "
        f"non_us_unique_images={metadata['non_us_unique_image_count']} "
        f"rights_gated={metadata['rights_gated_unique_image_count']} "
        f"mapped_catalog_images={metadata['mapped_catalog_image_count']} "
        f"overlay_placements={metadata['overlay_placement_count']} output={OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
