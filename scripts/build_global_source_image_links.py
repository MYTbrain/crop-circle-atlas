from __future__ import annotations

"""Build a worldwide, link-only source-image inventory.

The existing ICCRA image table is intentionally US-focused.  This builder
normalizes the image references already exposed by Crop Circle Center (CCC),
Crop Circle Connector, and the Dutch Crop Circle Archive (DCCA).  It can also
read public detail HTML to enumerate the high-yield report galleries.

Only HTML is requested.  Image URLs are never fetched, cached, copied, or
embedded.  Consequently ``image_sha256`` remains empty unless a future,
separately authorized workflow supplies a verified pixel hash.
"""

import argparse
import csv
import hashlib
import math
import re
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from lxml import html


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ASSERTIONS = ROOT / "data" / "source_assertions.csv"
EXPANSION_ASSERTIONS = ROOT / "data" / "source_expansion_assertions.csv"
EXPANSION_MANIFEST = ROOT / "data" / "source_expansion_crawl_manifest.csv"
SOURCE_SNAPSHOTS = ROOT / "data" / "source_snapshots.csv"
FORMATIONS = ROOT / "data" / "formations.csv"
OUTPUT = ROOT / "data" / "global_source_image_links.csv"
SITE_OUTPUT = ROOT / "data" / "global_source_site_candidates.csv"

USER_AGENT = "CropCircleAtlas/1.0 (+link-only source-image metadata inventory)"
PLACEMENT_STATUS = "source_link_only_not_georegistered"
IMAGE_FETCH_POLICY = "not_requested_metadata_only_no_pixel_download"
IMAGE_SHA256_STATUS = "not_computed_no_pixel_download"

SOURCE_NAMES = {
    "ccc": "Crop Circle Center",
    "connector": "Crop Circle Connector",
    "dcca": "Dutch Crop Circle Archive",
}

RIGHTS_STATUS = {
    "ccc": "link_only_contributor_images_not_redistributed",
    "connector": "metadata_only_contributor_image_rights_retained",
    "dcca": "metadata_only_attribution_and_publication_permission_required",
}

IMAGE_SUFFIX_RE = re.compile(r"\.(?:jpe?g|png|gif|webp)(?:$|\?)", re.IGNORECASE)
NON_CONTENT_IMAGE_TOKENS = (
    "archive.jpg",
    "back.jpg",
    "background.jpg",
    "banner",
    "btn_",
    "counter",
    "deadspace",
    "facebook",
    "fpcount",
    "logo",
    "meals-page",
    "newspaper",
    "paypal",
    "shop2",
    "spacer",
    "tiquett",
    "21stcen",
)

FIELDNAMES = [
    "image_link_id",
    "source_id",
    "source_name",
    "assertion_id",
    "formation_id",
    "date_iso",
    "place",
    "region",
    "country",
    "country_code",
    "source_record_url",
    "source_page_urls",
    "source_page_sha256s",
    "source_page_http_statuses",
    "source_page_fetch_policies",
    "image_url",
    "reference_roles",
    "image_kind",
    "alt_text",
    "title_text",
    "width",
    "height",
    "dimension_basis",
    "image_http_status",
    "image_sha256",
    "image_sha256_status",
    "image_fetch_policy",
    "local_cache_path",
    "rights_status",
    "embedding_allowed",
    "pixel_bytes_packaged",
    "placement_status",
]

SITE_FIELDNAMES = [
    "site_candidate_id",
    "source_id",
    "source_name",
    "assertion_id",
    "formation_id",
    "date_iso",
    "place",
    "region",
    "country",
    "country_code",
    "latitude",
    "longitude",
    "coordinate_method",
    "coordinate_reference_text",
    "coordinate_uncertainty_m",
    "coordinate_source_url",
    "source_record_url",
    "source_page_sha256",
    "source_page_http_status",
    "source_page_fetch_policy",
    "linked_image_count",
    "rights_status",
    "embedding_allowed",
    "review_status",
]

OS_GRID_RE = re.compile(r"\b([HNOST][A-HJ-Z])\s*(\d{4}|\d{6}|\d{8}|\d{10})\b", re.IGNORECASE)
OS_GRID_CONTEXT_RE = re.compile(
    r"(?:\bmap\b|\bgrid\b|\bos\b)\s*(?:ref(?:erence)?\.?|reference\b)\s*[:#-]?\s*$",
    re.IGNORECASE,
)
GB_LATITUDE_RANGE = (49.5, 61.0)
GB_LONGITUDE_RANGE = (-8.5, 2.5)
LOCALITY_SANITY_FLOOR_KM = 75.0

