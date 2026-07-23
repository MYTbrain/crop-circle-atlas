from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMATIONS_PATH = ROOT / "data" / "formations.csv"
IMAGES_PATH = ROOT / "web" / "data" / "formation_images.json"
OVERLAYS_PATH = ROOT / "web" / "data" / "registered_overlays.json"
SITE_CANDIDATES_PATH = ROOT / "data" / "global_source_site_candidates.csv"
ARCHIVE_PATH = ROOT / "data" / "reviewed_us_archive_image_links.json"
CSV_OUTPUT_PATH = ROOT / "data" / "overlay_production_queue.csv"
JSON_OUTPUT_PATH = ROOT / "data" / "overlay_production_queue.json"


ARCHIVE_EVIDENCE = {
    "cc_104e3b95dd75": {
        "clues": ["approximately 20 miles south of Teton City", "Bryon Parker", "Richard Nielsen"],
        "landmarks": ["field and road pattern south of Teton City"],
    },
    "cc_24e959df4a14": {
        "clues": ["Molex property", "Steve Berning farm", "Naperville soybean field"],
        "landmarks": ["Molex campus buildings", "property and field boundaries"],
    },
    "cc_2152af98e2d7": {
        "clues": ["near Seip Mound", "Paint Creek", "Bainbridge", "Ross County"],
        "landmarks": ["Seip Earthworks", "Paint Creek", "persistent road and field boundaries"],
    },
    "cc_7cdb63cfe429": {
        "clues": ["Serpent Mound", "Brush Creek", "Peebles", "Locust Grove"],
        "landmarks": ["Serpent Mound", "Brush Creek", "persistent road network"],
    },
    "cc_ae1b8ee2ae1f": {
        "clues": ["Rockville Road", "Suisun Valley Road", "Solano County"],
        "landmarks": ["Rockville Road", "Suisun Valley Road", "road intersection", "field corners"],
    },
    "cc_3fb745fb7416": {
        "clues": ["Miamisburg Mound", "source-reported formation coordinate"],
        "landmarks": ["Miamisburg Mound", "persistent roads", "field boundaries"],
    },
    "cc_64e65753ca3c": {
        "clues": ["Gene Smallidge farm", "Cottage Grove"],
        "landmarks": ["farm buildings", "field boundaries", "tree lines"],
    },
    "cc_a20bb389770e": {
        "clues": ["Swoboda field", "Tilden", "Chippewa County"],
        "landmarks": ["roadside field boundaries"],
    },
    "cc_ad68564a4282": {
        "clues": ["junction of Cordelia Road and Hale Ranch Road", "Solano County"],
        "landmarks": ["Cordelia Road", "Hale Ranch Road", "road junction", "field corners"],
    },
    "cc_c8e2401c7fbf": {
        "clues": ["Spanish Fork barley field", "landowner property"],
        "landmarks": ["field boundaries", "roads", "buildings visible in aerial frame"],
    },
    "cc_c3c841d2f230": {
        "clues": ["highway between Port Arthur and Sabine Pass", "low wet field"],
        "landmarks": ["highway", "wire fence", "drainage pattern"],
    },
    "cc_72e3a77239de": {
        "clues": ["Northwood", "airport vicinity", "local grain elevator"],
        "landmarks": ["airport runway", "road grid", "field boundaries"],
    },
    "cc_74854ad00686": {
        "clues": ["Geneseo soybean field", "farmer Jim Stah"],
        "landmarks": ["field boundaries", "roads", "farm buildings where visible"],
    },
    "cc_d77797cdea69": {
        "clues": ["Sandyville", "Stark County"],
        "landmarks": ["roads", "field boundaries", "tree lines where visible"],
    },
    "cc_cee3a40aace5": {
        "clues": ["Huntingburg", "Dubois County wheat field"],
        "landmarks": ["roads", "field boundaries", "farm buildings where visible"],
    },
    "cc_27e66142db39": {
        "clues": ["two circles at field edge", "oil rig behind circles", "Herington"],
        "landmarks": ["field edge", "road grid"],
    },
}


