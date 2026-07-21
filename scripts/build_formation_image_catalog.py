from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMATIONS_PATH = ROOT / "data" / "formations.csv"
IMAGES_PATH = ROOT / "data" / "iccra_image_links.csv"
OVERLAYS_PATH = ROOT / "web" / "data" / "registered_overlays.json"
INDEX_PATH = ROOT / "web" / "data" / "formation_index.json"
OUTPUT_PATH = ROOT / "web" / "data" / "formation_images.json"


def split_ids(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(";") if item.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def public_image_entry(image: dict[str, str], assertion_id: str, overlay: dict | None = None) -> dict:
    entry = {
        "image_link_id": image.get("image_link_id", ""),
        "assertion_id": assertion_id,
        "source_page_url": image.get("source_page_url", ""),
        "image_url": image.get("image_url", ""),
        "image_kind": image.get("image_kind", "photograph_or_unspecified"),
        "alt_text": image.get("alt_text", ""),
        "title_text": image.get("title_text", ""),
        "width": int(image["width"]) if image.get("width", "").isdigit() else None,
        "height": int(image["height"]) if image.get("height", "").isdigit() else None,
        "sha256": image.get("sha256", ""),
        "rights_status": image.get("public_redistribution_status", "not_cleared"),
        "placement_status": "mapped_overlay" if overlay else "source_link_only_not_georegistered",
    }
    if overlay:
        entry["overlay_id"] = overlay.get("overlay_id", "")
        entry["registration_status"] = overlay.get("registration_status", "")
    return entry


def build_catalog() -> dict:
    formations = load_csv(FORMATIONS_PATH)
    images = load_csv(IMAGES_PATH)
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

    overlays_by_url = {
        item["source_image_url"]: item
        for item in overlays.get("overlays", [])
        if item.get("source_image_url")
    }
    image_rows_by_url = {image.get("image_url", ""): image for image in images if image.get("image_url")}
    images_by_formation: dict[str, dict[str, dict]] = defaultdict(dict)
    for image in images:
        if image.get("http_status") != "200" or image.get("is_iccra_hosted", "").lower() != "true":
            continue
        matched_assertions = [
            assertion_id for assertion_id in split_ids(image.get("assertion_ids", ""))
            if assertion_id in assertion_to_formation
        ]
        for assertion_id in matched_assertions:
            formation_id = assertion_to_formation[assertion_id]
            image_url = image.get("image_url", "")
            if not image_url:
                continue
            overlay = overlays_by_url.get(image_url)
            if overlay and overlay.get("formation_id") != formation_id:
                overlay = None
            entry = public_image_entry(image, assertion_id, overlay)
            images_by_formation[formation_id][image_url] = entry

    # Report-document images can lack assertion_ids in the crawl edge. A reviewed overlay
    # supplies the missing formation/assertion relationship without packaging the pixels.
    for overlay in overlays.get("overlays", []):
        image_url = overlay.get("source_image_url", "")
        image = image_rows_by_url.get(image_url)
        formation_id = overlay.get("formation_id", "")
        if not image or not formation_id:
            continue
        images_by_formation[formation_id][image_url] = public_image_entry(
            image,
            overlay.get("assertion_id", ""),
            overlay,
        )

    normalized = {
        formation_id: sorted(entries.values(), key=lambda item: (item["image_kind"], item["image_url"]))
        for formation_id, entries in sorted(images_by_formation.items())
    }
    formation_image_link_count = sum(len(entries) for entries in normalized.values())
    unique_image_urls = {
        entry["image_url"] for entries in normalized.values() for entry in entries
    }
    us_unique_image_urls = {
        entry["image_url"]
        for formation_id, entries in normalized.items()
        if country_by_formation.get(formation_id) == "US"
        for entry in entries
    }
    mapped_catalog_image_count = sum(
        entry["placement_status"] == "mapped_overlay"
        for entries in normalized.values()
        for entry in entries
    )
    return {
        "metadata": {
            "schema_version": "crop-circle-atlas/formation-images/v1",
            "generated_at": index_payload.get("metadata", {}).get("generated_at", ""),
            "unique_image_count": len(unique_image_urls),
            "formation_image_link_count": formation_image_link_count,
            "formation_count": len(normalized),
            "us_unique_image_count": len(us_unique_image_urls),
            "mapped_catalog_image_count": mapped_catalog_image_count,
            "overlay_placement_count": len(overlays.get("overlays", [])),
            "rights_notice": (
                "Source pixels are not packaged by the atlas. Images load from ICCRA only after an explicit "
                "user action. A source link is not a georegistration or publication-rights grant."
            ),
        },
        "images_by_formation": normalized,
    }


def main() -> None:
    payload = build_catalog()
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    metadata = payload["metadata"]
    print(
        f"unique_images={metadata['unique_image_count']} links={metadata['formation_image_link_count']} "
        f"formations={metadata['formation_count']} us_unique_images={metadata['us_unique_image_count']} "
        f"mapped_catalog_images={metadata['mapped_catalog_image_count']} "
        f"overlay_placements={metadata['overlay_placement_count']} "
        f"output={OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