# Coarse country envelopes are a rejection screen, not evidence that a point
# is inside a country.  Several countries need multiple envelopes for islands
# or antimeridian-spanning territory.  Every country code currently present in
# the worldwide source pipeline is represented so unknown geography fails
# closed instead of silently becoming a map marker.
COUNTRY_BOUNDS: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "AR": ((-56.0, -21.0, -74.5, -52.5),),
    "AT": ((46.2, 49.2, 9.3, 17.3),),
    "AU": ((-44.5, -9.0, 112.0, 154.5),),
    "BE": ((49.4, 51.7, 2.4, 6.5),),
    "BG": ((41.0, 44.4, 22.2, 28.8),),
    "BR": ((-34.5, 5.6, -74.5, -34.0),),
    "CA": ((41.0, 84.0, -142.0, -52.0),),
    "CH": ((45.7, 48.0, 5.8, 10.7),),
    "CN": ((18.0, 54.0, 73.0, 135.5),),
    "CZ": ((48.4, 51.2, 11.9, 19.0),),
    "DE": ((47.1, 55.2, 5.5, 15.6),),
    "DK": ((54.4, 57.9, 7.5, 15.3),),
    "ES": ((35.5, 44.2, -10.0, 4.6), (27.4, 29.6, -18.5, -13.0)),
    "FI": ((59.4, 70.3, 19.0, 32.0),),
    "FR": (
        (41.0, 51.6, -5.6, 10.0),
        (2.0, 6.0, -55.0, -51.0),
        (14.0, 19.0, -63.5, -60.5),
        (-22.0, -10.0, 43.0, 56.0),
        (-23.0, -12.0, 162.0, 169.0),
        (-28.0, -7.0, -153.0, -134.0),
    ),
    "GB": ((49.5, 61.0, -8.5, 2.5),),
    "HR": ((42.2, 46.7, 13.3, 19.5),),
    "HU": ((45.7, 48.7, 16.0, 23.0),),
    "IE": ((51.2, 55.6, -11.0, -5.0),),
    "IL": ((29.0, 33.5, 34.2, 35.9),),
    "IT": ((35.3, 47.2, 6.2, 18.8),),
    "JP": ((24.0, 46.0, 122.0, 146.5),),
    "MX": ((14.0, 33.5, -119.0, -86.0),),
    "NL": ((50.7, 53.8, 3.0, 7.4), (11.8, 18.5, -69.5, -62.5)),
    "NO": ((57.7, 71.5, 4.0, 31.5), (74.0, 81.0, 9.0, 35.0)),
    "NZ": ((-48.0, -33.0, 165.0, 179.9), (-45.0, -42.0, -177.0, -175.0)),
    "PL": ((48.9, 55.0, 14.0, 24.3),),
    "PR": ((17.5, 18.7, -67.5, -65.0),),
    "PT": ((36.7, 42.3, -9.7, -6.0), (30.0, 40.0, -32.0, -16.0)),
    "RO": ((43.4, 48.4, 20.0, 30.0),),
    "RS": ((42.2, 46.3, 18.7, 23.1),),
    "RU": ((41.0, 82.0, 19.0, 180.0), (50.0, 72.0, -180.0, -168.0)),
    "SE": ((55.1, 69.2, 10.4, 24.6),),
    "SI": ((45.3, 47.0, 13.3, 16.7),),
    "SK": ((47.7, 49.7, 16.8, 22.7),),
    "UA": ((44.0, 53.0, 21.0, 41.0),),
    "US": (
        (24.0, 50.0, -125.0, -66.0),
        (51.0, 72.0, -171.0, -129.0),
        (18.0, 23.0, -161.0, -154.0),
    ),
    "ZA": ((-35.2, -21.7, 16.0, 33.2),),
}


@dataclass(frozen=True)
class PageResult:
    url: str
    http_status: int
    body: bytes
    sha256: str
    fetch_policy: str
    error: str = ""


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def normalize_url(url: str) -> str:
    parts = urllib.parse.urlsplit((url or "").strip())
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, "")
    )


def absolute_url(page_url: str, value: str) -> str:
    return normalize_url(urllib.parse.urljoin(page_url, (value or "").strip()))


def record_directory(record_url: str) -> str:
    normalized = normalize_url(record_url)
    return normalized.rsplit("/", 1)[0] + "/"


def is_image_url(url: str) -> bool:
    return bool(url and IMAGE_SUFFIX_RE.search(url))


def is_report_image(record_url: str, image_url: str) -> bool:
    """Keep report-local imagery and reject navigation/advertising assets."""

    if not is_image_url(image_url):
        return False
    if not image_url.startswith(record_directory(record_url)):
        return False
    lowered = urllib.parse.urlsplit(image_url).path.lower()
    return not any(token in lowered for token in NON_CONTENT_IMAGE_TOKENS)


def is_index_content_image(image_url: str) -> bool:
    if not is_image_url(image_url):
        return False
    lowered = urllib.parse.urlsplit(image_url).path.lower()
    if any(token in lowered for token in NON_CONTENT_IMAGE_TOKENS):
        return False
    return "crop-circle-tour" not in lowered


def declared_dimension(value: str | None) -> int | None:
    match = re.search(r"\d+", value or "")
    if not match:
        return None
    parsed = int(match.group(0))
    return parsed if parsed > 0 else None


def infer_image_kind(image_url: str, alt_text: str = "", title_text: str = "") -> str:
    evidence = " ".join((image_url, alt_text, title_text)).lower()
    if any(token in evidence for token in ("diagram", "map", "plan", "sketch", "draw")):
        return "diagram_or_map"
    if any(token in evidence for token in ("aerial", "air0", "air1", "air2", "drone", "overhead", "birdview", "dji_", "/dji")):
        return "aerial_or_overhead"
    if "usselo-86" in evidence:
        return "placeholder_or_reference"
    return "photograph_or_unspecified"


def os_grid_ref_to_easting_northing(reference: str) -> tuple[float, float, int]:
    """Convert a British National Grid reference to metres in EPSG:27700.

    The returned uncertainty is the grid-square resolution implied by the
    number of digits.  References point to the south-west corner, so half a
    grid cell is added before conversion to represent its centre.
    """

    compact = re.sub(r"\s+", "", reference or "").upper()
    match = OS_GRID_RE.fullmatch(compact)
    if not match:
        raise ValueError(f"invalid British National Grid reference: {reference}")
    letters, digits = match.groups()
    first = ord(letters[0]) - ord("A")
    second = ord(letters[1]) - ord("A")
    if first > 7:
        first -= 1
    if second > 7:
        second -= 1
    e100km = ((first - 2) % 5) * 5 + (second % 5)
    n100km = 19 - (first // 5) * 5 - (second // 5)
    if not (0 <= e100km <= 6 and 0 <= n100km <= 12):
        raise ValueError(f"British National Grid reference is outside the grid: {reference}")
    half = len(digits) // 2
    resolution = 10 ** (5 - half)
    easting = e100km * 100000 + int(digits[:half]) * resolution + resolution / 2
    northing = n100km * 100000 + int(digits[half:]) * resolution + resolution / 2
    return float(easting), float(northing), int(resolution)


def is_within_gb(latitude: float, longitude: float) -> bool:
    return (
        GB_LATITUDE_RANGE[0] <= latitude <= GB_LATITUDE_RANGE[1]
        and GB_LONGITUDE_RANGE[0] <= longitude <= GB_LONGITUDE_RANGE[1]
    )


def normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", (value or "").strip().lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def is_within_country(country_code: str, latitude: float, longitude: float) -> bool:
    """Conservatively reject points outside the claimed country's envelopes."""

    bounds = COUNTRY_BOUNDS.get((country_code or "").upper())
    if not bounds:
        return False
    return any(
        minimum_latitude <= latitude <= maximum_latitude
        and minimum_longitude <= longitude <= maximum_longitude
        for minimum_latitude, maximum_latitude, minimum_longitude, maximum_longitude in bounds
    )


def haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    latitude_a_rad, latitude_b_rad = map(math.radians, (latitude_a, latitude_b))
    delta_latitude = math.radians(latitude_b - latitude_a)
    delta_longitude = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(latitude_a_rad)
        * math.cos(latitude_b_rad)
        * math.sin(delta_longitude / 2) ** 2
    )
    return 6371.0088 * 2 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(max(0.0, 1.0 - haversine)),
    )


