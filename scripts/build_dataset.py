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


def write_geojson(path: Path, entities):
    features = []
    for row in entities:
        if row["latitude"] == "" or row["longitude"] == "":
            continue
        properties = {k: row[k] for k in (
            "formation_id", "date_iso", "date_precision", "year", "place", "region", "country",
            "country_code", "county", "crop", "classification", "coordinate_uncertainty_km",
            "geocode_method", "geocode_admin1", "geocode_confidence", "source_count", "source_names", "source_urls", "has_straight_component",
            "straight_component_tier", "straight_detector_score", "straight_candidate_id",
            "diagram_angle_deg", "diagram_angle_uncertainty_deg", "diagram_angle_reference",
            "straight_review_status", "orientation_status", "source_image_count", "has_source_images",
            "source_image_straight_status", "source_image_straight_tier", "source_image_straight_score",
            "source_image_straight_candidate_id", "source_image_axis_deg",
            "source_image_axis_uncertainty_deg", "source_image_axis_reference",
            "source_image_analysis_count", "source_image_candidate_count",
            "source_image_straight_caveat")}
        features.append({"type":"Feature", "geometry":{"type":"Point", "coordinates":[row["longitude"], row["latitude"]]}, "properties":properties})
    method_counts = Counter(row["geocode_method"] for row in entities if row["latitude"] != "")
    payload = {"type":"FeatureCollection", "features":features,
               "metadata":{"generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                           "coordinate_notice":"Coordinates mix source-reported field positions and approximate locality centroids. Inspect geocode_method and coordinate_uncertainty_km before spatial analysis.",
                           "coordinate_methods":dict(method_counts)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


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
    assertions = pdf_rows + web_rows + iccra_rows + expansion_rows
    assertion_ids = [row["assertion_id"] for row in assertions]
    if len(assertion_ids) != len(set(assertion_ids)):
        raise ValueError("Assertion IDs are not globally unique after source expansion")
    geonames_index = load_geonames()
    entities = build_entities(assertions, geonames_index)
    straight_counts = apply_straight_component_enrichment(entities)
    image_straight_counts = apply_iccra_image_straight_enrichment(entities)
    orientation_counts = apply_orientation_status(entities)
    image_straight_metrics = load_optional_json(ROOT / "outputs" / "straight-components" / "iccra_image_metrics.json")
    write_csv(ROOT / "data" / "source_assertions.csv", assertions)
    write_csv(ROOT / "data" / "formations.csv", entities)
    write_geojson(ROOT / "web" / "data" / "formations.geojson", entities)
    pdf_hash = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "pdf": {"path": str(args.pdf), "sha256": pdf_hash, "pages": page_count, "assertions": len(pdf_rows)},
        "assertions": {"total": len(assertions), "cropcirclecenter_pdf": len(pdf_rows),
                       "cropcirclecenter_web": len(web_rows), "iccra": len(iccra_rows),
                       "iccra_mode": iccra_mode, "source_expansion": len(expansion_rows),
                       "source_expansion_by_source": dict(Counter(
                           row.get("expansion_source_id", "unknown") for row in expansion_rows))},
        "formations": len(entities),
        "geocoded": sum(1 for row in entities if row["latitude"] != ""),
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