BLOCKED_ARCHIVE = {
    "cc_289dd87e4b7c": "Exact Coles County location was deliberately withheld by the source.",
    "cc_eb8ed861eac4": "The source says the aerial photographer could not provide the actual Northern Colorado location.",
    "cc_7e1b225d2395": "The location witness supplied no usable contact or field location.",
}


PRODUCTION_REVIEW = {
    "cc_003c3da5c31b": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact 2018-06-23 publisher target, the earlier 2018-06-09 "
            "formation coordinate visible in the same wide frame, the Hackpen White "
            "Horse, and the road junction identify one candidate field. Tests across "
            "the long oblique scene produced incompatible local and terrain transforms, "
            "so no single defensible full-frame footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_5d5c33e3e3cf": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher map target, field shape, road, parking/access geometry, "
            "wooded Danebury earthworks, and multiple wide aerials identify one "
            "candidate field. Strong perspective and terrain parallax leave only the "
            "formation anchor defensible; tested projective fits were unstable, so no "
            "image footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_029cf09b5162": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Westbury map target and the road, escarpment, and White Horse "
            "scene identify one candidate field. The wide source frames are strongly "
            "oblique and the additional controls are compressed, near-collinear, or "
            "affected by terrain parallax; the near-nadir frames contain no persistent "
            "landmarks, so no image footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_70a65215ef96": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Stonehenge publisher target identifies one candidate field and "
            "the wide source aerials show the A303 scene. The road segment lacks unique "
            "distributed intersections in the source frame and the remaining views are "
            "formation-tight; no defensible third affine or fourth projective control "
            "was found, so no image footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_c125d1c37d59": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher map target and the persistent Cerne Abbas Giant, road, "
            "and field pattern identify one candidate field. The surviving source "
            "frames are strongly oblique or tightly cropped and do not expose three "
            "defensible distributed affine controls or four projective controls, so "
            "no image footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_ec30f3c01b4d": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact publisher target and the Winchester Science Centre campus, "
            "road junction, tree block, and surrounding fields identify one candidate "
            "field. Elevated-roof parallax and nearly collinear controls make the "
            "tested full-frame projective fits unstable, so no image footprint is "
            "published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_30c270c0d791": {
        "processing_status": "candidate_field",
        "reason": (
            "The Oakvale source coordinate constrains a candidate field, but the only "
            "surviving 273 by 204 source photograph is a tight ground view without "
            "persistent surrounding landmarks. It is unsuitable for a defensible "
            "image registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_8a68d8a0471b": {
        "processing_status": "unresolved",
        "reason": (
            "The Aloha coordinate is minute-rounded with approximately 1.5 km "
            "uncertainty, while the surviving aerial is tightly cropped around the "
            "formation and exposes no persistent surrounding landmarks. No unique "
            "field or defensible registration can be selected."
        ),
        "review_date": "2026-07-22",
    },
    "cc_db1599385db5": {
        "processing_status": "unresolved",
        "reason": (
            "The Bedford report and map pin constrain the Sandpit Road / Mitchell Road "
            "vicinity, but the linked archive consists of ground photographs and the "
            "reported point leaves multiple adjacent fields plausible. No unique field "
            "or image registration is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_72e3a77239de": {
        "processing_status": "clues_reviewed",
        "reason": (
            "Official North Dakota 2005 NAIP acquired 2005-07-12 confirms the "
            "Northwood Municipal / Vince Field road, runway, drainage, and farmstead "
            "context and narrows the source scene to the airport-adjacent field block. "
            "The surviving aerial controls are clustered along the drainage and canopy; "
            "full-image projective fits are unstable, so no overlay is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_ad68564a4282": {
        "processing_status": "clues_reviewed",
        "reason": (
            "Official California 2005 NAIP and the public report constrain the event to "
            "a pylon-crossed agricultural scene southeast of Fairfield. The only usable "
            "source aerial is a tight oblique frame: its two pylon controls are nearly "
            "collinear and no defensible distributed third or fourth control survives, "
            "so the field match and overlay remain unresolved."
        ),
        "review_date": "2026-07-22",
    },
    "cc_b4d637c767f9": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Waden Hill publisher target and the independently visible "
            "Silbury Hill / A4 scene identify one candidate field. The source is "
            "strongly oblique and terrain-dominated; only the formation anchor and "
            "clustered mound controls survived review. A three-control affine trial "
            "missed its held-out summit check by approximately 88 metres, so no "
            "source-frame footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_079e9ed8bea7": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Patney Bridge publisher target, railway corridor, underbridge, "
            "field edges, and farm structures identify one candidate field. The wide "
            "frames are materially oblique and the tight frames contain formation "
            "geometry without distributed persistent landmarks. Tested full-frame "
            "fits were unstable, so no source-frame footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_c13a98d2fd3f": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Pepperbox Hill publisher target, red-roof shed, angled hedge "
            "corner, adjoining green field, wooded belt, and A36 context identify one "
            "candidate field. Fewer than three defensible affine or four projective "
            "controls survive across the oblique source frames; trial transforms had "
            "implausible footprints, so no source-frame overlay is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_8b6d16796ee3": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Maiden Castle publisher target, the persistent hillfort "
            "ramparts, and the surrounding field pattern identify one candidate "
            "field. The available wide aerial is strongly oblique and the usable "
            "rampart controls are terrain-sensitive and nearly collinear; a tested "
            "three-control affine fit missed the held-out rampart check by about "
            "100 metres, so no source-frame footprint is published."
        ),
        "review_date": "2026-07-22",
    },
}


CSV_FIELDS = [
    "formation_id",
    "assertion_ids",
    "event_date",
    "place",
    "region",
    "country",
    "source_report_urls",
    "source_image_urls",
    "source_image_count",
    "current_location_role",
    "current_latitude",
    "current_longitude",
    "current_coordinate_uncertainty_m",
    "source_coordinate_availability",
    "publisher_map_target_availability",
    "named_geographic_clues",
    "identifiable_persistent_landmarks",
    "source_image_dimensions",
    "display_rights",
    "publication_rights",
    "straight_component_likelihood",
    "priority_score",
    "processing_status",
    "blocker_or_rejection_reason",
    "selected_overlay_id",
    "registration_classification",
    "review_date",
]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def split_values(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def number(value: object) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def overlay_is_proper(overlay: dict) -> bool:
    return overlay.get("registration_status") in {
        "properly_registered",
        "accepted_georegistration",
        "accepted_projective_registration",
    }


def straight_likelihood(formation: dict[str, str]) -> str:
    tiers = {
        formation.get("straight_component_tier", "").lower(),
        formation.get("source_image_straight_tier", "").lower(),
    }
    if "high" in tiers:
        return "high"
    if "medium" in tiers:
        return "medium"
    if formation.get("has_straight_component") == "yes_candidate":
        return "candidate"
    return "unknown"


def build_queue() -> dict:
    formations = [row for row in load_csv(FORMATIONS_PATH) if not row.get("alias_of")]
    image_payload = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
    images_by_formation = image_payload.get("images_by_formation", {})
    overlay_payload = json.loads(OVERLAYS_PATH.read_text(encoding="utf-8"))
    overlays_by_formation: dict[str, list[dict]] = defaultdict(list)
    for overlay in overlay_payload.get("overlays", []):
        overlays_by_formation[overlay.get("formation_id", "")].append(overlay)
    site_candidates: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_csv(SITE_CANDIDATES_PATH):
        site_candidates[row.get("formation_id", "")].append(row)
    archive_payload = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    archive_by_formation = {
        row["formation_id"]: row for row in archive_payload.get("reports", [])
    }

    records: list[dict] = []
    for formation in formations:
        formation_id = formation["formation_id"]
        images = list(images_by_formation.get(formation_id, []))
        archive = archive_by_formation.get(formation_id)
        if not images and not archive:
            continue

        if archive:
            known_urls = {image.get("image_url", "") for image in images}
            for metadata in archive.get("source_image_metadata", []):
                if metadata.get("url") in known_urls:
                    continue
                images.append(
                    {
                        "image_url": metadata.get("url", ""),
                        "source_record_url": archive.get("source_record_url", ""),
                        "source_name": archive_payload.get("source_name", ""),
                        "width": metadata.get("width"),
                        "height": metadata.get("height"),
                        "rights_status": metadata.get("rights_status", ""),
                        "embedding_allowed": False,
                        "pixel_display_policy": "link_only_rights_gated",
                    }
                )

        source_report_urls = unique(
            split_values(formation.get("source_urls", ""))
            + [image.get("source_record_url", "") for image in images]
            + ([archive.get("source_record_url", "")] if archive else [])
        )
        source_image_urls = unique([image.get("image_url", "") for image in images])
        dimensions = unique(
            [
                f"{image.get('width')}x{image.get('height')}"
                for image in images
                if image.get("width") and image.get("height")
            ]
        )
        rights = unique([image.get("rights_status", "") for image in images])
        displayable = any(
            truthy(image.get("embedding_allowed"))
            or image.get("pixel_display_policy")
            in {
                "remote_source_on_explicit_user_action",
                "remote_open_license_on_explicit_user_action",
            }
            for image in images
        )
        openly_licensed = any(
            "commons" in image.get("source_name", "").lower()
            or "open" in image.get("rights_status", "").lower()
            or image.get("license_url")
            for image in images
        )

        has_site = bool(formation.get("site_latitude") and formation.get("site_longitude"))
        latitude = formation.get("site_latitude") if has_site else formation.get("latitude")
        longitude = formation.get("site_longitude") if has_site else formation.get("longitude")
        uncertainty_m = number(formation.get("site_coordinate_uncertainty_m")) if has_site else None
        if uncertainty_m is None:
            uncertainty_km = number(formation.get("coordinate_uncertainty_km"))
            uncertainty_m = uncertainty_km * 1000 if uncertainty_km is not None else None

        candidates = site_candidates.get(formation_id, [])
        methods = " ".join(
            [formation.get("site_coordinate_method", ""), formation.get("geocode_method", "")]
            + [candidate.get("coordinate_method", "") for candidate in candidates]
        ).lower()
        source_coordinate = any(
            token in methods
            for token in ("source", "gps", "google_maps", "publisher", "report_coordinate")
        )
        publisher_map_target = any(
            candidate.get("coordinate_source_url") or "google_maps" in candidate.get("coordinate_method", "")
            for candidate in candidates
        )

        evidence = ARCHIVE_EVIDENCE.get(formation_id, {})
        record_place = archive.get("place", "") if archive else formation.get("place", "")
        record_region = archive.get("region", "") if archive else formation.get("region", "")
        clues = unique(
            [record_place, formation.get("county", ""), record_region]
            + split_values(formation.get("site_search_aliases", ""))
            + list(evidence.get("clues", []))
        )
        landmarks = unique(list(evidence.get("landmarks", [])))
        if formation.get("site_search_aliases") and not landmarks:
            landmarks = split_values(formation.get("site_search_aliases", ""))

        overlays = overlays_by_formation.get(formation_id, [])
        selected_overlay = overlays[0] if overlays else None
        if selected_overlay and overlay_is_proper(selected_overlay):
            processing_status = "properly_registered"
            registration_classification = "properly_registered"
        elif selected_overlay:
            processing_status = "provisional_registration"
            registration_classification = "provisional_registration"
        elif formation_id in BLOCKED_ARCHIVE:
            processing_status = "blocked_source"
            registration_classification = ""
        elif archive:
            processing_status = "source_image_acquired"
            registration_classification = ""
        else:
            processing_status = "queued"
            registration_classification = ""

        production_review = PRODUCTION_REVIEW.get(formation_id, {})
        if production_review and not selected_overlay:
            processing_status = production_review["processing_status"]

        country_code = formation.get("country_code", "")
        site_status = formation.get("site_status", "")
        if archive:
            priority = 6000
        elif country_code == "US" and site_status in {"registered_site", "candidate_field"}:
            priority = 5000
        elif country_code == "US" and formation.get("location_role") == "locality_reference":
            priority = 4000
        elif country_code == "US":
            priority = 3000
        elif site_status in {"registered_site", "candidate_field"} or source_coordinate:
            priority = 2000
        else:
            priority = 1000
        priority += min(len(source_image_urls), 20) * 3
        priority += 90 if site_status == "registered_site" else 60 if site_status == "candidate_field" else 0
        priority += 45 if source_coordinate else 0
        priority += 45 if publisher_map_target else 0
        priority += min(len(landmarks), 8) * 5
        priority += 20 if straight_likelihood(formation) == "high" else 10 if straight_likelihood(formation) == "medium" else 0
        priority -= 500 if formation_id in BLOCKED_ARCHIVE else 0

        record = {
            "formation_id": formation_id,
            "assertion_ids": split_values(formation.get("assertion_ids", "")),
            "event_date": formation.get("date_iso", ""),
            "place": record_place,
            "region": record_region,
            "country": formation.get("country", ""),
            "source_report_urls": source_report_urls,
            "source_image_urls": source_image_urls,
            "source_image_count": len(source_image_urls),
            "current_location_role": formation.get("location_role", ""),
            "current_latitude": number(latitude),
            "current_longitude": number(longitude),
            "current_coordinate_uncertainty_m": uncertainty_m,
            "source_coordinate_availability": "yes" if source_coordinate else "no",
            "publisher_map_target_availability": "yes" if publisher_map_target else "no",
            "named_geographic_clues": clues,
            "identifiable_persistent_landmarks": landmarks,
            "source_image_dimensions": dimensions,
            "display_rights": "source_hosted_on_explicit_user_action" if displayable else "link_only_rights_gated",
            "publication_rights": "at_least_one_open_license" if openly_licensed else "not_cleared_for_redistribution",
            "straight_component_likelihood": straight_likelihood(formation),
            "priority_score": priority,
            "processing_status": processing_status,
            "blocker_or_rejection_reason": production_review.get(
                "reason", BLOCKED_ARCHIVE.get(formation_id, "")
            ),
            "selected_overlay_id": selected_overlay.get("overlay_id", "") if selected_overlay else "",
            "registration_classification": registration_classification,
            "review_date": (
                selected_overlay.get("reviewed_at", "")
                if selected_overlay
                else production_review.get("review_date", "")
                or (archive_payload.get("reviewed_at", "") if archive else "")
            ),
        }
        records.append(record)

    records.sort(key=lambda row: (-row["priority_score"], row["formation_id"]))
    status_counts = Counter(record["processing_status"] for record in records)
    return {
        "schema_version": "crop-circle-atlas/overlay-production-queue/v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "queue_basis": "Unique formation events with one or more source-image records; the 23 reviewed U.S. Crop Circle Archives matches are ranked first.",
        "unique_formation_event_count": len(records),
        "reviewed_us_archive_event_count": len(archive_by_formation),
        "reviewed_us_archive_image_count": sum(
            len(row.get("image_urls", [])) for row in archive_payload.get("reports", [])
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "records": records,
    }


def write_queue(payload: dict) -> None:
    JSON_OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with CSV_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in payload["records"]:
            writer.writerow(
                {
                    field: "; ".join(str(item) for item in record[field])
                    if isinstance(record.get(field), list)
                    else "" if record.get(field) is None
                    else record.get(field, "")
                    for field in CSV_FIELDS
                }
            )


if __name__ == "__main__":
    queue = build_queue()
    write_queue(queue)
    print(
        json.dumps(
            {
                "unique_formation_event_count": queue["unique_formation_event_count"],
                "reviewed_us_archive_event_count": queue["reviewed_us_archive_event_count"],
                "reviewed_us_archive_image_count": queue["reviewed_us_archive_image_count"],
                "status_counts": queue["status_counts"],
            },
            sort_keys=True,
        )
    )