def geodetic_to_cartesian(
    latitude: float,
    longitude: float,
    height: float,
    semi_major: float,
    semi_minor: float,
) -> tuple[float, float, float]:
    eccentricity2 = 1 - (semi_minor * semi_minor) / (semi_major * semi_major)
    nu = semi_major / math.sqrt(1 - eccentricity2 * math.sin(latitude) ** 2)
    x = (nu + height) * math.cos(latitude) * math.cos(longitude)
    y = (nu + height) * math.cos(latitude) * math.sin(longitude)
    z = ((1 - eccentricity2) * nu + height) * math.sin(latitude)
    return x, y, z


def cartesian_to_geodetic(
    x: float,
    y: float,
    z: float,
    semi_major: float,
    semi_minor: float,
) -> tuple[float, float]:
    eccentricity2 = 1 - (semi_minor * semi_minor) / (semi_major * semi_major)
    p = math.sqrt(x * x + y * y)
    latitude = math.atan2(z, p * (1 - eccentricity2))
    for _ in range(12):
        nu = semi_major / math.sqrt(1 - eccentricity2 * math.sin(latitude) ** 2)
        updated = math.atan2(z + eccentricity2 * nu * math.sin(latitude), p)
        if abs(updated - latitude) < 1e-12:
            latitude = updated
            break
        latitude = updated
    return latitude, math.atan2(y, x)


def bng_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """Convert EPSG:27700 easting/northing to WGS84 using OSTN fallback math."""

    airy_a = 6377563.396
    airy_b = 6356256.909
    f0 = 0.9996012717
    latitude0 = math.radians(49)
    longitude0 = math.radians(-2)
    northing0 = -100000.0
    easting0 = 400000.0
    n = (airy_a - airy_b) / (airy_a + airy_b)

    latitude = latitude0
    meridional = 0.0
    while northing - northing0 - meridional >= 0.00001:
        latitude = (northing - northing0 - meridional) / (airy_a * f0) + latitude
        ma = (1 + n + 5 / 4 * n**2 + 5 / 4 * n**3) * (latitude - latitude0)
        mb = (3 * n + 3 * n**2 + 21 / 8 * n**3) * math.sin(latitude - latitude0) * math.cos(latitude + latitude0)
        mc = (15 / 8 * n**2 + 15 / 8 * n**3) * math.sin(2 * (latitude - latitude0)) * math.cos(2 * (latitude + latitude0))
        md = 35 / 24 * n**3 * math.sin(3 * (latitude - latitude0)) * math.cos(3 * (latitude + latitude0))
        meridional = airy_b * f0 * (ma - mb + mc - md)

    eccentricity2 = 1 - (airy_b * airy_b) / (airy_a * airy_a)
    sin_latitude = math.sin(latitude)
    cos_latitude = math.cos(latitude)
    tan_latitude = math.tan(latitude)
    nu = airy_a * f0 / math.sqrt(1 - eccentricity2 * sin_latitude**2)
    rho = airy_a * f0 * (1 - eccentricity2) / (1 - eccentricity2 * sin_latitude**2) ** 1.5
    eta2 = nu / rho - 1
    delta_easting = easting - easting0

    vii = tan_latitude / (2 * rho * nu)
    viii = tan_latitude / (24 * rho * nu**3) * (5 + 3 * tan_latitude**2 + eta2 - 9 * tan_latitude**2 * eta2)
    ix = tan_latitude / (720 * rho * nu**5) * (61 + 90 * tan_latitude**2 + 45 * tan_latitude**4)
    x = 1 / (cos_latitude * nu)
    xi = 1 / (cos_latitude * 6 * nu**3) * (nu / rho + 2 * tan_latitude**2)
    xii = 1 / (cos_latitude * 120 * nu**5) * (5 + 28 * tan_latitude**2 + 24 * tan_latitude**4)
    xiia = 1 / (cos_latitude * 5040 * nu**7) * (61 + 662 * tan_latitude**2 + 1320 * tan_latitude**4 + 720 * tan_latitude**6)

    osgb_latitude = latitude - vii * delta_easting**2 + viii * delta_easting**4 - ix * delta_easting**6
    osgb_longitude = longitude0 + x * delta_easting - xi * delta_easting**3 + xii * delta_easting**5 - xiia * delta_easting**7

    cartesian = geodetic_to_cartesian(osgb_latitude, osgb_longitude, 0.0, airy_a, airy_b)
    tx, ty, tz = 446.448, -125.157, 542.060
    rx = math.radians(0.1502 / 3600)
    ry = math.radians(0.2470 / 3600)
    rz = math.radians(0.8421 / 3600)
    scale = -20.4894e-6
    x1, y1, z1 = cartesian
    x2 = tx + (1 + scale) * x1 - rz * y1 + ry * z1
    y2 = ty + rz * x1 + (1 + scale) * y1 - rx * z1
    z2 = tz - ry * x1 + rx * y1 + (1 + scale) * z1
    latitude_wgs84, longitude_wgs84 = cartesian_to_geodetic(
        x2,
        y2,
        z2,
        6378137.0,
        6356752.3141,
    )
    return math.degrees(latitude_wgs84), math.degrees(longitude_wgs84)


def parse_dms_pair(value: str) -> tuple[float, float] | None:
    decoded = urllib.parse.unquote_plus(value or "")
    matches = re.findall(
        r"(\d{1,3})[^0-9A-Z]+(\d{1,2})[^0-9A-Z]+([0-9.]+)[^A-Z0-9]*([NSEW])",
        decoded.upper(),
    )
    if len(matches) < 2:
        return None
    values: dict[str, float] = {}
    for degrees, minutes, seconds, direction in matches[:2]:
        decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
        if direction in {"S", "W"}:
            decimal *= -1
        values[direction] = decimal
    latitude = values.get("N", values.get("S"))
    longitude = values.get("E", values.get("W"))
    if latitude is None or longitude is None:
        return None
    return latitude, longitude


