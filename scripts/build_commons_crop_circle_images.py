"""Build a provenance-first Wikimedia Commons crop-circle image snapshot.

The intake stores links and public metadata only.  Original image bytes are never
downloaded or packaged.  The committed CSV is therefore an index of reusable
source material, not a redistribution of the media.

Examples:
    python scripts/build_commons_crop_circle_images.py --refresh
    python scripts/build_commons_crop_circle_images.py --refresh --retrieved-at 2026-07-21
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import math
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FORMATIONS_PATH = ROOT / "data" / "formations.csv"
IMAGES_PATH = ROOT / "data" / "commons_crop_circle_images.csv"
ASSERTIONS_PATH = ROOT / "data" / "commons_crop_circle_assertions.csv"

API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "CropCircleAtlas/1.0 "
    "(https://github.com/MYTbrain/crop-circle-atlas; provenance-only research intake)"
)
ROOT_CATEGORIES = ("Category:Crop circles",)
MAX_CATEGORY_DEPTH = 4

# These branches contain derived art rather than photographs of formations.
EXCLUDED_CATEGORY_FRAGMENTS = (
    "crop circle icons",
    "eine botschaft von gott",
)

IMAGE_FIELDS = (
    "commons_image_id",
    "commons_page_id",
    "file_title",
    "commons_page_url",
    "original_file_url",
    "mime_type",
    "width_px",
    "height_px",
    "byte_size",
    "sha1",
    "hash_algorithm",
    "commons_revision_timestamp",
    "captured_at",
    "date_precision",
    "date_source",
    "description",
    "place",
    "region",
    "country",
    "country_code",
    "latitude",
    "longitude",
    "coordinate_source",
    "author",
    "license_short_name",
    "license_url",
    "usage_terms",
    "attribution_required",
    "open_license_verified",
    "embedding_allowed",
    "image_kind",
    "overlay_readiness",
    "commons_categories",
    "discovery_categories",
    "retrieved_at",
    "pixel_storage_policy",
)

ASSERTION_FIELDS = (
    "commons_assertion_id",
    "commons_image_id",
    "commons_page_url",
    "date_iso",
    "date_precision",
    "place",
    "region",
    "country",
    "country_code",
    "latitude",
    "longitude",
    "matched_formation_id",
    "match_status",
    "match_method",
    "match_distance_km",
    "candidate_count",
    "overlay_readiness",
    "provenance_note",
)


@dataclass(frozen=True)
class PlaceRule:
    tokens: tuple[str, ...]
    place: str
    region: str
    country: str
    country_code: str


# Rules are intentionally explicit.  They turn only words supplied by Commons
# into normalized place labels; they do not assert a field-level geolocation.
PLACE_RULES = (
    PlaceRule(("diessenhofen",), "Diessenhofen", "Thurgau", "Switzerland", "CH"),
    PlaceRule(("tagermoos", "tägermoos", "steckborn"), "Steckborn / Hörhausen", "Thurgau", "Switzerland", "CH"),
    PlaceRule(("horhausen", "hörhausen"), "Hörhausen", "Thurgau", "Switzerland", "CH"),
    PlaceRule(("dietzenbach",), "Dietzenbach", "Hesse", "Germany", "DE"),
    PlaceRule(("sarraltroff", "saraltroff"), "Sarraltroff", "Moselle", "France", "FR"),
    PlaceRule(("alton barnes",), "Alton Barnes", "Wiltshire", "United Kingdom", "GB"),
    PlaceRule(("alton priors",), "Alton Priors", "Wiltshire", "United Kingdom", "GB"),
    PlaceRule(("barbury",), "Barbury Castle", "Wiltshire", "United Kingdom", "GB"),
    PlaceRule(("west kennett",), "West Kennett", "Wiltshire", "United Kingdom", "GB"),
    PlaceRule(("avebury",), "Avebury", "Wiltshire", "United Kingdom", "GB"),
    PlaceRule(("woodborough hill",), "Woodborough Hill", "Wiltshire", "United Kingdom", "GB"),
    PlaceRule(("lay wood",), "Lay Wood", "Wiltshire", "United Kingdom", "GB"),
    PlaceRule(("chilbolton",), "Chilbolton", "Hampshire", "United Kingdom", "GB"),
    PlaceRule(("chartley manor", "chartley castle"), "Chartley Castle", "Staffordshire", "United Kingdom", "GB"),
    PlaceRule(("steep down",), "Steep Down", "West Sussex", "United Kingdom", "GB"),
    PlaceRule(("ancona",), "Ancona", "Marche", "Italy", "IT"),
    PlaceRule(("berbah", "sleman"), "Sleman", "Yogyakarta", "Indonesia", "ID"),
    PlaceRule(("pistoletto",), "Assago", "Lombardy", "Italy", "IT"),
)

COUNTRY_TOKEN_RULES = (
    (("switzerland", "swiss", "thurgau"), "Switzerland", "CH"),
    (("united kingdom", "england", "wiltshire", "hampshire", "staffordshire"), "United Kingdom", "GB"),
    (("germany", "deutschland", "hesse"), "Germany", "DE"),
    (("france", "moselle", "lorraine"), "France", "FR"),
    (("italy", "italia", "marche"), "Italy", "IT"),
    (("netherlands", "nizozemsko", "nederland"), "Netherlands", "NL"),
    (("indonesia", "yogyakarta"), "Indonesia", "ID"),
    (("finland", "suomi"), "Finland", "FI"),
    (("czech", "česko"), "Czechia", "CZ"),
    (("japan", "hachioji", "八王子"), "Japan", "JP"),
    (("russia", "russian", "росси"), "Russia", "RU"),
    (("united states", "usa", "california", "ohio"), "United States", "US"),
)

# Used only if Commons supplies coordinates but no usable country words.  The
# boxes are conservative and evaluated from smallest/specific to largest.
COUNTRY_BOXES = (
    ("CH", "Switzerland", 45.75, 47.90, 5.90, 10.60),
    ("NL", "Netherlands", 50.70, 53.70, 3.20, 7.30),
    ("GB", "United Kingdom", 49.70, 60.90, -8.80, 2.00),
    ("DE", "Germany", 47.20, 55.10, 5.50, 15.60),
    ("IT", "Italy", 35.40, 47.10, 6.00, 19.00),
    ("FR", "France", 41.00, 51.30, -5.60, 9.70),
    ("CZ", "Czechia", 48.50, 51.10, 12.00, 18.90),
    ("FI", "Finland", 59.70, 70.20, 19.00, 32.00),
    ("ID", "Indonesia", -11.00, 6.20, 95.00, 141.10),
    ("JP", "Japan", 24.00, 46.00, 122.00, 146.00),
)

OPEN_LICENSE_MARKERS = (
    "cc by",
    "cc-by",
    "cc0",
    "public domain",
    "gfdl",
    "free art license",
)


class CommonsApi:
    def __init__(self, *, retries: int = 3, timeout: int = 45) -> None:
        self.retries = retries
        self.timeout = timeout

    def get(self, **params: str | int) -> dict:
        query = {
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
            **params,
        }
        url = f"{API_URL}?{urlencode(query)}"
        request = Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        for attempt in range(self.retries):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except URLError as error:
                # Some managed Windows Python distributions do not inherit the
                # OS trust store correctly. curl.exe/SChannel is a verified-TLS
                # fallback; certificate checking is never disabled.
                if "CERTIFICATE_VERIFY_FAILED" in str(error):
                    try:
                        completed = subprocess.run(
                            ["curl.exe", "--fail", "--silent", "--show-error", "--location", "--user-agent", USER_AGENT, url],
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=self.timeout,
                        )
                    except (FileNotFoundError, subprocess.CalledProcessError):
                        # Final Windows-only fallback uses Invoke-WebRequest and
                        # the OS certificate store. EncodedCommand prevents URL
                        # metacharacters from being interpreted by a shell.
                        powershell = (
                            "$ProgressPreference='SilentlyContinue'; "
                            "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
                            f"$value=(Invoke-WebRequest -UseBasicParsing -Uri '{url}' "
                            f"-Headers @{{'User-Agent'='{USER_AGENT}'}}).Content; "
                            "[Console]::Out.Write($value)"
                        )
                        encoded = base64.b64encode(powershell.encode("utf-16le")).decode("ascii")
                        completed = subprocess.run(
                            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            check=True,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            timeout=self.timeout,
                        )
                    return json.loads(completed.stdout)
                if attempt + 1 >= self.retries:
                    raise
                time.sleep(1.5 * (attempt + 1))
            except (HTTPError, TimeoutError, json.JSONDecodeError):
                if attempt + 1 >= self.retries:
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("unreachable")


def clean_html(value: str) -> str:
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def normalize(value: str) -> str:
    value = html.unescape(value or "").casefold()
    value = value.replace("’", "'")
    return re.sub(r"[^a-z0-9à-ž一-龯]+", " ", value).strip()


def stable_id(prefix: str, value: str, length: int = 16) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]}"


def metadata_value(metadata: dict, key: str) -> str:
    item = metadata.get(key, {})
    return clean_html(str(item.get("value", ""))) if isinstance(item, dict) else ""


def discover_files(api: CommonsApi, max_depth: int = MAX_CATEGORY_DEPTH) -> dict[str, set[str]]:
    discovered: dict[str, set[str]] = {}
    queue = deque((category, 0) for category in ROOT_CATEGORIES)
    visited: set[str] = set()
    while queue:
        category, depth = queue.popleft()
        if category in visited:
            continue
        visited.add(category)
        if any(fragment in normalize(category) for fragment in EXCLUDED_CATEGORY_FRAGMENTS):
            continue
        continuation = ""
        while True:
            params: dict[str, str | int] = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category,
                "cmtype": "file|subcat",
                "cmlimit": "max",
                "cmsort": "sortkey",
                "cmdir": "asc",
            }
            if continuation:
                params["cmcontinue"] = continuation
            payload = api.get(**params)
            for member in payload.get("query", {}).get("categorymembers", []):
                title = member.get("title", "")
                if member.get("ns") == 6:
                    discovered.setdefault(title, set()).add(category)
                elif member.get("ns") == 14 and depth < max_depth:
                    queue.append((title, depth + 1))
            continuation = payload.get("continue", {}).get("cmcontinue", "")
            if not continuation:
                break
    return discovered


def batched(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch_file_pages(api: CommonsApi, titles: Iterable[str]) -> list[dict]:
    pages: list[dict] = []
    for batch in batched(sorted(set(titles)), 25):
        payload = api.get(
            action="query",
            prop="imageinfo|coordinates|categories",
            titles="|".join(batch),
            iiprop="url|size|sha1|timestamp|mime|extmetadata",
            colimit="max",
            cllimit="max",
        )
        pages.extend(payload.get("query", {}).get("pages", []))
    return sorted(pages, key=lambda page: page.get("title", ""))


def parse_capture_date(metadata: dict, title: str) -> tuple[str, str, str]:
    value = metadata_value(metadata, "DateTimeOriginal")
    approximate_title_year = re.search(r"\bc\.?\s*(19\d{2}|20\d{2})\b", title, flags=re.I)
    if approximate_title_year:
        return approximate_title_year.group(1), "year", "commons_file_title_approximate_year"
    candidates = ((value, "commons_extmetadata_DateTimeOriginal"), (title, "commons_file_title"))
    patterns = (
        (r"(?<!\d)(\d{4})[-:/.](\d{2})[-:/.](\d{2})(?!\d)", "ymd"),
        (r"(?<!\d)(\d{2})[-:/.](\d{2})[-:/.](\d{4})(?!\d)", "dmy"),
        (r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", "year"),
    )
    for candidate, source in candidates:
        for pattern, kind in patterns:
            match = re.search(pattern, candidate)
            if not match:
                continue
            try:
                if kind == "ymd":
                    year, month, day = map(int, match.groups())
                    return f"{year:04d}-{month:02d}-{day:02d}", "day", source
                if kind == "dmy":
                    day, month, year = map(int, match.groups())
                    return f"{year:04d}-{month:02d}-{day:02d}", "day", source
                return match.group(1), "year", source
            except ValueError:
                continue
    return "", "unknown", ""


def classify_place(text: str, latitude: float | None, longitude: float | None) -> tuple[str, str, str, str]:
    normalized = normalize(text)
    for rule in PLACE_RULES:
        if any((needle := normalize(token)) and needle in normalized for token in rule.tokens):
            return rule.place, rule.region, rule.country, rule.country_code
    for tokens, country, code in COUNTRY_TOKEN_RULES:
        if any((needle := normalize(token)) and needle in normalized for token in tokens):
            return "", "", country, code
    if latitude is not None and longitude is not None:
        for code, country, south, north, west, east in COUNTRY_BOXES:
            if south <= latitude <= north and west <= longitude <= east:
                return "", "", country, code
    return "", "", "", ""


def classify_image(title: str, description: str, mime_type: str) -> str:
    text = normalize(f"{title} {description}")
    if mime_type.startswith("video/"):
        return "video"
    if any(token in text for token in (
        "diagram", "coloring book", "svg", "sketch", "cartoon", "drawing",
        "explained", "microscopy", "illustration", "pamphlet", "barnstar",
        "map of", "made in paint", "journal of", "signs crop circle", "icon",
    )):
        return "diagram_or_illustration"
    if any(token in text for token in ("aerial", "aerial view", "aerial shot", "luftbild")):
        return "aerial_photograph"
    if mime_type.startswith("image/") and any(token in text for token in ("inside", "detail", "dentro", "cerchio")):
        return "ground_photograph"
    if mime_type.startswith("image/"):
        return "photograph_or_unspecified"
    return "other_media"


def license_is_open(short_name: str, usage_terms: str, license_url: str) -> bool:
    value = normalize(f"{short_name} {usage_terms} {license_url}")
    return any(normalize(marker) in value for marker in OPEN_LICENSE_MARKERS)


def overlay_readiness(image_kind: str, latitude: str, longitude: str, place: str) -> str:
    if image_kind == "aerial_photograph" and latitude and longitude:
        return "geotagged_aerial_landmark_candidate"
    if image_kind in {"aerial_photograph", "photograph_or_unspecified"} and latitude and longitude:
        return "geotagged_scene_candidate"
    if image_kind == "aerial_photograph" and place:
        return "place_known_landmark_geolocation_required"
    if image_kind in {"aerial_photograph", "photograph_or_unspecified", "ground_photograph"}:
        return "source_photo_only"
    return "not_an_overlay_source"


def page_to_row(page: dict, discovery_categories: set[str], retrieved_at: str) -> dict[str, str]:
    info = (page.get("imageinfo") or [{}])[0]
    metadata = info.get("extmetadata") or {}
    title = page.get("title", "")
    description = metadata_value(metadata, "ImageDescription")
    coordinates = page.get("coordinates") or []
    latitude: float | None = None
    longitude: float | None = None
    coordinate_source = ""
    if coordinates:
        latitude = float(coordinates[0]["lat"])
        longitude = float(coordinates[0]["lon"])
        coordinate_source = "commons_page_coordinates"
    elif metadata_value(metadata, "GPSLatitude") and metadata_value(metadata, "GPSLongitude"):
        latitude = float(metadata_value(metadata, "GPSLatitude"))
        longitude = float(metadata_value(metadata, "GPSLongitude"))
        coordinate_source = "commons_extmetadata_gps"

    commons_categories = sorted(
        item.get("title", "").removeprefix("Category:")
        for item in page.get("categories", [])
        if item.get("title")
    )
    context = " | ".join((title, description, " | ".join(commons_categories)))
    place, region, country, country_code = classify_place(context, latitude, longitude)
    captured_at, date_precision, date_source = parse_capture_date(metadata, title)
    mime_type = info.get("mime", "")
    image_kind = classify_image(title, context, mime_type)
    license_short_name = metadata_value(metadata, "LicenseShortName")
    usage_terms = metadata_value(metadata, "UsageTerms")
    license_url = metadata_value(metadata, "LicenseUrl")
    image_id = stable_id("commons_img", str(page.get("pageid", title)))
    latitude_text = f"{latitude:.8f}".rstrip("0").rstrip(".") if latitude is not None else ""
    longitude_text = f"{longitude:.8f}".rstrip("0").rstrip(".") if longitude is not None else ""
    return {
        "commons_image_id": image_id,
        "commons_page_id": str(page.get("pageid", "")),
        "file_title": title,
        "commons_page_url": info.get("descriptionurl", ""),
        "original_file_url": info.get("url", ""),
        "mime_type": mime_type,
        "width_px": str(info.get("width", "")),
        "height_px": str(info.get("height", "")),
        "byte_size": str(info.get("size", "")),
        "sha1": info.get("sha1", ""),
        "hash_algorithm": "SHA-1 (Wikimedia original-file revision)",
        "commons_revision_timestamp": info.get("timestamp", ""),
        "captured_at": captured_at,
        "date_precision": date_precision,
        "date_source": date_source,
        "description": description,
        "place": place,
        "region": region,
        "country": country,
        "country_code": country_code,
        "latitude": latitude_text,
        "longitude": longitude_text,
        "coordinate_source": coordinate_source,
        "author": metadata_value(metadata, "Artist"),
        "license_short_name": license_short_name,
        "license_url": license_url,
        "usage_terms": usage_terms,
        "attribution_required": metadata_value(metadata, "AttributionRequired").lower(),
        "open_license_verified": str(license_is_open(license_short_name, usage_terms, license_url)).lower(),
        "embedding_allowed": str(license_is_open(license_short_name, usage_terms, license_url)).lower(),
        "image_kind": image_kind,
        "overlay_readiness": overlay_readiness(image_kind, latitude_text, longitude_text, place),
        "commons_categories": ";".join(commons_categories),
        "discovery_categories": ";".join(sorted(discovery_categories)),
        "retrieved_at": retrieved_at,
        "pixel_storage_policy": "remote_link_only_no_pixels_packaged",
    }


def load_formations(path: Path = FORMATIONS_PATH) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def date_year(value: str) -> str:
    match = re.match(r"^(\d{4})", value or "")
    return match.group(1) if match else ""


def comparable_place(value: str) -> set[str]:
    normalized = normalize(value)
    aliases = {
        "steckborn horhausen": {"steckborn", "horhausen"},
        "horhausen": {"horhausen", "steckborn"},
        "barbury castle": {"barbury", "barbury castle", "barbury hill"},
        "chartley castle": {"chartley castle", "chartley manor farm"},
    }
    return aliases.get(normalized, {normalized}) if normalized else set()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def formation_coordinates(formation: dict[str, str]) -> tuple[float, float] | None:
    options = (
        (formation.get("accepted_site_latitude", ""), formation.get("accepted_site_longitude", "")),
        (formation.get("site_latitude", ""), formation.get("site_longitude", "")),
        (formation.get("latitude", ""), formation.get("longitude", "")),
    )
    for latitude, longitude in options:
        try:
            return float(latitude), float(longitude)
        except (TypeError, ValueError):
            continue
    return None


def match_formations(row: dict[str, str], formations: list[dict[str, str]]) -> list[dict[str, str]]:
    row_year = date_year(row["captured_at"])
    row_places = comparable_place(row["place"])
    candidates: list[tuple[int, float | None, dict[str, str], str]] = []
    row_coordinates = None
    if row["latitude"] and row["longitude"]:
        row_coordinates = float(row["latitude"]), float(row["longitude"])

    for formation in formations:
        if row["country_code"] and formation.get("country_code") and row["country_code"] != formation.get("country_code"):
            continue
        formation_year = date_year(formation.get("date_iso", ""))
        if row_year and formation_year and row_year != formation_year:
            continue
        formation_place = normalize(formation.get("place", ""))
        place_match = any(
            place == formation_place or place in formation_place or formation_place in place
            for place in row_places
            if place and formation_place
        )
        distance = None
        coords = formation_coordinates(formation)
        if row_coordinates and coords:
            distance = haversine_km(*row_coordinates, *coords)

        exact_date = bool(row["captured_at"] and row["captured_at"] == formation.get("date_iso"))
        if place_match and exact_date:
            candidates.append((0, distance, formation, "exact_place_and_date"))
        elif place_match and row_year:
            candidates.append((1, distance, formation, "place_and_year_candidate"))
        elif exact_date and distance is not None and distance <= 10:
            candidates.append((2, distance, formation, "coordinate_and_date_candidate"))

    if not candidates:
        return []
    best_rank = min(item[0] for item in candidates)
    retained = [item for item in candidates if item[0] == best_rank]
    retained.sort(key=lambda item: ((item[1] if item[1] is not None else 1e12), item[2]["formation_id"]))
    status = retained[0][3] if len(retained) == 1 else f"ambiguous_{retained[0][3]}"
    output = []
    for _, distance, formation, method in retained:
        output.append(
            {
                "matched_formation_id": formation["formation_id"],
                "match_status": status,
                "match_method": method,
                "match_distance_km": f"{distance:.3f}" if distance is not None else "",
                "candidate_count": str(len(retained)),
            }
        )
    return output


def build_assertions(rows: list[dict[str, str]], formations: list[dict[str, str]]) -> list[dict[str, str]]:
    assertions: list[dict[str, str]] = []
    for row in rows:
        matches = match_formations(row, formations)
        if not matches:
            matches = [{
                "matched_formation_id": "",
                "match_status": "no_defensible_existing_formation_match",
                "match_method": "",
                "match_distance_km": "",
                "candidate_count": "0",
            }]
        for match in matches:
            identity = f"{row['commons_image_id']}|{match['matched_formation_id']}|{match['match_status']}"
            assertions.append(
                {
                    "commons_assertion_id": stable_id("commons_assertion", identity),
                    "commons_image_id": row["commons_image_id"],
                    "commons_page_url": row["commons_page_url"],
                    "date_iso": row["captured_at"],
                    "date_precision": row["date_precision"],
                    "place": row["place"],
                    "region": row["region"],
                    "country": row["country"],
                    "country_code": row["country_code"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    **match,
                    "overlay_readiness": row["overlay_readiness"],
                    "provenance_note": (
                        "Wikimedia Commons API metadata; remote original linked only; "
                        "formation match is conservative and does not itself georegister the image."
                    ),
                }
            )
    return sorted(assertions, key=lambda item: (item["commons_image_id"], item["matched_formation_id"]))


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def refresh(*, retrieved_at: str, max_depth: int = MAX_CATEGORY_DEPTH) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    api = CommonsApi()
    discovered = discover_files(api, max_depth=max_depth)
    pages = fetch_file_pages(api, discovered)
    rows = [page_to_row(page, discovered.get(page.get("title", ""), set()), retrieved_at) for page in pages]
    # This bounded collection is intentionally strict: explicit free license,
    # known non-US country, and actual photographic media only.
    rows = [
        row for row in rows
        if row["open_license_verified"] == "true"
        and row["country_code"] not in {"", "US"}
        and row["image_kind"] in {"aerial_photograph", "ground_photograph", "photograph_or_unspecified"}
    ]
    rows.sort(key=lambda item: (item["country_code"], item["captured_at"], item["file_title"]))
    assertions = build_assertions(rows, load_formations())
    write_csv(IMAGES_PATH, IMAGE_FIELDS, rows)
    write_csv(ASSERTIONS_PATH, ASSERTION_FIELDS, assertions)
    return rows, assertions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Query Commons and rewrite the committed CSV snapshot.")
    parser.add_argument(
        "--retrieved-at",
        default=datetime.now(UTC).date().isoformat(),
        help="ISO retrieval date recorded in every row (use an explicit date for reproducible snapshots).",
    )
    parser.add_argument("--max-category-depth", type=int, default=MAX_CATEGORY_DEPTH)
    args = parser.parse_args()
    if not args.refresh:
        parser.error("--refresh is required; this script never downloads image pixels")
    rows, assertions = refresh(retrieved_at=args.retrieved_at, max_depth=args.max_category_depth)
    matched_images = len({item["commons_image_id"] for item in assertions if item["matched_formation_id"]})
    ready = sum(row["overlay_readiness"] == "geotagged_aerial_landmark_candidate" for row in rows)
    print(
        f"Wrote {len(rows)} openly licensed non-US Commons images, "
        f"{matched_images} image-to-formation matches, and {ready} geotagged aerial candidates."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
