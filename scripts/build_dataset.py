from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import pypdf
from lxml import html

try:
    from .orientation_validation import validate_orientation
except ImportError:
    from orientation_validation import validate_orientation


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SITE_RESOLUTIONS_PATH = ROOT / "data" / "site_resolutions.csv"
GLOBAL_SITE_CANDIDATES_PATH = ROOT / "data" / "global_source_site_candidates.csv"
GLOBAL_SOURCE_IMAGES_PATH = ROOT / "data" / "global_source_image_links.csv"
REVIEWED_US_ARCHIVE_IMAGES_PATH = ROOT / "data" / "reviewed_us_archive_image_links.json"
ICCRA_IMAGES_PATH = ROOT / "data" / "iccra_image_links.csv"
COMMONS_EVENT_ASSERTIONS_PATH = ROOT / "data" / "commons_crop_circle_event_assertions.csv"
COMMONS_IMAGES_PATH = ROOT / "data" / "commons_crop_circle_images.csv"
COMMONS_ASSERTIONS_PATH = ROOT / "data" / "commons_crop_circle_assertions.csv"
REGISTERED_OVERLAYS_PATH = ROOT / "web" / "data" / "registered_overlays.json"
FORMATION_ALIAS_REVIEWS_PATH = ROOT / "data" / "formation_alias_reviews.csv"
SITE_STATUSES = {
    "unresolved",
    "locality_reference",
    "candidate_field",
    "corroborated_field",
    "registered_site",
}
FIELD_SITE_STATUSES = {"candidate_field", "corroborated_field", "registered_site"}
SOURCE_COORDINATE_METHODS = {
    "report_source_degree_decimal_minutes_converted",
    "source_decimal_degrees",
    "source_degree_decimal_minutes_converted",
}
SITE_RESOLUTION_FIELDS = {
    "formation_id", "site_status", "latitude", "longitude", "coordinate_uncertainty_m",
    "coordinate_method", "directly_visible", "alignment_eligible", "site_cluster_id",
    "search_aliases", "evidence_source_url", "evidence_artifact_ids",
    "evidence_artifact_sha256s", "imagery_provider", "imagery_acquisition_date",
    "review_status", "reviewer", "reviewed_at", "rights_status", "notes",
}
FORMATION_ALIAS_REVIEW_FIELDS = {
    "alias_formation_id", "canonical_formation_id", "review_status", "reviewer",
    "reviewed_at", "reason",
}
MONTHS = {name.lower(): index for index, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
MONTHS.update({name[:3]: index for name, index in list(MONTHS.items())})
US_STATES = {
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California",
    "CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia",
    "HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa",
    "KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland",
    "MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri",
    "MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey",
    "NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio",
    "OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina",
    "SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont",
    "VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming",
}
COUNTRY_ALIASES = {
    "united states of america":"United States", "usa":"United States", "us":"United States",
    "the netherlands":"Netherlands", "holland":"Netherlands", "uk":"United Kingdom",
    "england":"England", "scotland":"Scotland", "wales":"Wales", "czech republic":"Czechia",
}
COUNTRY_TO_ISO = {
    "United States":"US", "England":"GB", "Scotland":"GB", "Wales":"GB", "United Kingdom":"GB",
    "Netherlands":"NL", "Germany":"DE", "France":"FR", "Canada":"CA", "Australia":"AU",
    "Austria":"AT", "Belgium":"BE", "Brazil":"BR", "China":"CN", "Czechia":"CZ",
    "Denmark":"DK", "Finland":"FI", "Hungary":"HU", "Ireland":"IE", "Italy":"IT",
    "Japan":"JP", "Mexico":"MX", "New Zealand":"NZ", "Norway":"NO", "Poland":"PL",
    "Portugal":"PT", "Romania":"RO", "Russia":"RU", "Slovakia":"SK", "Slovenia":"SI",
    "South Africa":"ZA", "Spain":"ES", "Sweden":"SE", "Switzerland":"CH", "Ukraine":"UA",
}


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ").replace("\r", " ").strip()
    if any(mark in value for mark in ("Ã", "Â", "â", "Å", "Ø")):
        try:
            value = value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return re.sub(r"\s+", " ", value).strip()


def norm(value: str) -> str:
    value = clean_text(value).lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def canonical_country(value: str) -> str:
    value = clean_text(value)
    return COUNTRY_ALIASES.get(value.lower(), value)


def parse_date_location(line: str):
    match = re.match(r"^(\d{3,4})\s*(.*)$", clean_text(line))
    if not match:
        return None
    year = int(match.group(1))
    rest = match.group(2).strip()
    tokens = rest.split()
    month = day = None
    qualifier = ""
    if tokens and tokens[0].lower() in MONTHS:
        month = MONTHS[tokens.pop(0).lower()]
        if tokens and tokens[0].isdigit() and 1 <= int(tokens[0]) <= 31:
            day = int(tokens.pop(0))
        if tokens and tokens[0].lower() in {"early", "mid", "late", "beginning", "end"}:
            qualifier = tokens.pop(0).lower()
    place = " ".join(tokens).strip()
    precision = "day" if day else "month" if month else "year"
    if qualifier:
        precision = "qualified"
    date_iso = f"{year:04d}-{month:02d}-{day:02d}" if month and day else f"{year:04d}-{month:02d}" if month else f"{year:04d}"
    return year, month, day, qualifier, precision, date_iso, place


def parse_flexible_date(line: str):
    parsed = parse_date_location(line)
    if parsed:
        return parsed
    match = re.match(r"^(?:(early|mid|late)\s+)?([A-Za-z]+)(?:\s+(\d{1,2}))?\s*,?\s+(\d{4})$", clean_text(line), re.I)
    if not match or match.group(2).lower() not in MONTHS:
        return None
    qualifier = (match.group(1) or "").lower()
    month = MONTHS[match.group(2).lower()]
    day = int(match.group(3)) if match.group(3) else None
    year = int(match.group(4))
    precision = "day" if day else "qualified" if qualifier else "month"
    date_iso = f"{year:04d}-{month:02d}-{day:02d}" if day else f"{year:04d}-{month:02d}"
    return year, month, day, qualifier, precision, date_iso, ""


def assertion_id(source: str, source_url: str, ordinal: int) -> str:
    return "a_" + hashlib.sha1(f"{source}|{source_url}|{ordinal}".encode()).hexdigest()[:14]


def parse_pdf(pdf_path: Path):
    reader = pypdf.PdfReader(str(pdf_path))
    rows = []
    ignored = {"no diagram", "more info needed", "info@cropcircle-archive.com", "manmade"}
    for page_number, page in enumerate(reader.pages, start=1):
        lines = [clean_text(x) for x in (page.extract_text() or "").splitlines()]
        lines = [x for x in lines if x and not x.startswith("www.cropcirclecenter.com") and
                 not x.startswith("Please help us to keep going")]
        current = None
        extras = []
        ordinal = 0
        for line in lines:
            parsed = parse_date_location(line)
            if parsed:
                current = parsed
                extras = []
                continue
            if current and "|" in line:
                region, country = [clean_text(part) for part in line.split("|", 1)]
                year, month, day, qualifier, precision, date_iso, place = current
                flags = [x for x in extras if x.lower() in ignored]
                if not place:
                    place_parts = [x for x in extras if x.lower() not in ignored]
                    place = " ".join(place_parts)
                ordinal += 1
                source_url = "https://www.cropcirclecenter.com/"
                rows.append({
                    "assertion_id": assertion_id("cropcirclecenter_pdf", f"pdf-page-{page_number}", ordinal),
                    "source_name": "Crop Circle Center PDF catalog",
                    "source_url": source_url,
                    "source_record_url": "",
                    "retrieved_at": "2026-07-20",
                    "source_page": page_number,
                    "source_slot": ordinal,
                    "year": year, "month": month or "", "day": day or "", "date_iso": date_iso,
                    "date_precision": precision, "date_qualifier": qualifier,
                    "place": clean_text(place), "region": region,
                    "country": canonical_country(country), "country_code": "",
                    "county": "", "crop": "", "size_text": "",
                    "classification": "manmade" if "manmade" in flags else "unreviewed",
                    "thumbnail_url": "", "notes": "; ".join(flags),
                })
                current = None
                extras = []
            elif current:
                extras.append(line)
    return rows, len(reader.pages)


def parse_cropcirclecenter():
    rows = []
    for path in sorted((RAW / "cropcirclecenter" / "date").rglob("*.html")):
        try:
            doc = html.fromstring(path.read_bytes())
        except Exception:
            continue
        year = path.parent.name
        ym = path.stem
        page_url = f"https://www.cropcirclecenter.com/date/{year}/{ym}.html"
        ordinal = 0
        for span in doc.xpath('//span[contains(@class,"cclink")]'):
            ordinal += 1
            location = clean_text(" ".join(span.itertext()))
            place, region = (location.split("|", 1) + [""])[:2]
            place, region = clean_text(place), clean_text(region)
            tr = span
            while tr is not None and tr.tag.lower() != "tr":
                tr = tr.getparent()
            values = []
            cursor = tr.getnext() if tr is not None else None
            for _ in range(6):
                if cursor is None:
                    break
                values.extend(clean_text(" ".join(x.itertext())) for x in cursor.xpath('.//span[contains(@class,"body")]'))
                cursor = cursor.getnext()
            values = [x for x in values if x]
            country = canonical_country(values[0]) if values else ""
            date_text = values[1] if len(values) > 1 else ""
            parsed = parse_flexible_date(date_text)
            if not parsed:
                continue
            rec_year, month, day, qualifier, precision, date_iso, _ = parsed
            # Some location anchors in the source point to a different event.
            # Prefer the entry's image anchor, then a link whose URL-encoded date
            # agrees with the date printed in the row.
            links = tr.xpath('.//a[contains(@href,"ccdata")]') if tr is not None else []
            span_links = span.xpath('ancestor::a[contains(@href,"ccdata")]')
            candidates = list(dict.fromkeys(links + span_links))
            dated = []
            if day:
                date_path = f"/{rec_year:04d}/{month:02d}/{day:02d}/"
                dated = [link for link in candidates if date_path in (link.get("href") or "").replace("\\", "/")]
            image_links = [link for link in candidates if link.xpath('.//img[@src]')]
            link = (dated or image_links or candidates or [None])[0]
            href = link.get("href", "") if link is not None else ""
            if not href:
                continue
            record_url = urljoin(page_url, href)
            crop = values[2] if len(values) > 2 else ""
            size_text = values[3] if len(values) > 3 else ""
            img = tr.xpath('.//img[@src]') if tr is not None else []
            thumbnail_url = urljoin(page_url, img[0].get("src")) if img else ""
            rows.append({
                "assertion_id": assertion_id("cropcirclecenter_web", f"{page_url}|{record_url}", ordinal),
                "source_name": "Crop Circle Center",
                "source_url": page_url, "source_record_url": record_url,
                "retrieved_at": "2026-07-20", "source_page": "", "source_slot": ordinal,
                "year": rec_year, "month": month or "", "day": day or "", "date_iso": date_iso,
                "date_precision": precision, "date_qualifier": qualifier,
                "place": place, "region": region, "country": country, "country_code": "",
                "county": "", "crop": crop, "size_text": size_text,
                "classification": "unreviewed", "thumbnail_url": thumbnail_url, "notes": "",
            })
    return rows


def parse_iccra():
    rows = []
    date_re = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{1,2})?\s*,?\s*(\d{4})\s*[-–]\s*(.+)$", re.I)
    for path in sorted((RAW / "iccra" / "byyear").glob("*")):
        try:
            doc = html.fromstring(path.read_bytes())
        except Exception:
            continue
        page_url = "https://iccra.org/byyear/" + path.name.replace(" ", "%20")
        ordinal = 0
        for li in doc.xpath("//li"):
            text = clean_text(" ".join(li.itertext()))
            match = date_re.match(text)
            if not match:
                continue
            month = MONTHS[match.group(1).lower()]
            day = int(match.group(2)) if match.group(2) else None
            year = int(match.group(3))
            location = clean_text(match.group(4))
            parts = [clean_text(x) for x in location.split(",")]
            state_abbr = parts[-1].upper() if parts and re.fullmatch(r"[A-Z]{2}", parts[-1].upper()) else ""
            region = US_STATES.get(state_abbr, state_abbr)
            county = parts[-2] if len(parts) > 1 and "county" in parts[-2].lower() else ""
            place_parts = parts[:-2] if county else parts[:-1]
            place = ", ".join(place_parts).strip() or (parts[0] if parts else "")
            links = li.xpath(".//a[@href]")
            record_url = urljoin(page_url, links[0].get("href")) if links else page_url
            date_iso = f"{year:04d}-{month:02d}-{day:02d}" if day else f"{year:04d}-{month:02d}"
            ordinal += 1
            rows.append({
                "assertion_id": assertion_id("iccra", record_url, ordinal),
                "source_name": "ICCRA", "source_url": page_url, "source_record_url": record_url,
                "retrieved_at": "2026-07-20", "source_page": "", "source_slot": ordinal,
                "year": year, "month": month, "day": day or "", "date_iso": date_iso,
                "date_precision": "day" if day else "month", "date_qualifier": "",
                "place": place, "region": region, "country": "United States", "country_code": "US",
                "county": county, "crop": "", "size_text": "", "classification": "unreviewed",
                "thumbnail_url": "", "notes": f"ICCRA listing text: {text}",
            })
    return rows