def coordinate_from_map_url(url: str) -> dict[str, object] | None:
    decoded = urllib.parse.unquote_plus(url or "")
    lowered = decoded.lower()
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parsed.query)

    if "streetmap.co.uk" in lowered:
        try:
            easting = float(query.get("x", [""])[0])
            northing = float(query.get("y", [""])[0])
        except ValueError:
            easting = northing = 0.0
        reference = query.get("sv", [""])[0]
        if easting and northing:
            latitude, longitude = bng_to_wgs84(easting, northing)
            return {
                "latitude": latitude,
                "longitude": longitude,
                "method": "streetmap_bng_pointer_to_wgs84",
                "reference": f"EPSG:27700 E={easting:.0f} N={northing:.0f}" + (f"; {reference}" if reference else ""),
                "uncertainty_m": 25,
            }
        if reference:
            match = OS_GRID_RE.search(reference.upper())
            if match:
                compact = "".join(match.groups())
                easting, northing, resolution = os_grid_ref_to_easting_northing(compact)
                latitude, longitude = bng_to_wgs84(easting, northing)
                return {
                    "latitude": latitude,
                    "longitude": longitude,
                    "method": "streetmap_os_grid_reference_to_wgs84",
                    "reference": compact,
                    "uncertainty_m": max(25, resolution),
                }

    if not any(token in lowered for token in ("google.", "goo.gl/maps", "maps.google")):
        return None

    dms = parse_dms_pair(decoded)
    if dms:
        return {
            "latitude": dms[0],
            "longitude": dms[1],
            "method": "google_maps_dms_target",
            "reference": "DMS target embedded in map URL",
            "uncertainty_m": 25,
        }

    target = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", decoded)
    if target:
        return {
            "latitude": float(target.group(1)),
            "longitude": float(target.group(2)),
            "method": "google_maps_place_target",
            "reference": "Google Maps place target",
            "uncertainty_m": 25,
        }

    for key in ("q", "ll"):
        value = query.get(key, [""])[0]
        pair = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", value)
        if pair:
            return {
                "latitude": float(pair.group(1)),
                "longitude": float(pair.group(2)),
                "method": "google_maps_query_coordinate",
                "reference": f"Google Maps {key}= coordinate",
                "uncertainty_m": 25,
            }

    at_coordinate = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),([0-9.]+)([mz])", decoded)
    if at_coordinate:
        view_value = float(at_coordinate.group(3))
        view_unit = at_coordinate.group(4)
        if view_unit == "m":
            uncertainty = max(25, min(500, int(view_value / 4)))
            method = "google_maps_satellite_view_center"
        else:
            uncertainty = 100 if view_value >= 17 else 1000 if view_value >= 14 else 5000
            method = "google_maps_view_center_review_needed"
        return {
            "latitude": float(at_coordinate.group(1)),
            "longitude": float(at_coordinate.group(2)),
            "method": method,
            "reference": f"Google Maps view center at {view_value:g}{view_unit}",
            "uncertainty_m": uncertainty,
        }
    return None


def stable_link_id(source_id: str, assertion_id: str, image_url: str) -> str:
    material = "|".join((source_id, assertion_id, normalize_url(image_url)))
    return "gimg_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def formation_index() -> dict[str, str]:
    result: dict[str, str] = {}
    for row in load_csv(FORMATIONS):
        formation_id = row.get("alias_of", "") or row["formation_id"]
        for assertion_id in (row.get("assertion_ids", "") or "").split(";"):
            if assertion_id.strip():
                result[assertion_id.strip()] = formation_id
    # A source-expansion parser default can be corrected before formations are
    # next rebuilt.  Link that assertion to the independently matched baseline
    # formation immediately so images and map clues never remain attached to a
    # known-wrong duplicate entity during the rebuild interval.
    for row in load_csv(EXPANSION_ASSERTIONS):
        if row.get("canonical_match_status") != "baseline_geography_correction":
            continue
        matched_id = row.get("matched_baseline_assertion_id", "").strip()
        if matched_id in result:
            result[row["assertion_id"]] = result[matched_id]
    return result


def formation_locality_index() -> dict[str, dict[str, object]]:
    """Load independently geocoded locality references for distance screening."""

    result: dict[str, dict[str, object]] = {}
    for row in load_csv(FORMATIONS):
        formation_id = row.get("alias_of", "") or row.get("formation_id", "")
        latitude_text = row.get("locality_latitude", "")
        longitude_text = row.get("locality_longitude", "")
        if not formation_id or not latitude_text or not longitude_text:
            continue
        try:
            latitude = float(latitude_text)
            longitude = float(longitude_text)
            uncertainty_km = float(row.get("locality_coordinate_uncertainty_km") or 0)
        except (TypeError, ValueError):
            continue
        candidate = {
            "latitude": latitude,
            "longitude": longitude,
            "country_code": row.get("country_code", "").upper(),
            "admin1": row.get("locality_admin1", ""),
            "uncertainty_km": uncertainty_km,
        }
        existing = result.get(formation_id)
        if existing is None or uncertainty_km < float(existing["uncertainty_km"]):
            result[formation_id] = candidate
    return result


def candidate_is_geographically_plausible(
    assertion: dict[str, str],
    candidate: dict[str, object],
    formation_id: str = "",
    locality_by_formation: dict[str, dict[str, object]] | None = None,
) -> bool:
    """Apply country and independently corroborated locality sanity checks.

    The country envelope is mandatory for every coordinate method.  Locality
    distance is enforced only when the formation has an independent locality
    reference whose administrative region agrees with the source assertion;
    this avoids treating an ambiguous same-named town centroid as authority.
    """

    try:
        latitude = float(candidate["latitude"])
        longitude = float(candidate["longitude"])
    except (KeyError, TypeError, ValueError):
        return False
    country_code = assertion.get("country_code", "").upper()
    if not is_within_country(country_code, latitude, longitude):
        return False

    locality = (locality_by_formation or {}).get(formation_id)
    if not locality:
        return True
    if locality.get("country_code") and locality.get("country_code") != country_code:
        return False
    source_region = normalized_text(assertion.get("region", ""))
    locality_region = normalized_text(str(locality.get("admin1", "")))
    if not source_region or source_region != locality_region:
        return True
    distance_limit = max(
        LOCALITY_SANITY_FLOOR_KM,
        3 * float(locality.get("uncertainty_km") or 0),
    )
    return haversine_km(
        latitude,
        longitude,
        float(locality["latitude"]),
        float(locality["longitude"]),
    ) <= distance_limit


