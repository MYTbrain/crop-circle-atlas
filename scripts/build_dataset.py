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
            links = span.xpath('.//a[contains(@href,"ccdata")] | ancestor::a[contains(@href,"ccdata")]')
            if not links:
                continue
            link = links[0]
            href = link.get("href", "")
            record_url = urljoin(page_url, href)
            if not href:
                continue
            ordinal += 1
            location = clean_text(" ".join(span.itertext()))
            place, region = (location.split("|", 1) + [""])[:2]
            place, region = clean_text(place), clean_text(region)
            tr = link
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
            crop = values[2] if len(values) > 2 else ""
            size_text = values[3] if len(values) > 3 else ""
            img = tr.xpath('.//img[@src]') if tr is not None else []
            thumbnail_url = urljoin(page_url, img[0].get("src")) if img else ""
            rows.append({
                "assertion_id": assertion_id("cropcirclecenter_web", record_url, ordinal),
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
    pool = region_matches or candidates
    best = max(pool, key=lambda c: c["population"])
    confidence = 0.72 if region_matches and norm(variant) == norm(raw_place) else 0.62 if norm(variant) == norm(raw_place) else 0.48
    return {**best, "geocode_method": "geonames_locality_centroid", "geocode_confidence": confidence,
            "coordinate_uncertainty_km": 5 if confidence >= 0.7 else 15 if confidence >= 0.6 else 30}


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
                "coordinate_uncertainty_km": "", "geoname_id": "", "source_count": 0,
                "source_names": [], "source_urls": [], "assertion_ids": [],
                "has_straight_component": "unknown", "orientation_status": "not_reviewed",
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
    result = []
    for key in order:
        entity = entities[key]
        entity["source_names"] = "; ".join(sorted(set(entity["source_names"])))
        entity["source_urls"] = "; ".join(dict.fromkeys(entity["source_urls"]))
        entity["assertion_ids"] = "; ".join(entity["assertion_ids"])
        entity["source_count"] = len(entity["assertion_ids"].split("; "))
        geo = geocode(entity, geonames_index)
        if geo:
            for field in ("latitude", "longitude", "geocode_method", "geocode_confidence", "coordinate_uncertainty_km", "geoname_id"):
                entity[field] = geo[field]
        result.append(entity)
    return result


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
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
            "geocode_confidence", "source_count", "source_names", "source_urls", "orientation_status")}
        features.append({"type":"Feature", "geometry":{"type":"Point", "coordinates":[row["longitude"], row["latitude"]]}, "properties":properties})
    payload = {"type":"FeatureCollection", "features":features,
               "metadata":{"generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                           "coordinate_notice":"Approximate locality centroids; not field coordinates."}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    pdf_rows, page_count = parse_pdf(args.pdf)
    web_rows = parse_cropcirclecenter()
    iccra_rows = parse_iccra()
    assertions = pdf_rows + web_rows + iccra_rows
    geonames_index = load_geonames()
    entities = build_entities(assertions, geonames_index)
    write_csv(ROOT / "data" / "source_assertions.csv", assertions)
    write_csv(ROOT / "data" / "formations.csv", entities)
    write_geojson(ROOT / "web" / "data" / "formations.geojson", entities)
    pdf_hash = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "pdf": {"path": str(args.pdf), "sha256": pdf_hash, "pages": page_count, "assertions": len(pdf_rows)},
        "assertions": {"total": len(assertions), "cropcirclecenter_pdf": len(pdf_rows),
                       "cropcirclecenter_web": len(web_rows), "iccra": len(iccra_rows)},
        "formations": len(entities),
        "geocoded": sum(1 for row in entities if row["latitude"] != ""),
        "us_formations": sum(1 for row in entities if row["country_code"] == "US"),
        "countries": len({row["country_code"] for row in entities if row["country_code"]}),
        "year_min": min(row["year"] for row in entities), "year_max": max(row["year"] for row in entities),
        "top_countries": Counter(row["country"] for row in entities).most_common(15),
    }
    (ROOT / "data" / "build_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