def load_iccra_full():
    """Load the exhaustively reconciled ICCRA table when it has been built."""
    path = ROOT / "data" / "iccra_assertions_full.csv"
    if not path.exists():
        return None
    reconciliation_path = ROOT / "data" / "iccra_reconciliation.json"
    if not reconciliation_path.exists():
        raise ValueError("Exhaustive ICCRA CSV exists without its reconciliation record")
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    checks = reconciliation.get("completeness_checks", {})
    if (not checks.get("index_inventory_complete") or not checks.get("scope_inventory_complete") or
            not checks.get("every_parsed_index_slot_accounted")):
        raise ValueError("ICCRA reconciliation does not certify a complete index and archive-scope inventory")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Exhaustive ICCRA table is empty: {path}")
    required = {"year", "date_iso", "place", "region"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Exhaustive ICCRA table lacks required fields: {sorted(missing)}")
    expected_rows = reconciliation.get("totals", {}).get("canonical_assertions")
    if expected_rows != len(rows):
        raise ValueError(f"ICCRA reconciliation row count {expected_rows!r} does not match CSV row count {len(rows)}")
    seen = set()
    normalized = []
    for ordinal, row in enumerate(rows, start=1):
        row = {key: clean_text(value or "") for key, value in row.items()}
        row["source_name"] = row.get("source_name") or "ICCRA"
        row["source_url"] = row.get("source_url") or "https://iccra.org/"
        row["source_record_url"] = row.get("source_record_url") or row["source_url"]
        row["retrieved_at"] = row.get("retrieved_at") or "2026-07-21"
        row["country"] = canonical_country(row.get("country") or "United States")
        row["country_code"] = row.get("country_code") or "US"
        row["classification"] = row.get("classification") or "unreviewed"
        row["assertion_id"] = row.get("assertion_id") or assertion_id("iccra", row["source_record_url"], ordinal)
        if not row.get("year") or not row.get("date_iso") or not row.get("place") or not row.get("country"):
            raise ValueError(f"Incomplete exhaustive ICCRA row at ordinal {ordinal}")
        row["year"] = int(row["year"])
        if not row["date_iso"].startswith(str(row["year"])):
            raise ValueError(f"ICCRA date/year mismatch at ordinal {ordinal}: {row['date_iso']!r}")
        for date_part in ("month", "day"):
            if row.get(date_part):
                row[date_part] = int(row[date_part])
        row["date_precision"] = row.get("date_precision") or ("day" if row.get("day") else "month" if row.get("month") else "year")
        if row["assertion_id"] in seen:
            raise ValueError(f"Duplicate ICCRA assertion_id: {row['assertion_id']}")
        seen.add(row["assertion_id"])
        normalized.append(row)
    return normalized


def load_source_expansion():
    """Load the bounded, rights-reviewed external metadata assertion table."""
    path = ROOT / "data" / "source_expansion_assertions.csv"
    reconciliation_path = ROOT / "data" / "source_expansion_reconciliation.json"
    if not path.exists():
        return []
    if not reconciliation_path.exists():
        raise ValueError("Source-expansion assertions exist without reconciliation metadata")
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    checks = reconciliation.get("completeness_checks", {})
    required_checks = ("all_assertion_ids_unique", "all_rows_have_provenance",
                       "all_rows_have_valid_dates", "no_image_urls_emitted")
    if not all(checks.get(name) for name in required_checks):
        raise ValueError("Source-expansion reconciliation did not pass required metadata-only checks")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = reconciliation.get("yield", {}).get("expansion_assertions")
    if expected != len(rows):
        raise ValueError(f"Source-expansion row count {len(rows)} does not match reconciliation {expected!r}")
    seen = set()
    for ordinal, row in enumerate(rows, start=1):
        if not row.get("assertion_id", "").startswith("sx_"):
            raise ValueError(f"Invalid source-expansion assertion ID at row {ordinal}")
        if row["assertion_id"] in seen:
            raise ValueError(f"Duplicate source-expansion assertion ID: {row['assertion_id']}")
        seen.add(row["assertion_id"])
        if not all(row.get(field) for field in ("source_name", "source_url", "source_record_url", "year", "date_iso", "place", "country")):
            raise ValueError(f"Incomplete source-expansion row at ordinal {ordinal}")
        row["year"] = int(row["year"])
        for field in ("month", "day", "source_slot"):
            if row.get(field):
                row[field] = int(row[field])
    return rows


def load_commons_event_assertions(
    path: Path = COMMONS_EVENT_ASSERTIONS_PATH,
    images_path: Path = COMMONS_IMAGES_PATH,
) -> list[dict[str, object]]:
    """Load human-reviewed, openly licensed events missing from the base corpus."""
    if not path.is_file():
        return []
    event_rows = load_optional_csv(path)
    image_rows = {
        row.get("commons_image_id", ""): row for row in load_optional_csv(images_path)
        if row.get("commons_image_id")
    }
    assertions: list[dict[str, object]] = []
    for ordinal, row in enumerate(event_rows, 1):
        if row.get("review_status") != "accepted_distinct_same_place_event":
            raise ValueError(f"Commons event assertion row {ordinal} is not accepted")
        image_ids = [value.strip() for value in row.get("commons_image_ids", "").split(";") if value.strip()]
        if not image_ids or any(image_id not in image_rows for image_id in image_ids):
            raise ValueError(f"Commons event assertion row {ordinal} has unknown image IDs")
        images = [image_rows[image_id] for image_id in image_ids]
        if any(image.get("open_license_verified", "").lower() != "true" for image in images):
            raise ValueError(f"Commons event assertion row {ordinal} includes a non-open image")
        if any(image.get("captured_at") != row.get("date_iso") for image in images):
            raise ValueError(f"Commons event assertion row {ordinal} has inconsistent image dates")
        expected_key = entity_key(row)
        expected_formation_id = "cc_" + hashlib.sha1("|".join(expected_key).encode()).hexdigest()[:12]
        if row.get("formation_id") != expected_formation_id:
            raise ValueError(
                f"Commons event assertion row {ordinal} formation ID is not stable: "
                f"expected {expected_formation_id}"
            )
        image_urls = [image["original_file_url"] for image in images]
        assertions.append({
            "assertion_id": row["assertion_id"],
            "source_name": "Wikimedia Commons",
            "source_url": row["source_url"],
            "source_record_url": row["source_record_url"],
            "retrieved_at": "2026-07-21",
            "source_page": row["source_record_url"],
            "source_slot": ordinal,
            "year": int(row["year"]),
            "month": int(row["month"]),
            "day": int(row["day"]),
            "date_iso": row["date_iso"],
            "date_precision": row["date_precision"],
            "date_qualifier": "",
            "place": row["place"],
            "region": row["region"],
            "country": row["country"],
            "country_code": row["country_code"],
            "county": "",
            "crop": "",
            "size_text": "",
            "classification": "open_license_aerial_event_assertion",
            "thumbnail_url": image_urls[0],
            "image_urls": ";".join(image_urls),
            "notes": row["notes"],
            "rights_scope": row["rights_status"],
        })
    return assertions


def load_geonames():
    admin_names = {}
    admin_path = RAW / "geonames" / "admin1CodesASCII.txt"
    if admin_path.exists():
        for line in admin_path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                admin_names[parts[0]] = parts[1]
    index = defaultdict(list)
    paths = [RAW / "geonames" / "cities500" / "cities500.txt", RAW / "geonames" / "US" / "US.txt"]
    seen_ids = set()
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                p = line.rstrip("\n").split("\t")
                if len(p) < 15 or p[6] != "P" or p[0] in seen_ids:
                    continue
                seen_ids.add(p[0])
                country, admin1 = p[8], p[10]
                record = {
                    "geoname_id": p[0], "name": p[1], "latitude": float(p[4]), "longitude": float(p[5]),
                    "country_code": country, "admin1": admin_names.get(f"{country}.{admin1}", ""),
                    "population": int(p[14] or 0),
                }
                names = {p[1], p[2]}
                names.update((p[3] or "").split(",")[:40])
                for name in names:
                    if name:
                        index[(country, norm(name))].append(record)
    return index


def country_code(country: str) -> str:
    return COUNTRY_TO_ISO.get(canonical_country(country), "")


def geocode(row, index):
    cc = row.get("country_code") or country_code(row.get("country", ""))
    if not cc or not row.get("place"):
        return None
    raw_place = re.split(r"[/;]", row["place"])[0].strip()
    variants = [raw_place]
    variants.append(re.sub(r"\b(near|at|farm|field|hill|down|downs|stone circle|airfield|lake|mount|mt\.?|road)\b.*$", "", raw_place, flags=re.I).strip())
    words = raw_place.split()
    if len(words) > 1:
        variants.append(" ".join(words[:-1]))
        variants.append(words[0])
    candidates = []
    for variant in variants:
        candidates = index.get((cc, norm(variant)), [])
        if candidates:
            break
    if not candidates:
        return None
    region_norm = norm(row.get("region", ""))
    region_matches = [c for c in candidates if region_norm and norm(c["admin1"]) == region_norm]
    if cc == "US" and region_norm and not region_matches:
        return None
    pool = region_matches or candidates
    best = max(pool, key=lambda c: c["population"])
    confidence = 0.72 if region_matches and norm(variant) == norm(raw_place) else 0.62 if norm(variant) == norm(raw_place) else 0.48
    return {**best, "geocode_method": "geonames_locality_centroid", "geocode_confidence": confidence,
            "geocode_admin1": best["admin1"],
            "coordinate_uncertainty_km": 5 if confidence >= 0.7 else 15 if confidence >= 0.6 else 30}


def source_coordinate(assertion):
    lat_text = assertion.get("exact_latitude") or assertion.get("latitude")
    lon_text = assertion.get("exact_longitude") or assertion.get("longitude")
    method = assertion.get("coordinate_method") or assertion.get("geocode_method")
    if lat_text in (None, "") or lon_text in (None, "") or not method:
        return None
    try:
        latitude, longitude = float(lat_text), float(lon_text)
    except (TypeError, ValueError):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    try:
        confidence = float(assertion.get("coordinate_confidence") or assertion.get("geocode_confidence") or 0.9)
    except (TypeError, ValueError):
        confidence = 0.9
    try:
        uncertainty = float(assertion.get("coordinate_uncertainty_km") or 1.0)
    except (TypeError, ValueError):
        uncertainty = 1.0
    return {
        "latitude": latitude,
        "longitude": longitude,
        "geocode_method": method,
        "geocode_confidence": confidence,
        "coordinate_uncertainty_km": uncertainty,
        "geoname_id": "",
        "geocode_admin1": "",
    }


def entity_key(row):
    return (str(row["year"]), str(row.get("month", "")), str(row.get("day", "")),
            norm(row.get("place", "")), norm(row.get("region", "")),
            row.get("country_code") or country_code(row.get("country", "")))


def build_entities(assertions, geonames_index):
    entities = {}
    order = []
    for assertion in assertions:
        assertion["country"] = canonical_country(assertion.get("country", ""))
        assertion["country_code"] = assertion.get("country_code") or country_code(assertion["country"])
        key = entity_key(assertion)
        if key not in entities:
            digest = hashlib.sha1("|".join(key).encode()).hexdigest()[:12]
            entity = {
                "formation_id": f"cc_{digest}", "date_iso": assertion["date_iso"],
                "date_precision": assertion["date_precision"], "year": assertion["year"],
                "month": assertion.get("month", ""), "day": assertion.get("day", ""),
                "place": assertion.get("place", ""), "region": assertion.get("region", ""),
                "country": assertion.get("country", ""), "country_code": assertion.get("country_code", ""),
                "county": assertion.get("county", ""), "crop": assertion.get("crop", ""),
                "size_text": assertion.get("size_text", ""), "classification": assertion.get("classification", "unreviewed"),
                "latitude": "", "longitude": "", "geocode_method": "", "geocode_confidence": "",
                "coordinate_uncertainty_km": "", "geoname_id": "", "geocode_admin1": "", "source_count": 0,
                "source_names": [], "source_urls": [], "assertion_ids": [],
                "has_straight_component": "unknown", "orientation_status": "not_reviewed",
                "_source_coordinates": [],
                "_source_image_urls": [],
            }
            entities[key] = entity
            order.append(key)
        entity = entities[key]
        entity["source_names"].append(assertion["source_name"])
        entity["source_urls"].append(assertion.get("source_record_url") or assertion["source_url"])
        entity["assertion_ids"].append(assertion["assertion_id"])
        if assertion["source_name"] == "ICCRA":
            entity["county"] = assertion.get("county") or entity["county"]
            entity["place"] = assertion.get("place") or entity["place"]
            entity["region"] = assertion.get("region") or entity["region"]
        entity["crop"] = entity["crop"] or assertion.get("crop", "")
        entity["size_text"] = entity["size_text"] or assertion.get("size_text", "")
        coordinate = source_coordinate(assertion)
        if coordinate:
            entity["_source_coordinates"].append(coordinate)
        if assertion.get("image_urls"):
            entity["_source_image_urls"].extend(url.strip() for url in assertion["image_urls"].split(";") if url.strip())
    result = []
    for key in order:
        entity = entities[key]
        entity["source_names"] = "; ".join(sorted(set(entity["source_names"])))
        unique_urls = list(dict.fromkeys(entity["source_urls"]))
        unique_urls.sort(key=lambda value: (0 if "iccra.org" in value.lower() else 1 if "ccdata" in value.lower() else 2, value))
        entity["source_urls"] = "; ".join(unique_urls)
        entity["assertion_ids"] = "; ".join(entity["assertion_ids"])
        entity["source_count"] = len(entity["assertion_ids"].split("; "))
        coordinate_candidates = entity.pop("_source_coordinates")
        image_urls = list(dict.fromkeys(entity.pop("_source_image_urls")))
        entity["source_image_count"] = len(image_urls)
        entity["has_source_images"] = "yes_linked_rights_unverified" if image_urls else "no_linked_images"
        geo = min(coordinate_candidates, key=lambda item: item["coordinate_uncertainty_km"]) if coordinate_candidates else geocode(entity, geonames_index)
        if geo:
            for field in ("latitude", "longitude", "geocode_method", "geocode_confidence", "coordinate_uncertainty_km", "geoname_id", "geocode_admin1"):
                entity[field] = geo[field]
        result.append(entity)
    return result


def parse_boolean(value: object, field: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"{field} must be true or false, got {value!r}")


def load_formation_alias_reviews(path: Path = FORMATION_ALIAS_REVIEWS_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("formation_alias_reviews.csv has no header")
        missing = FORMATION_ALIAS_REVIEW_FIELDS - set(reader.fieldnames)
        if missing:
            raise ValueError("formation_alias_reviews.csv is missing fields: " + ", ".join(sorted(missing)))
        rows = list(reader)
    aliases = set()
    for ordinal, row in enumerate(rows, 2):
        alias_id = row.get("alias_formation_id", "").strip()
        canonical_id = row.get("canonical_formation_id", "").strip()
        if not alias_id or not canonical_id or alias_id == canonical_id:
            raise ValueError(f"invalid formation alias at row {ordinal}")
        if alias_id in aliases:
            raise ValueError(f"duplicate formation alias review for {alias_id}")
        if row.get("review_status", "").strip() != "accepted":
            raise ValueError(f"formation alias {alias_id} is not accepted")
        if not row.get("reviewer", "").strip() or not row.get("reviewed_at", "").strip():
            raise ValueError(f"formation alias {alias_id} lacks review provenance")
        aliases.add(alias_id)
    canonical_ids = {row["canonical_formation_id"].strip() for row in rows}
    if aliases & canonical_ids:
        raise ValueError("formation alias reviews contain a chain or cycle")
    return rows


def _merge_semicolon_values(*values: object) -> str:
    merged = []
    for value in values:
        for item in str(value or "").split("; "):
            item = item.strip()
            if item and item not in merged:
                merged.append(item)
    return "; ".join(merged)


def apply_formation_alias_reviews(entities: list[dict], reviews: list[dict[str, str]]) -> list[dict]:
    """Merge accepted report aliases while retaining every source assertion."""
    if not reviews:
        for entity in entities:
            entity.update({"alias_of": "", "merged_alias_formation_ids": "", "alias_count": 0})
        return entities
    by_id = {entity["formation_id"]: entity for entity in entities}
    reviewed_ids = {
        value for row in reviews for value in (
            row["alias_formation_id"].strip(), row["canonical_formation_id"].strip()
        )
    }
    missing = sorted(reviewed_ids - set(by_id))
    if missing:
        raise ValueError("formation alias reviews reference unknown IDs: " + ", ".join(missing))
    alias_ids = set()
    for review in sorted(reviews, key=lambda row: row["alias_formation_id"]):
        alias_id = review["alias_formation_id"].strip()
        canonical_id = review["canonical_formation_id"].strip()
        alias = by_id[alias_id]
        canonical = by_id[canonical_id]
        alias_ids.add(alias_id)
        canonical["source_names"] = _merge_semicolon_values(canonical.get("source_names"), alias.get("source_names"))
        canonical["source_urls"] = _merge_semicolon_values(canonical.get("source_urls"), alias.get("source_urls"))
        canonical["assertion_ids"] = _merge_semicolon_values(canonical.get("assertion_ids"), alias.get("assertion_ids"))
        canonical["source_count"] = len([value for value in canonical["assertion_ids"].split("; ") if value])
        canonical["source_image_count"] = int(canonical.get("source_image_count") or 0) + int(alias.get("source_image_count") or 0)
        canonical["has_source_images"] = (
            "yes_linked_rights_unverified" if canonical["source_image_count"] else "no_linked_images"
        )
        for field in ("county", "crop", "size_text"):
            canonical[field] = canonical.get(field) or alias.get(field, "")
        canonical["merged_alias_formation_ids"] = _merge_semicolon_values(
            canonical.get("merged_alias_formation_ids"), alias_id
        )
        canonical["alias_review_status"] = "accepted"
        canonical["alias_reviewed_at"] = _merge_semicolon_values(
            canonical.get("alias_reviewed_at"), review.get("reviewed_at", "")
        )
        canonical["alias_review_notes"] = _merge_semicolon_values(
            canonical.get("alias_review_notes"), review.get("reason", "")
        )
    output = []
    for entity in entities:
        if entity["formation_id"] in alias_ids:
            continue
        entity.setdefault("alias_of", "")
        entity.setdefault("merged_alias_formation_ids", "")
        entity["alias_count"] = len([
            value for value in entity["merged_alias_formation_ids"].split("; ") if value
        ])
        entity.setdefault("alias_review_status", "")
        entity.setdefault("alias_reviewed_at", "")
        entity.setdefault("alias_review_notes", "")
        output.append(entity)
    return output


def apply_complete_source_image_counts(
    entities: list[dict], assertions: list[dict]
) -> None:
    """Count all catalog relationships, not only images embedded in assertions.

    The global archive and Commons inventories are intentionally built as
    separate provenance tables.  Join them here by assertion/formation so the
    public entity records and location-work queue do not incorrectly claim that
    image-bearing international reports have no photographs.
    """
    urls_by_assertion: dict[str, set[str]] = defaultdict(set)
    urls_by_formation: dict[str, set[str]] = defaultdict(set)
    for assertion in assertions:
        assertion_id = assertion.get("assertion_id", "")
        for value in str(assertion.get("image_urls", "")).split(";"):
            url = value.strip()
            if assertion_id and url:
                urls_by_assertion[assertion_id].add(url)

    if GLOBAL_SOURCE_IMAGES_PATH.is_file():
        with GLOBAL_SOURCE_IMAGES_PATH.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                assertion_id = row.get("assertion_id", "").strip()
                image_url = row.get("image_url", "").strip()
                if assertion_id and image_url:
                    urls_by_assertion[assertion_id].add(image_url)

    if REVIEWED_US_ARCHIVE_IMAGES_PATH.is_file():
        reviewed_archive = json.loads(
            REVIEWED_US_ARCHIVE_IMAGES_PATH.read_text(encoding="utf-8")
        )
        for report in reviewed_archive.get("reports", []):
            formation_id = str(report.get("formation_id", "")).strip()
            assertion_id = str(report.get("assertion_id", "")).strip()
            for value in report.get("image_urls", []):
                image_url = str(value).strip()
                if formation_id and image_url:
                    urls_by_formation[formation_id].add(image_url)
                if assertion_id and image_url:
                    urls_by_assertion[assertion_id].add(image_url)

    if ICCRA_IMAGES_PATH.is_file():
        with ICCRA_IMAGES_PATH.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("http_status", "").strip() != "200":
                    continue
                image_url = row.get("image_url", "").strip()
                for assertion_id in str(row.get("assertion_ids", "")).split(";"):
                    assertion_id = assertion_id.strip()
                    if assertion_id and image_url:
                        urls_by_assertion[assertion_id].add(image_url)

    commons_by_id: dict[str, str] = {}
    if COMMONS_IMAGES_PATH.is_file():
        with COMMONS_IMAGES_PATH.open(encoding="utf-8-sig", newline="") as handle:
            commons_by_id = {
                row.get("commons_image_id", "").strip(): row.get(
                    "original_file_url", ""
                ).strip()
                for row in csv.DictReader(handle)
                if row.get("commons_image_id", "").strip()
                and row.get("original_file_url", "").strip()
            }

    if COMMONS_EVENT_ASSERTIONS_PATH.is_file():
        with COMMONS_EVENT_ASSERTIONS_PATH.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                assertion_id = row.get("assertion_id", "").strip()
                for image_id in str(row.get("commons_image_ids", "")).split(";"):
                    image_url = commons_by_id.get(image_id.strip(), "")
                    if assertion_id and image_url:
                        urls_by_assertion[assertion_id].add(image_url)

    if COMMONS_ASSERTIONS_PATH.is_file():
        with COMMONS_ASSERTIONS_PATH.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                if row.get("match_status", "").strip() not in {
                    "exact_place_and_date",
                    "reviewed_same_event_later_documentation",
                }:
                    continue
                formation_id = row.get("matched_formation_id", "").strip()
                image_url = commons_by_id.get(
                    row.get("commons_image_id", "").strip(), ""
                )
                if formation_id and image_url:
                    urls_by_formation[formation_id].add(image_url)

    if REGISTERED_OVERLAYS_PATH.is_file():
        overlay_payload = json.loads(
            REGISTERED_OVERLAYS_PATH.read_text(encoding="utf-8")
        )
        for overlay in overlay_payload.get("overlays", []):
            formation_id = str(overlay.get("formation_id", "")).strip()
            image_url = str(overlay.get("source_image_url", "")).strip()
            if formation_id and image_url:
                urls_by_formation[formation_id].add(image_url)

    for entity in entities:
        image_urls = set(urls_by_formation.get(entity["formation_id"], set()))
        for alias_id in str(entity.get("merged_alias_formation_ids", "")).split("; "):
            image_urls.update(urls_by_formation.get(alias_id.strip(), set()))
        for assertion_id in str(entity.get("assertion_ids", "")).split("; "):
            image_urls.update(urls_by_assertion.get(assertion_id.strip(), set()))
        entity["source_image_count"] = len(image_urls)
        entity["has_source_images"] = (
            "yes_linked_rights_unverified" if image_urls else "no_linked_images"
        )


def load_site_resolutions(path: Path = SITE_RESOLUTIONS_PATH) -> dict[str, dict[str, object]]:
    """Load reviewed field-location overrides without conflating review or rights.

    The table is deliberately keyed by stable ``formation_id``.  Its
    ``site_status`` describes spatial confidence only; ``review_status`` and
    ``rights_status`` remain independent metadata and never change that tier.
    """
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("site_resolutions.csv has no header")
        missing = SITE_RESOLUTION_FIELDS - set(reader.fieldnames)
        if missing:
            raise ValueError("site_resolutions.csv is missing fields: " + ", ".join(sorted(missing)))
        rows = list(reader)
    resolutions: dict[str, dict[str, object]] = {}
    for ordinal, row in enumerate(rows, 2):
        formation_id = row.get("formation_id", "").strip()
        status = row.get("site_status", "").strip()
        if not formation_id:
            raise ValueError(f"site_resolutions.csv row {ordinal} has no formation_id")
        if formation_id in resolutions:
            raise ValueError(f"duplicate site resolution for {formation_id}")
        if status not in SITE_STATUSES:
            raise ValueError(f"invalid site_status for {formation_id}: {status!r}")
        resolved: dict[str, object] = dict(row)
        if status in FIELD_SITE_STATUSES:
            try:
                latitude = float(row.get("latitude", ""))
                longitude = float(row.get("longitude", ""))
                uncertainty_m = float(row.get("coordinate_uncertainty_m", ""))
            except (TypeError, ValueError) as error:
                raise ValueError(f"field site {formation_id} lacks numeric coordinates/uncertainty") from error
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError(f"field site {formation_id} has invalid coordinates")
            if not math.isfinite(uncertainty_m) or uncertainty_m <= 0:
                raise ValueError(f"field site {formation_id} has invalid uncertainty")
            if not row.get("coordinate_method", "").strip():
                raise ValueError(f"field site {formation_id} has no coordinate_method")
            required_evidence_fields = (
                "evidence_source_url", "evidence_artifact_ids", "review_status",
                "reviewer", "reviewed_at", "rights_status", "notes",
            )
            missing_evidence = [
                field for field in required_evidence_fields if not row.get(field, "").strip()
            ]
            if missing_evidence:
                raise ValueError(
                    f"field site {formation_id} lacks reviewed evidence metadata: "
                    + ", ".join(missing_evidence)
                )
            resolved.update({
                "latitude": latitude,
                "longitude": longitude,
                "coordinate_uncertainty_m": uncertainty_m,
                "directly_visible": parse_boolean(row.get("directly_visible", ""), "directly_visible"),
                "alignment_eligible": parse_boolean(row.get("alignment_eligible", ""), "alignment_eligible"),
            })
            artifact_ids = [
                value.strip() for value in row.get("evidence_artifact_ids", "").split(";") if value.strip()
            ]
            hashes = [value.strip() for value in row.get("evidence_artifact_sha256s", "").split(";") if value.strip()]
            if not hashes or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
                raise ValueError(f"field site {formation_id} has invalid evidence artifact SHA-256 metadata")
            if len(artifact_ids) != len(hashes):
                raise ValueError(f"field site {formation_id} evidence artifact IDs/hashes do not pair")
            if resolved["alignment_eligible"] and status not in {"corroborated_field", "registered_site"}:
                raise ValueError(f"alignment-eligible site {formation_id} has insufficient spatial status")
        resolutions[formation_id] = resolved
    return resolutions


def load_global_source_site_resolutions(
    path: Path = GLOBAL_SITE_CANDIDATES_PATH,
) -> dict[str, dict[str, object]]:
    """Promote explicit source-map targets to visible, non-accepted candidates.

    These rows are useful search loci, not independent image/landmark matches.
    They therefore remain yellow ``candidate_field`` points, are never eligible
    for alignment tests, and cannot override a curated site resolution.
    """
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    required = {
        "site_candidate_id", "source_name", "formation_id", "place", "region",
        "country_code", "latitude", "longitude", "coordinate_method",
        "coordinate_reference_text", "coordinate_uncertainty_m",
        "coordinate_source_url", "source_page_sha256", "source_page_http_status",
        "linked_image_count", "rights_status", "review_status",
    }
    if rows and not required <= set(rows[0]):
        raise ValueError(
            "global_source_site_candidates.csv is missing fields: "
            + ", ".join(sorted(required - set(rows[0])))
        )
    supported_methods = {
        "streetmap_bng_pointer_to_wgs84",
        "streetmap_os_grid_reference_to_wgs84",
        "reported_os_grid_reference_to_wgs84",
        "google_maps_dms_target",
        "google_maps_place_target",
        "google_maps_query_coordinate",
        "google_maps_satellite_view_center",
    }
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for ordinal, row in enumerate(rows, 2):
        formation_id = row.get("formation_id", "").strip()
        if not formation_id:
            continue
        method = row.get("coordinate_method", "").strip()
        if method not in supported_methods:
            continue
        if row.get("source_page_http_status", "").strip() != "200":
            continue
        if int(row.get("linked_image_count", "0") or 0) < 1:
            continue
        try:
            latitude = float(row.get("latitude", ""))
            longitude = float(row.get("longitude", ""))
            uncertainty_m = float(row.get("coordinate_uncertainty_m", ""))
        except ValueError as error:
            raise ValueError(f"global site candidate row {ordinal} has invalid numbers") from error
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and uncertainty_m > 0):
            raise ValueError(f"global site candidate row {ordinal} is outside WGS84")
        if "grid" in method or "bng" in method:
            if row.get("country_code", "").strip() != "GB":
                raise ValueError(f"non-GB row {ordinal} was parsed as a British grid reference")
            if not (49 <= latitude <= 61 and -9 <= longitude <= 3):
                raise ValueError(f"British grid row {ordinal} converted outside Great Britain")
        page_hash = row.get("source_page_sha256", "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", page_hash):
            raise ValueError(f"global site candidate row {ordinal} lacks a page SHA-256")
        normalized = dict(row)
        normalized.update({
            "latitude": latitude,
            "longitude": longitude,
            "coordinate_uncertainty_m": uncertainty_m,
            "source_page_sha256": page_hash,
        })
        grouped[formation_id].append(normalized)

    resolutions: dict[str, dict[str, object]] = {}
    for formation_id, candidates in grouped.items():
        best = min(
            candidates,
            key=lambda row: (
                float(row["coordinate_uncertainty_m"]),
                0 if str(row["coordinate_method"]).startswith("google_maps_") else 1,
                str(row["site_candidate_id"]),
            ),
        )
        source_name = str(best["source_name"])
        reference = str(best["coordinate_reference_text"])
        resolutions[formation_id] = {
            "formation_id": formation_id,
            "site_status": "candidate_field",
            "latitude": best["latitude"],
            "longitude": best["longitude"],
            "coordinate_uncertainty_m": max(25.0, float(best["coordinate_uncertainty_m"])),
            "coordinate_method": f"source_map_target_{best['coordinate_method']}",
            "directly_visible": False,
            "alignment_eligible": False,
            "site_cluster_id": "",
            "search_aliases": "; ".join(
                value for value in (best.get("place", ""), best.get("region", "")) if value
            ),
            "evidence_source_url": best["coordinate_source_url"],
            "evidence_artifact_ids": best["site_candidate_id"],
            "evidence_artifact_sha256s": best["source_page_sha256"],
            "imagery_provider": f"{source_name} source map link",
            "imagery_acquisition_date": "",
            "review_status": "source_map_target_not_landmark_validated",
            "reviewer": "Automated source-map extraction with geographic sanity gates",
            "reviewed_at": "2026-07-21",
            "rights_status": "coordinate_metadata_only; source pixels follow archive policy",
            "resolution_source": "global_source_map_candidate_queue",
            "notes": (
                f"The source report exposes an explicit map coordinate or grid target ({reference}). "
                "It is published as a candidate search field, not an accepted formation site: "
                "the aerial source image has not yet been independently matched to roads, tree lines, "
                "field edges, buildings, or historical imagery. It is excluded from alignment tests."
            ),
        }
    return resolutions


def automatic_site_status(entity: dict) -> str:
    if entity.get("latitude", "") == "" or entity.get("longitude", "") == "":
        return "unresolved"
    if entity.get("geocode_method") == "geonames_locality_centroid":
        return "locality_reference"
    if entity.get("geocode_method") not in SOURCE_COORDINATE_METHODS:
        raise ValueError(
            f"unsupported automatic source-coordinate method for {entity.get('formation_id')}: "
            f"{entity.get('geocode_method')!r}"
        )
    return "registered_site"


def apply_site_resolutions(entities: list[dict], resolutions: dict[str, dict[str, object]]) -> Counter:
    """Classify every entity and apply reviewed field coordinates first.

    Existing GeoNames coordinates are retained as locality references.  A
    reviewed field resolution replaces the legacy canonical coordinate while
    preserving the locality centroid in dedicated columns for audit/search.
    """
    by_id = {entity["formation_id"]: entity for entity in entities}
    unknown = sorted(set(resolutions) - set(by_id))
    if unknown:
        raise ValueError("site resolutions reference unknown formation IDs: " + ", ".join(unknown))

    counts: Counter = Counter()
    for entity in entities:
        baseline_status = automatic_site_status(entity)
        baseline_latitude = entity.get("latitude", "")
        baseline_longitude = entity.get("longitude", "")
        baseline_method = entity.get("geocode_method", "")
        baseline_uncertainty_km = entity.get("coordinate_uncertainty_km", "")
        baseline_geoname_id = entity.get("geoname_id", "")
        baseline_admin1 = entity.get("geocode_admin1", "")
        entity.update({
            "site_status": baseline_status,
            "site_latitude": baseline_latitude if baseline_status == "registered_site" else "",
            "site_longitude": baseline_longitude if baseline_status == "registered_site" else "",
            "site_coordinate_method": baseline_method if baseline_status == "registered_site" else "",
            "site_coordinate_uncertainty_m": (
                float(baseline_uncertainty_km) * 1000
                if baseline_status == "registered_site" and baseline_uncertainty_km not in (None, "") else ""
            ),
            "site_directly_visible": "",
            "site_alignment_eligible": "false",
            "site_cluster_id": "",
            "site_search_aliases": "",
            "site_evidence_source_url": "",
            "site_evidence_artifact_ids": "",
            "site_evidence_artifact_sha256s": "",
            "site_imagery_provider": "",
            "site_imagery_acquisition_date": "",
            "site_review_status": "source_report_not_independently_reviewed" if baseline_status == "registered_site" else "not_reviewed",
            "site_reviewer": "",
            "site_reviewed_at": "",
            "site_rights_status": "coordinate_metadata_only" if baseline_status == "registered_site" else "not_applicable",
            "site_notes": "",
            "site_resolution_source": "automatic_source_coordinate" if baseline_status == "registered_site" else (
                "automatic_geonames_locality" if baseline_status == "locality_reference" else "automatic_unresolved"
            ),
            "locality_latitude": baseline_latitude if baseline_status == "locality_reference" else "",
            "locality_longitude": baseline_longitude if baseline_status == "locality_reference" else "",
            "locality_coordinate_method": baseline_method if baseline_status == "locality_reference" else "",
            "locality_coordinate_uncertainty_km": baseline_uncertainty_km if baseline_status == "locality_reference" else "",
            "locality_geoname_id": baseline_geoname_id if baseline_status == "locality_reference" else "",
            "locality_admin1": baseline_admin1 if baseline_status == "locality_reference" else "",
        })

        override = resolutions.get(entity["formation_id"])
        if override:
            status = str(override["site_status"])
            entity.update({
                "site_status": status,
                "site_alignment_eligible": "true" if override.get("alignment_eligible") else "false",
                "site_cluster_id": str(override.get("site_cluster_id", "")),
                "site_search_aliases": str(override.get("search_aliases", "")),
                "site_evidence_source_url": str(override.get("evidence_source_url", "")),
                "site_evidence_artifact_ids": str(override.get("evidence_artifact_ids", "")),
                "site_evidence_artifact_sha256s": str(override.get("evidence_artifact_sha256s", "")),
                "site_imagery_provider": str(override.get("imagery_provider", "")),
                "site_imagery_acquisition_date": str(override.get("imagery_acquisition_date", "")),
                "site_review_status": str(override.get("review_status", "")),
                "site_reviewer": str(override.get("reviewer", "")),
                "site_reviewed_at": str(override.get("reviewed_at", "")),
                "site_rights_status": str(override.get("rights_status", "")),
                "site_notes": str(override.get("notes", "")),
                "site_resolution_source": str(
                    override.get("resolution_source", "reviewed_override")
                ),
            })
            if status in FIELD_SITE_STATUSES:
                latitude = float(override["latitude"])
                longitude = float(override["longitude"])
                uncertainty_m = float(override["coordinate_uncertainty_m"])
                confidence = {"candidate_field": 0.65, "corroborated_field": 0.9, "registered_site": 0.95}[status]
                entity.update({
                    "site_latitude": latitude,
                    "site_longitude": longitude,
                    "site_coordinate_method": str(override["coordinate_method"]),
                    "site_coordinate_uncertainty_m": uncertainty_m,
                    "site_directly_visible": "true" if override["directly_visible"] else "false",
                    "latitude": latitude,
                    "longitude": longitude,
                    "geocode_method": str(override["coordinate_method"]),
                    "geocode_confidence": confidence,
                    "coordinate_uncertainty_km": uncertainty_m / 1000,
                    "geoname_id": "",
                    "geocode_admin1": "",
                })
            elif status == "unresolved":
                entity.update({
                    "site_latitude": "", "site_longitude": "", "site_coordinate_method": "",
                    "site_coordinate_uncertainty_m": "", "site_directly_visible": "",
                    "latitude": "", "longitude": "", "geocode_method": "",
                    "geocode_confidence": "", "coordinate_uncertainty_km": "",
                    "geoname_id": "", "geocode_admin1": "",
                })
        status = entity["site_status"]
        entity["location_status"] = status
        entity["location_role"] = (
            "formation_site" if status in FIELD_SITE_STATUSES else
            "locality_reference" if status == "locality_reference" else "unresolved"
        )
        entity["accepted_site_latitude"] = entity.get("site_latitude", "") if status in {
            "corroborated_field", "registered_site"
        } else ""
        entity["accepted_site_longitude"] = entity.get("site_longitude", "") if status in {
            "corroborated_field", "registered_site"
        } else ""
        entity["locality_reference_latitude"] = entity.get("locality_latitude", "")
        entity["locality_reference_longitude"] = entity.get("locality_longitude", "")
        counts[entity["site_status"]] += 1
    return counts


def load_optional_csv(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_optional_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def apply_straight_component_enrichment(entities):
    candidates = load_optional_csv(ROOT / "data" / "straight_component_candidates.csv")
    by_assertion = {row.get("assertion_id", ""): row for row in candidates if row.get("assertion_id")}
    tier_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
    counts = Counter()
    for entity in entities:
        assertion_ids = entity.get("assertion_ids", "").split("; ")
        matches = [by_assertion[item] for item in assertion_ids if item in by_assertion]
        entity.update({
            "straight_component_tier": "not_analyzed",
            "straight_detector_score": "",
            "straight_candidate_id": "",
            "diagram_angle_deg": "",
            "diagram_angle_uncertainty_deg": "",
            "diagram_angle_reference": "",
            "straight_review_status": "not_reviewed",
        })
        if not matches:
            entity["has_straight_component"] = "not_analyzed"
            counts["not_analyzed"] += 1
            continue
        best = max(matches, key=lambda row: (tier_rank.get(row.get("straight_component_tier", "none"), -1),
                                              float(row.get("detector_score") or 0)))
        tier = best.get("straight_component_tier") or "none"
        entity["straight_component_tier"] = tier
        entity["straight_detector_score"] = best.get("detector_score", "")
        entity["straight_candidate_id"] = best.get("candidate_id", "")
        entity["diagram_angle_deg"] = best.get("dominant_axis_image_deg", "")
        entity["diagram_angle_uncertainty_deg"] = best.get("axis_uncertainty_deg", "")
        entity["diagram_angle_reference"] = best.get("axis_reference", "")
        entity["straight_review_status"] = "automated_pdf_diagram"
        if tier in {"high", "medium"}:
            entity["has_straight_component"] = "yes_candidate"
        elif tier == "low":
            entity["has_straight_component"] = "possible_candidate"
        else:
            entity["has_straight_component"] = "no_candidate"
        counts[tier] += 1
    return counts


def apply_iccra_image_straight_enrichment(entities):
    """Attach metadata-only ICCRA image review candidates to formations.

    This is deliberately independent from the validated PDF-diagram detector.
    It does not change ``has_straight_component`` or orientation qualification:
    source photographs, maps, and diagrams contain unrelated straight edges and
    their automated tiers are only a queue for human review.
    """
    candidates = load_optional_csv(ROOT / "data" / "iccra_image_straight_candidates.csv")
    by_assertion = defaultdict(list)
    for row in candidates:
        for assertion_id in (item.strip() for item in row.get("assertion_ids", "").split(";")):
            if assertion_id:
                by_assertion[assertion_id].append(row)
    tier_rank = {"not_analyzed": -1, "none": 0, "low": 1, "medium": 2, "high": 3}
    counts = Counter()
    for entity in entities:
        assertion_ids = [item for item in entity.get("assertion_ids", "").split("; ") if item]
        matches = [row for assertion_id in assertion_ids for row in by_assertion.get(assertion_id, [])]
        # The same bytes can be referenced from more than one ICCRA page. Count
        # an image once per formation while retaining a deterministic best row.
        unique_matches = {}
        for row in matches:
            identity = row.get("image_sha256") or row.get("image_link_id") or row.get("candidate_id")
            unique_matches.setdefault(identity, row)
        matches = list(unique_matches.values())
        analyzed = [row for row in matches if row.get("analysis_status") == "analyzed_private_cache"]
        review_candidates = [row for row in analyzed if row.get("straight_component_tier") in {"high", "medium", "low"}]
        entity.update({
            "source_image_straight_status": "no_linked_iccra_image_analysis",
            "source_image_straight_tier": "not_analyzed",
            "source_image_straight_score": "",
            "source_image_straight_candidate_id": "",
            "source_image_axis_deg": "",
            "source_image_axis_uncertainty_deg": "",
            "source_image_axis_reference": "",
            "source_image_analysis_count": len(analyzed),
            "source_image_candidate_count": len(review_candidates),
            "source_image_straight_caveat": "",
        })
        if not matches:
            counts["no_linked_iccra_image_analysis"] += 1
            continue
        if not analyzed:
            entity["source_image_straight_status"] = "linked_but_analysis_unavailable"
            counts["linked_but_analysis_unavailable"] += 1
            continue
        best = max(
            analyzed,
            key=lambda row: (
                tier_rank.get(row.get("straight_component_tier", "not_analyzed"), -1),
                float(row.get("detector_score") or 0),
                row.get("candidate_id", ""),
            ),
        )
        tier = best.get("straight_component_tier") or "none"
        entity["source_image_straight_status"] = f"review_candidate_{tier}" if tier in {"high", "medium", "low"} else "analyzed_no_candidate"
        entity["source_image_straight_tier"] = tier
        entity["source_image_straight_score"] = best.get("detector_score", "")
        entity["source_image_straight_candidate_id"] = best.get("candidate_id", "")
        entity["source_image_axis_deg"] = best.get("dominant_axis_image_deg", "")
        entity["source_image_axis_uncertainty_deg"] = best.get("axis_uncertainty_deg", "")
        entity["source_image_axis_reference"] = best.get("axis_reference", "")
        entity["source_image_straight_caveat"] = best.get("caveat", "")
        counts[entity["source_image_straight_status"]] += 1
    return counts


def apply_orientation_status(entities):
    rows = load_optional_csv(ROOT / "data" / "orientation_observations.csv")
    entity_by_id = {entity["formation_id"]: entity for entity in entities}
    qualified = set()
    observed = set()
    invalid_foreign_keys = 0
    for row in rows:
        formation_id = row.get("formation_id", "")
        if not formation_id:
            continue
        entity = entity_by_id.get(formation_id)
        if not entity:
            invalid_foreign_keys += 1
            continue
        observed.add(formation_id)
        result = validate_orientation(row, entity)
        if "orientation_assertion_not_attached_to_formation" in result["reasons"]:
            invalid_foreign_keys += 1
        if result["qualified"]:
            qualified.add(formation_id)
    for entity in entities:
        formation_id = entity["formation_id"]
        if formation_id in qualified:
            entity["orientation_status"] = "evidence_qualified_true_north"
            entity["has_straight_component"] = "yes_evidence_reviewed"
            entity["straight_review_status"] = "human_orientation_evidence_reviewed"
        elif formation_id in observed:
            entity["orientation_status"] = "observation_rejected_or_incomplete"
        elif entity["has_straight_component"] in {"yes_candidate", "possible_candidate"}:
            entity["orientation_status"] = "diagram_only_no_true_north"
        else:
            entity["orientation_status"] = "not_reviewed"
    return {
        "observations": len(rows),
        "qualified_formations": len(qualified),
        "invalid_foreign_keys": invalid_foreign_keys,
    }


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


GEOJSON_PROPERTY_FIELDS = (
    "formation_id", "date_iso", "date_precision", "year", "place", "region", "country",
    "country_code", "county", "crop", "classification", "coordinate_uncertainty_km",
    "geocode_method", "geocode_admin1", "geocode_confidence", "source_count", "source_names", "source_urls",
    "has_straight_component", "straight_component_tier", "straight_detector_score", "straight_candidate_id",
    "diagram_angle_deg", "diagram_angle_uncertainty_deg", "diagram_angle_reference",
    "straight_review_status", "orientation_status", "source_image_count", "has_source_images",
    "source_image_straight_status", "source_image_straight_tier", "source_image_straight_score",
    "source_image_straight_candidate_id", "source_image_axis_deg",
    "source_image_axis_uncertainty_deg", "source_image_axis_reference",
    "source_image_analysis_count", "source_image_candidate_count", "source_image_straight_caveat",
    "site_status", "site_coordinate_method", "site_coordinate_uncertainty_m", "site_directly_visible",
    "site_alignment_eligible", "site_cluster_id", "site_search_aliases", "site_evidence_source_url",
    "site_evidence_artifact_ids", "site_evidence_artifact_sha256s", "site_imagery_provider", "site_imagery_acquisition_date",
    "site_review_status", "site_reviewer", "site_reviewed_at", "site_rights_status", "site_notes",
    "site_resolution_source", "locality_coordinate_method", "locality_coordinate_uncertainty_km",
    "location_status", "location_role", "accepted_site_latitude", "accepted_site_longitude",
    "locality_reference_latitude", "locality_reference_longitude", "alias_of",
    "merged_alias_formation_ids", "alias_count", "alias_review_status", "alias_reviewed_at",
    "alias_review_notes",
)

PUBLIC_INDEX_FIELDS = (
    "formation_id", "date_iso", "date_precision", "year", "place", "region", "country",
    "country_code", "county", "crop", "size_text", "classification", "latitude", "longitude",
    "geocode_method", "coordinate_uncertainty_km", "source_count", "source_names", "source_urls",
    "has_straight_component", "orientation_status", "source_image_count", "has_source_images",
    "merged_alias_formation_ids", "alias_count", "alias_review_status", "site_status",
    "site_coordinate_method", "site_coordinate_uncertainty_m", "site_directly_visible",
    "site_alignment_eligible", "site_cluster_id", "site_search_aliases", "site_evidence_source_url",
    "site_evidence_artifact_ids", "site_evidence_artifact_sha256s", "site_imagery_provider", "site_imagery_acquisition_date",
    "site_review_status", "site_rights_status", "site_notes", "location_status", "location_role",
    "straight_component_tier", "diagram_angle_deg", "source_image_straight_tier",
    "source_image_axis_deg", "source_image_axis_uncertainty_deg",
)

SITE_GEOJSON_PROPERTY_FIELDS = PUBLIC_INDEX_FIELDS

LOCALITY_GEOJSON_PROPERTY_FIELDS = (
    "formation_id", "date_iso", "date_precision", "year", "place", "region", "country",
    "country_code", "county", "source_count", "source_names", "source_urls",
    "has_straight_component", "orientation_status", "source_image_count", "has_source_images",
    "site_status", "locality_coordinate_method", "locality_coordinate_uncertainty_km",
    "location_status", "location_role", "straight_component_tier", "diagram_angle_deg",
    "source_image_straight_tier", "source_image_axis_deg", "source_image_axis_uncertainty_deg",
)


def compact_properties(row: dict, fields: tuple[str, ...]) -> dict:
    """Keep the public payload complete for the UI while omitting empty repeated keys."""
    return {
        field: row.get(field)
        for field in fields
        if row.get(field) not in {"", None}
    }


def write_geojson(path: Path, entities, coordinate_role: str = "canonical"):
    roles = {
        "canonical": ("latitude", "longitude", None),
        "site": ("site_latitude", "site_longitude", FIELD_SITE_STATUSES),
        "locality": ("locality_latitude", "locality_longitude", {"locality_reference"}),
    }
    if coordinate_role not in roles:
        raise ValueError(f"unsupported GeoJSON coordinate role: {coordinate_role}")
    latitude_field, longitude_field, allowed_statuses = roles[coordinate_role]
    features = []
    for row in entities:
        if allowed_statuses is not None and row.get("site_status") not in allowed_statuses:
            continue
        if row.get(latitude_field, "") == "" or row.get(longitude_field, "") == "":
            continue
        property_fields = GEOJSON_PROPERTY_FIELDS
        if coordinate_role == "site":
            property_fields = SITE_GEOJSON_PROPERTY_FIELDS
        elif coordinate_role == "locality":
            property_fields = LOCALITY_GEOJSON_PROPERTY_FIELDS
        properties = compact_properties(row, property_fields)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row[longitude_field], row[latitude_field]]},
            "properties": properties,
        })
    method_field = "geocode_method" if coordinate_role == "canonical" else (
        "site_coordinate_method" if coordinate_role == "site" else "locality_coordinate_method"
    )
    method_counts = Counter(feature["properties"].get(method_field, "") for feature in features)
    notices = {
        "canonical": "Backward-compatible mixed coordinate layer. Use formation_sites.geojson for field locations and locality_references.geojson only as search context.",
        "site": "Field-location layer only. Candidate, corroborated, and registered tiers remain distinct; inspect uncertainty and review metadata.",
        "locality": "Locality reference centroids are not crop-formation sites and must not be used as ray origins or alignment targets.",
    }
    payload = {"type":"FeatureCollection", "features":features,
               "metadata":{"generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                           "coordinate_role": coordinate_role,
                           "coordinate_notice": notices[coordinate_role],
                           "coordinate_methods":dict(method_counts)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def write_formation_index(path: Path, entities: list[dict]) -> None:
    payload = {
        "metadata": {
            "schema_version": "crop-circle-atlas/formation-index/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "record_count": len(entities),
            "site_status_counts": dict(Counter(row["site_status"] for row in entities)),
            "merged_alias_count": sum(int(row.get("alias_count") or 0) for row in entities),
            "coordinate_notice": "Field sites, locality references, and unresolved reports are distinct. Locality references are not formation sites.",
        },
        "formations": [compact_properties(entity, PUBLIC_INDEX_FIELDS) for entity in entities],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def line_priority(entity: dict) -> int:
    if entity.get("has_straight_component") == "yes_evidence_reviewed":
        return 3
    if (entity.get("has_straight_component") == "yes_candidate" or
            entity.get("straight_component_tier") in {"high", "medium"} or
            entity.get("source_image_straight_tier") in {"high", "medium"}):
        return 2
    if (entity.get("has_straight_component") == "possible_candidate" or
            entity.get("straight_component_tier") == "low" or
            entity.get("source_image_straight_tier") == "low"):
        return 1
    return 0


def next_location_action(entity: dict, has_images: bool, line_level: int) -> str:
    status = entity["site_status"]
    if status == "unresolved":
        return "research_exact_field_location"
    if status == "locality_reference":
        return "replace_locality_reference_with_field_evidence"
    if status == "candidate_field":
        return "corroborate_candidate_field"
    if status == "corroborated_field":
        return "register_source_image_and_review_components" if has_images else "seek_registration_evidence"
    if line_level or has_images:
        return "review_or_register_straight_components"
    return "site_resolution_complete"


def build_location_work_queue(entities: list[dict]) -> list[dict[str, object]]:
    status_need = {
        "unresolved": 4,
        "locality_reference": 3,
        "candidate_field": 2,
        "corroborated_field": 1,
        "registered_site": 0,
    }
    queue = []
    for entity in entities:
        is_us = entity.get("country_code") == "US"
        has_images = int(entity.get("source_image_count") or 0) > 0
        line_level = line_priority(entity)
        score = (1000 if is_us else 0) + (100 if has_images else 0) + line_level * 10 + status_need[entity["site_status"]]
        queue.append({
            "formation_id": entity["formation_id"],
            "date_iso": entity.get("date_iso", ""),
            "place": entity.get("place", ""),
            "region": entity.get("region", ""),
            "country_code": entity.get("country_code", ""),
            "site_status": entity["site_status"],
            "us_priority": "yes" if is_us else "no",
            "has_source_images": "yes" if has_images else "no",
            "source_image_count": entity.get("source_image_count", 0),
            "line_priority": line_level,
            "priority_score": score,
            "next_action": next_location_action(entity, has_images, line_level),
        })
    queue.sort(key=lambda row: (-int(row["priority_score"]), str(row["formation_id"])))
    for rank, row in enumerate(queue, 1):
        row["priority_rank"] = rank
    return queue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    pdf_rows, page_count = parse_pdf(args.pdf)
    web_rows = parse_cropcirclecenter()
    iccra_rows = load_iccra_full()
    iccra_mode = "exhaustive_reconciled" if iccra_rows is not None else "legacy_year_pages"
    if iccra_rows is None:
        iccra_rows = parse_iccra()
    expansion_rows = load_source_expansion()
    commons_event_rows = load_commons_event_assertions()
    assertions = pdf_rows + web_rows + iccra_rows + expansion_rows + commons_event_rows
    assertion_ids = [row["assertion_id"] for row in assertions]
    if len(assertion_ids) != len(set(assertion_ids)):
        raise ValueError("Assertion IDs are not globally unique after source expansion")
    geonames_index = load_geonames()
    entities = build_entities(assertions, geonames_index)
    formation_alias_reviews = load_formation_alias_reviews()
    entities = apply_formation_alias_reviews(entities, formation_alias_reviews)
    apply_complete_source_image_counts(entities, assertions)
    curated_site_resolutions = load_site_resolutions()
    global_source_site_resolutions = load_global_source_site_resolutions()
    site_resolutions = {
        **global_source_site_resolutions,
        **curated_site_resolutions,
    }
    site_status_counts = apply_site_resolutions(entities, site_resolutions)
    straight_counts = apply_straight_component_enrichment(entities)
    image_straight_counts = apply_iccra_image_straight_enrichment(entities)
    orientation_counts = apply_orientation_status(entities)
    image_straight_metrics = load_optional_json(ROOT / "outputs" / "straight-components" / "iccra_image_metrics.json")
    location_work_queue = build_location_work_queue(entities)
    write_csv(ROOT / "data" / "source_assertions.csv", assertions)
    write_csv(ROOT / "data" / "formations.csv", entities)
    write_csv(ROOT / "data" / "location_work_queue.csv", location_work_queue)
    write_formation_index(ROOT / "web" / "data" / "formation_index.json", entities)
    write_geojson(ROOT / "web" / "data" / "formations.geojson", entities, "canonical")
    write_geojson(ROOT / "web" / "data" / "formation_sites.geojson", entities, "site")
    write_geojson(ROOT / "web" / "data" / "locality_references.geojson", entities, "locality")
    pdf_hash = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "pdf": {"path": str(args.pdf), "sha256": pdf_hash, "pages": page_count, "assertions": len(pdf_rows)},
        "assertions": {"total": len(assertions), "cropcirclecenter_pdf": len(pdf_rows),
                       "cropcirclecenter_web": len(web_rows), "iccra": len(iccra_rows),
                       "iccra_mode": iccra_mode, "source_expansion": len(expansion_rows),
                       "commons_open_event_assertions": len(commons_event_rows),
                       "source_expansion_by_source": dict(Counter(
                           row.get("expansion_source_id", "unknown") for row in expansion_rows))},
        "formations": len(entities),
        "formation_aliases": {
            "accepted_reviews": len(formation_alias_reviews),
            "merged_alias_entities": len(formation_alias_reviews),
        },
        "geocoded": sum(1 for row in entities if row["latitude"] != ""),
        "site_resolutions": {
            "reviewed_overrides": len(curated_site_resolutions),
            "global_source_map_candidates": len(global_source_site_resolutions),
            "combined_overrides": len(site_resolutions),
            "status_counts": dict(site_status_counts),
            "field_site_features": sum(1 for row in entities if row["site_status"] in FIELD_SITE_STATUSES),
            "locality_reference_features": site_status_counts["locality_reference"],
            "unresolved_formations": site_status_counts["unresolved"],
            "full_index_records": len(entities),
            "location_work_queue_rows": len(location_work_queue),
        },
        "us_formations": sum(1 for row in entities if row["country_code"] == "US"),
        "countries": len({row["country_code"] for row in entities if row["country_code"]}),
        "year_min": min(row["year"] for row in entities), "year_max": max(row["year"] for row in entities),
        "top_countries": Counter(row["country"] for row in entities).most_common(15),
        "straight_components": dict(straight_counts),
        "iccra_image_straight_review": dict(image_straight_counts),
        "reviewed_line_or_axis_formations": orientation_counts["qualified_formations"],
        "orientations": orientation_counts,
        "images": {
            "iccra_image_references": len(load_optional_csv(ROOT / "data" / "iccra_image_links.csv")),
            "formations_with_linked_images": sum(1 for row in entities if row["source_image_count"]),
            "iccra_straight_analysis": {
                "successfully_cached_hosted_rows": image_straight_metrics.get("successfully_cached_hosted_rows", 0),
                "analyzed_rows": image_straight_metrics.get("analyzed_rows", 0),
                "cached_row_coverage": image_straight_metrics.get("cached_row_coverage"),
                "unique_pixel_sha256_analyzed": image_straight_metrics.get("unique_pixel_sha256_analyzed", 0),
                "analysis_status_counts": image_straight_metrics.get("analysis_status_counts", {}),
                "tier_counts_by_inventory_row": image_straight_metrics.get("tier_counts_by_inventory_row", {}),
            },
            "public_overlays": 0,
        },
    }
    (ROOT / "data" / "build_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