def source_rows() -> dict[str, list[dict[str, str]]]:
    ccc = [
        row
        for row in load_csv(SOURCE_ASSERTIONS)
        if row.get("source_name") == SOURCE_NAMES["ccc"] and row.get("source_record_url")
    ]
    expansion = load_csv(EXPANSION_ASSERTIONS)
    return {
        "ccc": ccc,
        "connector": [row for row in expansion if row.get("expansion_source_id") == "connector"],
        "dcca": [row for row in expansion if row.get("expansion_source_id") == "dcca"],
    }


def snapshot_index() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in load_csv(SOURCE_SNAPSHOTS):
        if row.get("url"):
            result[normalize_url(row["url"])] = row
    return result


def expansion_manifest_index() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in load_csv(EXPANSION_MANIFEST):
        if row.get("url") and row.get("cache_path"):
            result[normalize_url(row["url"])] = row
    return result


def read_manifest_page(row: dict[str, str]) -> tuple[bytes, str]:
    path = ROOT / row["cache_path"]
    return path.read_bytes(), row.get("sha256", "")


def ancestor_cell(element):
    current = element
    while current is not None:
        # Connector event cards are table cells.  Stopping at an inner DIV can
        # miss the thumbnail immediately before the linked event title.
        if str(current.tag).lower() == "td":
            return current
        current = current.getparent()
    return element


def connector_index_image(
    document,
    index_url: str,
    record_url: str,
) -> tuple[str, object | None]:
    normalized_record = normalize_url(record_url)
    for anchor in document.xpath("//a[@href]"):
        if absolute_url(index_url, anchor.get("href")).casefold() != normalized_record.casefold():
            continue
        container = ancestor_cell(anchor)
        candidates = container.xpath(".//img[@src]")
        candidates = [
            image
            for image in candidates
            if is_index_content_image(absolute_url(index_url, image.get("src")))
        ]
        if candidates:
            image = candidates[0]
            return absolute_url(index_url, image.get("src")), image
    return "", None


def dcca_index_image(
    document,
    index_url: str,
    record_url: str,
) -> tuple[str, object | None]:
    normalized_record = normalize_url(record_url)
    for anchor in document.xpath("//a[@href]"):
        if absolute_url(index_url, anchor.get("href")) != normalized_record:
            continue
        following = anchor.xpath("following::img[@src][1]")
        if following:
            image = following[0]
            return absolute_url(index_url, image.get("src")), image
    return "", None


def parse_detail_images(record_url: str, body: bytes) -> list[dict[str, object]]:
    if not body:
        return []
    try:
        document = html.fromstring(body, base_url=record_url)
    except (ValueError, TypeError):
        return []
    images: dict[str, dict[str, object]] = {}
    for element in document.xpath("//img[@src]"):
        image_url = absolute_url(record_url, element.get("src"))
        if not is_report_image(record_url, image_url):
            continue
        alt_text = (element.get("alt") or "").strip()
        title_text = (element.get("title") or "").strip()
        width = declared_dimension(element.get("width"))
        height = declared_dimension(element.get("height"))
        candidate = {
            "image_url": image_url,
            "alt_text": alt_text,
            "title_text": title_text,
            "width": width,
            "height": height,
            "image_kind": infer_image_kind(image_url, alt_text, title_text),
        }
        previous = images.get(image_url)
        previous_area = (previous.get("width") or 0) * (previous.get("height") or 0) if previous else -1
        candidate_area = (width or 0) * (height or 0)
        if previous is None or candidate_area > previous_area:
            images[image_url] = candidate
    return [images[url] for url in sorted(images)]


def fetch_html(
    url: str,
    timeout: float,
    allow_ccc_invalid_chain: bool,
) -> PageResult:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    host = urllib.parse.urlsplit(url).netloc.lower()
    fetch_policy = "live_html_tls_verified"
    context = ssl.create_default_context()
    invalid_chain_hosts = {
        "www.cropcirclecenter.com",
        "cropcircleconnector.com",
        "www.dcca.nl",
    }
    if host in invalid_chain_hosts and allow_ccc_invalid_chain:
        # These legacy sites currently present chains that fail strict Basic
        # Constraints validation in the bundled Python trust store.  This
        # exception is opt-in, recorded in every derived row, and applies only
        # to public HTML metadata.  Image pixels are never requested.
        context = ssl._create_unverified_context()
        fetch_policy = "live_html_source_invalid_chain_bypass_no_pixels"
    last_error = ""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
                body = response.read()
                status = int(getattr(response, "status", 200))
            return PageResult(
                url=url,
                http_status=status,
                body=body if status == 200 else b"",
                sha256=hashlib.sha256(body).hexdigest() if status == 200 else "",
                fetch_policy=fetch_policy,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = f"{type(error).__name__}: {error}"
            if attempt == 0:
                time.sleep(0.15)
    return PageResult(url, 0, b"", "", fetch_policy, last_error)


def fetch_detail_pages(
    urls: Iterable[str],
    max_workers: int,
    timeout: float,
    allow_ccc_invalid_chain: bool,
) -> dict[str, PageResult]:
    normalized_urls = sorted({normalize_url(url) for url in urls if url})

    def fetch(url: str) -> PageResult:
        return fetch_html(url, timeout, allow_ccc_invalid_chain)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(fetch, normalized_urls))
    return {result.url: result for result in results}


def empty_entry(
    source_id: str,
    assertion: dict[str, str],
    formation_by_assertion: dict[str, str],
    image_url: str,
) -> dict[str, object]:
    assertion_id = assertion["assertion_id"]
    return {
        "image_link_id": stable_link_id(source_id, assertion_id, image_url),
        "source_id": source_id,
        "source_name": SOURCE_NAMES[source_id],
        "assertion_id": assertion_id,
        "formation_id": formation_by_assertion.get(assertion_id, ""),
        "date_iso": assertion.get("date_iso", ""),
        "place": assertion.get("place", ""),
        "region": assertion.get("region", ""),
        "country": assertion.get("country", ""),
        "country_code": assertion.get("country_code", ""),
        "source_record_url": normalize_url(assertion.get("source_record_url", "")),
        "_source_page_urls": set(),
        "_source_page_sha256s": set(),
        "_source_page_http_statuses": set(),
        "_source_page_fetch_policies": set(),
        "image_url": normalize_url(image_url),
        "_reference_roles": set(),
        "image_kind": "photograph_or_unspecified",
        "alt_text": "",
        "title_text": "",
        "width": None,
        "height": None,
        "dimension_basis": "unknown",
        "image_http_status": "",
        "image_sha256": "",
        "image_sha256_status": IMAGE_SHA256_STATUS,
        "image_fetch_policy": IMAGE_FETCH_POLICY,
        "local_cache_path": "",
        "rights_status": RIGHTS_STATUS[source_id],
        "embedding_allowed": "false",
        "pixel_bytes_packaged": "false",
        "placement_status": PLACEMENT_STATUS,
    }


def merge_reference(
    entries: dict[tuple[str, str], dict[str, object]],
    source_id: str,
    assertion: dict[str, str],
    formation_by_assertion: dict[str, str],
    image_url: str,
    role: str,
    source_page_url: str,
    source_page_sha256: str,
    source_page_http_status: str | int,
    source_page_fetch_policy: str,
    element=None,
    parsed_image: dict[str, object] | None = None,
) -> None:
    image_url = normalize_url(image_url)
    if not image_url:
        return
    key = (assertion["assertion_id"], image_url)
    entry = entries.setdefault(
        key,
        empty_entry(source_id, assertion, formation_by_assertion, image_url),
    )
    entry["_reference_roles"].add(role)
    if source_page_url:
        entry["_source_page_urls"].add(normalize_url(source_page_url))
    if source_page_sha256:
        entry["_source_page_sha256s"].add(source_page_sha256)
    if str(source_page_http_status):
        entry["_source_page_http_statuses"].add(str(source_page_http_status))
    if source_page_fetch_policy:
        entry["_source_page_fetch_policies"].add(source_page_fetch_policy)

    alt_text = ""
    title_text = ""
    width = None
    height = None
    if element is not None:
        alt_text = (element.get("alt") or "").strip()
        title_text = (element.get("title") or "").strip()
        width = declared_dimension(element.get("width"))
        height = declared_dimension(element.get("height"))
    if parsed_image:
        alt_text = str(parsed_image.get("alt_text") or alt_text)
        title_text = str(parsed_image.get("title_text") or title_text)
        width = parsed_image.get("width") or width
        height = parsed_image.get("height") or height
    if len(alt_text) > len(str(entry["alt_text"])):
        entry["alt_text"] = alt_text
    if len(title_text) > len(str(entry["title_text"])):
        entry["title_text"] = title_text
    previous_area = (entry["width"] or 0) * (entry["height"] or 0)
    candidate_area = (width or 0) * (height or 0)
    if candidate_area > previous_area:
        entry["width"] = width
        entry["height"] = height
        entry["dimension_basis"] = "html_declared"
    entry["image_kind"] = infer_image_kind(
        image_url,
        str(entry["alt_text"]),
        str(entry["title_text"]),
    )


def add_ccc_index_references(
    entries: dict[tuple[str, str], dict[str, object]],
    assertions: list[dict[str, str]],
    formation_by_assertion: dict[str, str],
    snapshots: dict[str, dict[str, str]],
) -> None:
    for assertion in assertions:
        image_url = assertion.get("thumbnail_url", "")
        if not image_url:
            continue
        source_page = assertion.get("source_url", "")
        snapshot = snapshots.get(normalize_url(source_page), {})
        merge_reference(
            entries,
            "ccc",
            assertion,
            formation_by_assertion,
            image_url,
            "index_thumbnail",
            source_page,
            snapshot.get("sha256", ""),
            snapshot.get("http_status", ""),
            "cached_index_manifest",
        )


def add_expansion_index_references(
    entries: dict[tuple[str, str], dict[str, object]],
    source_id: str,
    assertions: list[dict[str, str]],
    formation_by_assertion: dict[str, str],
    manifest: dict[str, dict[str, str]],
) -> None:
    if source_id == "connector":
        # A handful of Connector entries are repeated or moved between month
        # indexes, so the parser's source_page can differ from the page that
        # currently carries the thumbnail.  Reconcile over every cached event
        # index by the stable detail URL.
        by_record: dict[str, tuple[str, object, dict[str, str]]] = {}
        for manifest_row in sorted(manifest.values(), key=lambda row: row.get("url", "")):
            if (
                manifest_row.get("source_id") != "connector"
                or manifest_row.get("fetch_kind") != "season_event_index"
                or manifest_row.get("http_status") != "200"
            ):
                continue
            source_page = normalize_url(manifest_row["url"])
            body, _ = read_manifest_page(manifest_row)
            try:
                document = html.fromstring(body, base_url=source_page)
            except (ValueError, TypeError):
                continue
            for anchor in document.xpath("//a[@href]"):
                record_url = absolute_url(source_page, anchor.get("href"))
                if not record_url.lower().endswith((".html", ".htm")):
                    continue
                image_url, element = connector_index_image(document, source_page, record_url)
                if image_url and element is not None:
                    by_record.setdefault(record_url.casefold(), (image_url, element, manifest_row))
        for assertion in assertions:
            found = by_record.get(normalize_url(assertion["source_record_url"]).casefold())
            if not found:
                continue
            image_url, element, manifest_row = found
            source_page = manifest_row["url"]
            merge_reference(
                entries,
                source_id,
                assertion,
                formation_by_assertion,
                image_url,
                "index_thumbnail_or_diagram",
                source_page,
                manifest_row.get("sha256", ""),
                manifest_row.get("http_status", ""),
                "cached_index_manifest",
                element=element,
            )
        return

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for assertion in assertions:
        grouped[normalize_url(assertion.get("source_page", ""))].append(assertion)
    for source_page in sorted(grouped):
        manifest_row = manifest.get(source_page)
        if not manifest_row:
            continue
        body, page_sha = read_manifest_page(manifest_row)
        try:
            document = html.fromstring(body, base_url=source_page)
        except (ValueError, TypeError):
            continue
        for assertion in grouped[source_page]:
            record_url = assertion["source_record_url"]
            if source_id == "connector":
                image_url, element = connector_index_image(document, source_page, record_url)
            else:
                image_url, element = dcca_index_image(document, source_page, record_url)
            if not image_url:
                continue
            merge_reference(
                entries,
                source_id,
                assertion,
                formation_by_assertion,
                image_url,
                "index_thumbnail_or_diagram",
                source_page,
                page_sha,
                manifest_row.get("http_status", ""),
                "cached_index_manifest",
                element=element,
            )


def add_detail_references(
    entries: dict[tuple[str, str], dict[str, object]],
    source_id: str,
    assertions: list[dict[str, str]],
    formation_by_assertion: dict[str, str],
    detail_pages: dict[str, PageResult],
) -> None:
    for assertion in assertions:
        record_url = normalize_url(assertion["source_record_url"])
        page = detail_pages.get(record_url)
        if not page or page.http_status != 200:
            continue
        for parsed_image in parse_detail_images(record_url, page.body):
            merge_reference(
                entries,
                source_id,
                assertion,
                formation_by_assertion,
                str(parsed_image["image_url"]),
                "detail_report_image",
                record_url,
                page.sha256,
                page.http_status,
                page.fetch_policy,
                parsed_image=parsed_image,
            )


def finalize_entries(entries: dict[tuple[str, str], dict[str, object]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in entries.values():
        row = dict(entry)
        row["source_page_urls"] = "; ".join(sorted(row.pop("_source_page_urls")))
        row["source_page_sha256s"] = "; ".join(sorted(row.pop("_source_page_sha256s")))
        row["source_page_http_statuses"] = "; ".join(
            sorted(row.pop("_source_page_http_statuses"))
        )
        row["source_page_fetch_policies"] = "; ".join(
            sorted(row.pop("_source_page_fetch_policies"))
        )
        row["reference_roles"] = "; ".join(sorted(row.pop("_reference_roles")))
        row["width"] = str(row["width"] or "")
        row["height"] = str(row["height"] or "")
        rows.append({field: str(row.get(field, "")) for field in FIELDNAMES})
    rows.sort(
        key=lambda row: (
            row["source_id"],
            row["country_code"],
            row["date_iso"],
            row["assertion_id"],
            row["image_url"],
        )
    )
    return rows


def stable_site_candidate_id(assertion_id: str, latitude: float, longitude: float) -> str:
    material = f"{assertion_id}|{latitude:.8f}|{longitude:.8f}"
    return "gsite_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def page_coordinate_candidates(
    record_url: str,
    body: bytes,
    country_code: str = "",
) -> list[dict[str, object]]:
    if not body:
        return []
    try:
        document = html.fromstring(body, base_url=record_url)
    except (ValueError, TypeError):
        return []
    candidates: list[dict[str, object]] = []
    for anchor in document.xpath("//a[@href]"):
        map_url = absolute_url(record_url, anchor.get("href"))
        candidate = coordinate_from_map_url(map_url)
        if candidate:
            method = str(candidate.get("method", "")).lower()
            if ("bng" in method or "os_grid" in method) and country_code.upper() != "GB":
                continue
            candidates.append({**candidate, "source_url": map_url})

    page_text = " ".join(document.text_content().split())
    text_grid_matches = OS_GRID_RE.finditer(page_text) if country_code.upper() == "GB" else ()
    for match in text_grid_matches:
        # Bare country/year and filename tokens such as TV2010, HU2020, and
        # NL2018 resemble low-precision grid references.  Prose references
        # are accepted only when the source labels them as a map/grid/OS ref.
        context = page_text[max(0, match.start() - 80) : match.start()]
        if not OS_GRID_CONTEXT_RE.search(context):
            continue
        reference = "".join(match.groups()).upper()
        try:
            easting, northing, resolution = os_grid_ref_to_easting_northing(reference)
            latitude, longitude = bng_to_wgs84(easting, northing)
        except ValueError:
            continue
        candidates.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "method": "reported_os_grid_reference_to_wgs84",
                "reference": reference,
                "uncertainty_m": max(25, resolution),
                "source_url": record_url,
            }
        )

    deduplicated: list[dict[str, object]] = []
    for candidate in candidates:
        latitude = float(candidate["latitude"])
        longitude = float(candidate["longitude"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        if country_code and not is_within_country(country_code, latitude, longitude):
            continue
        if any(
            abs(latitude - float(existing["latitude"])) < 0.00001
            and abs(longitude - float(existing["longitude"])) < 0.00001
            for existing in deduplicated
        ):
            continue
        deduplicated.append(candidate)
    return deduplicated


def build_site_rows(
    detail_pages: dict[str, PageResult],
    image_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not detail_pages:
        return []
    assertions_by_source = source_rows()
    formation_by_assertion = formation_index()
    locality_by_formation = formation_locality_index()
    image_counts: dict[str, int] = defaultdict(int)
    for row in image_rows:
        image_counts[row["assertion_id"]] += 1

    rows: list[dict[str, str]] = []
    for source_id, assertions in assertions_by_source.items():
        for assertion in assertions:
            record_url = normalize_url(assertion["source_record_url"])
            page = detail_pages.get(record_url)
            if not page or page.http_status != 200:
                continue
            candidates = page_coordinate_candidates(
                record_url,
                page.body,
                assertion.get("country_code", ""),
            )
            if not candidates:
                continue
            country_code = assertion.get("country_code", "").upper()
            formation_id = formation_by_assertion.get(assertion["assertion_id"], "")
            defensible_candidates: list[dict[str, object]] = []
            for candidate in candidates:
                method = str(candidate.get("method", "")).lower()
                candidate_latitude = float(candidate["latitude"])
                candidate_longitude = float(candidate["longitude"])
                if not candidate_is_geographically_plausible(
                    assertion,
                    candidate,
                    formation_id,
                    locality_by_formation,
                ):
                    continue
                if "bng" in method or "os_grid" in method:
                    if country_code != "GB" or not is_within_gb(
                        candidate_latitude,
                        candidate_longitude,
                    ):
                        continue
                defensible_candidates.append(candidate)
            candidates = defensible_candidates
            if not candidates:
                continue
            # The report's explicit map pointer normally precedes contextual
            # map links.  Choose the most precise clue, preserving page order
            # as the tie-breaker.  This remains a review queue, not acceptance.
            indexed = list(enumerate(candidates))
            _, best = min(indexed, key=lambda item: (int(item[1]["uncertainty_m"]), item[0]))
            uncertainty = int(best["uncertainty_m"])
            latitude = float(best["latitude"])
            longitude = float(best["longitude"])
            row = {
                "site_candidate_id": stable_site_candidate_id(assertion["assertion_id"], latitude, longitude),
                "source_id": source_id,
                "source_name": SOURCE_NAMES[source_id],
                "assertion_id": assertion["assertion_id"],
                "formation_id": formation_id,
                "date_iso": assertion.get("date_iso", ""),
                "place": assertion.get("place", ""),
                "region": assertion.get("region", ""),
                "country": assertion.get("country", ""),
                "country_code": assertion.get("country_code", ""),
                "latitude": f"{latitude:.8f}",
                "longitude": f"{longitude:.8f}",
                "coordinate_method": str(best["method"]),
                "coordinate_reference_text": str(best["reference"]),
                "coordinate_uncertainty_m": str(uncertainty),
                "coordinate_source_url": str(best["source_url"]),
                "source_record_url": record_url,
                "source_page_sha256": page.sha256,
                "source_page_http_status": str(page.http_status),
                "source_page_fetch_policy": page.fetch_policy,
                "linked_image_count": str(image_counts.get(assertion["assertion_id"], 0)),
                "rights_status": RIGHTS_STATUS[source_id],
                "embedding_allowed": "false",
                "review_status": (
                    "source_exact_coordinate_clue_not_landmark_validated"
                    if uncertainty <= 100
                    else "source_map_view_center_not_landmark_validated"
                ),
            }
            rows.append({field: row.get(field, "") for field in SITE_FIELDNAMES})
    rows.sort(
        key=lambda row: (
            row["country_code"],
            row["date_iso"],
            row["assertion_id"],
        )
    )
    return rows


def build_rows(
    live_details: bool = False,
    max_workers: int = 12,
    timeout: float = 20.0,
    allow_ccc_invalid_chain: bool = False,
) -> tuple[list[dict[str, str]], dict[str, PageResult]]:
    assertions_by_source = source_rows()
    formation_by_assertion = formation_index()
    entries: dict[tuple[str, str], dict[str, object]] = {}

    add_ccc_index_references(
        entries,
        assertions_by_source["ccc"],
        formation_by_assertion,
        snapshot_index(),
    )
    manifest = expansion_manifest_index()
    add_expansion_index_references(
        entries,
        "connector",
        assertions_by_source["connector"],
        formation_by_assertion,
        manifest,
    )
    add_expansion_index_references(
        entries,
        "dcca",
        assertions_by_source["dcca"],
        formation_by_assertion,
        manifest,
    )

    detail_pages: dict[str, PageResult] = {}
    if live_details:
        detail_pages = fetch_detail_pages(
            (
                assertion["source_record_url"]
                for assertions in assertions_by_source.values()
                for assertion in assertions
            ),
            max_workers=max_workers,
            timeout=timeout,
            allow_ccc_invalid_chain=allow_ccc_invalid_chain,
        )
        for source_id, assertions in assertions_by_source.items():
            add_detail_references(
                entries,
                source_id,
                assertions,
                formation_by_assertion,
                detail_pages,
            )

    return finalize_entries(entries), detail_pages


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_site_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SITE_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(
    rows: list[dict[str, str]],
    detail_pages: dict[str, PageResult],
    site_rows: list[dict[str, str]],
) -> str:
    source_counts = {
        source_id: sum(row["source_id"] == source_id for row in rows)
        for source_id in SOURCE_NAMES
    }
    assertion_counts = {
        source_id: len({row["assertion_id"] for row in rows if row["source_id"] == source_id})
        for source_id in SOURCE_NAMES
    }
    country_count = len({row["country_code"] for row in rows if row["country_code"]})
    dimension_count = sum(bool(row["width"] and row["height"]) for row in rows)
    detail_success = sum(page.http_status == 200 for page in detail_pages.values())
    detail_failed = sum(page.http_status != 200 for page in detail_pages.values())
    return (
        f"rows={len(rows)} unique_images={len({row['image_url'] for row in rows})} "
        f"assertions={len({row['assertion_id'] for row in rows})} countries={country_count} "
        f"with_declared_dimensions={dimension_count} "
        f"ccc={source_counts['ccc']}/{assertion_counts['ccc']} "
        f"connector={source_counts['connector']}/{assertion_counts['connector']} "
        f"dcca={source_counts['dcca']}/{assertion_counts['dcca']} "
        f"detail_pages_ok={detail_success} detail_pages_failed={detail_failed} "
        f"site_candidates={len(site_rows)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-details",
        action="store_true",
        help="Fetch public detail HTML and enumerate report-local image links; pixels are never requested.",
    )
    parser.add_argument(
        "--allow-ccc-invalid-chain",
        action="store_true",
        help="Backward-compatible alias for --allow-source-invalid-chain.",
    )
    parser.add_argument(
        "--allow-source-invalid-chain",
        action="store_true",
        help="Allow metadata-only HTML fetches from the three legacy sources despite invalid certificate chains.",
    )
    parser.add_argument("--max-workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--site-output", type=Path, default=SITE_OUTPUT)
    args = parser.parse_args()
    if args.max_workers < 1 or args.max_workers > 32:
        parser.error("--max-workers must be between 1 and 32")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    rows, detail_pages = build_rows(
        live_details=args.live_details,
        max_workers=args.max_workers,
        timeout=args.timeout,
        allow_ccc_invalid_chain=(args.allow_ccc_invalid_chain or args.allow_source_invalid_chain),
    )
    site_rows = build_site_rows(detail_pages, rows)
    write_rows(args.output, rows)
    write_site_rows(args.site_output, site_rows)
    print(summarize(rows, detail_pages, site_rows))
    print(f"output={args.output}")
    print(f"site_output={args.site_output}")


if __name__ == "__main__":
    main()
