from __future__ import annotations

"""Bounded, metadata-only expansion crawl for public crop-circle indexes.

The crawler deliberately downloads HTML only.  It never follows image links,
membership links, search endpoints, or APIs.  Every request is checked against
the site's robots policy (a missing robots.txt is recorded rather than silently
treated as an affirmative permission statement), rate limited, hashed, and
listed in the crawl manifest.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from lxml import html


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "source_expansion"
DATA = ROOT / "data"
USER_AGENT = "CropCircleAtlas/0.1 (+public metadata research catalog)"
PARSER_VERSION = "source-expansion-v1"

MONTHS = {
    "january": 1, "jan": 1, "januari": 1,
    "february": 2, "feb": 2, "februari": 2,
    "march": 3, "mar": 3, "maart": 3,
    "april": 4, "apr": 4,
    "may": 5, "mei": 5,
    "june": 6, "jun": 6, "juni": 6,
    "july": 7, "jul": 7, "juli": 7,
    "august": 8, "aug": 8, "augustus": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

COUNTRIES = {
    "argentina": ("Argentina", "AR"),
    "australia": ("Australia", "AU"),
    "austria": ("Austria", "AT"),
    "belgium": ("Belgium", "BE"),
    "brazil": ("Brazil", "BR"),
    "bulgaria": ("Bulgaria", "BG"),
    "canada": ("Canada", "CA"),
    "croatia": ("Croatia", "HR"),
    "czech republic": ("Czechia", "CZ"),
    "czechia": ("Czechia", "CZ"),
    "denmark": ("Denmark", "DK"),
    "england": ("England", "GB"),
    "france": ("France", "FR"),
    "germany": ("Germany", "DE"),
    "holland": ("Netherlands", "NL"),
    "hungary": ("Hungary", "HU"),
    "italy": ("Italy", "IT"),
    "mexico": ("Mexico", "MX"),
    "netherlands": ("Netherlands", "NL"),
    "the netherlands": ("Netherlands", "NL"),
    "new zealand": ("New Zealand", "NZ"),
    "norway": ("Norway", "NO"),
    "poland": ("Poland", "PL"),
    "portugal": ("Portugal", "PT"),
    "romania": ("Romania", "RO"),
    "russia": ("Russia", "RU"),
    "scotland": ("Scotland", "GB"),
    "serbia": ("Serbia", "RS"),
    "slovakia": ("Slovakia", "SK"),
    "slovenia": ("Slovenia", "SI"),
    "spain": ("Spain", "ES"),
    "sweden": ("Sweden", "SE"),
    "switzerland": ("Switzerland", "CH"),
    "uk": ("England", "GB"),
    "u.k.": ("England", "GB"),
    "united kingdom": ("England", "GB"),
    "united states": ("United States", "US"),
    "usa": ("United States", "US"),
    "u.s.a.": ("United States", "US"),
    "wales": ("Wales", "GB"),
}

ENGLISH_COUNTIES = {
    "bedfordshire", "berkshire", "buckinghamshire", "cambridgeshire",
    "cheshire", "cornwall", "cumbria", "derbyshire", "devon", "dorset",
    "durham", "east sussex", "essex", "gloucestershire", "hampshire",
    "herefordshire", "hertfordshire", "kent", "lancashire", "leicestershire",
    "lincolnshire", "norfolk", "northamptonshire", "northumberland",
    "nottinghamshire", "oxfordshire", "shropshire", "somerset", "staffordshire",
    "suffolk", "surrey", "warwickshire", "west sussex", "wiltshire",
    "worcestershire", "yorkshire",
}

CANADIAN_PROVINCES = {
    "alberta", "british columbia", "manitoba", "new brunswick",
    "newfoundland and labrador", "nova scotia", "ontario", "prince edward island",
    "quebec", "saskatchewan",
}

US_REGIONS = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
}

GERMAN_REGIONS = {"bavaria", "brandenburg", "hesse", "saxony", "thuringia"}


SOURCES = {
    "connector": {
        "name": "Crop Circle Connector",
        "root": "https://cropcircleconnector.com/",
        "robots": "https://cropcircleconnector.com/robots.txt",
        "terms": "https://cropcircleconnector.com/anasazi/ImageUsePolicy2004.html",
        "rights": "metadata_only_no_images; contributor image rights retained",
    },
    "dcca": {
        "name": "Dutch Crop Circle Archive",
        "root": "https://www.dcca.nl/dcca.htm",
        "robots": "https://www.dcca.nl/robots.txt",
        "terms": "https://www.dcca.nl/dcca.htm",
        "rights": "metadata_only_with_source_attribution; publication particulars require contact",
    },
    "cccrn": {
        "name": "Canadian Crop Circle Research Network mirror",
        "root": "https://www.ufobc.ca/Supernatural/Cropcircles/cccrnnews.htm",
        "robots": "https://www.ufobc.ca/robots.txt",
        "terms": "https://www.ufobc.ca/Supernatural/Cropcircles/cccrnnews.htm",
        "rights": "metadata_only; mirrored newsletter copyright not assumed transferable",
    },
    "vigay": {
        "name": "Paul Vigay Crop Circle Research",
        "root": "https://www.vigay.com/cropcircles/articles/index.html",
        "robots": "https://www.vigay.com/robots.txt",
        "terms": "https://www.vigay.com/site/copyright.html",
        "rights": "field-report index metadata only; articles and images not redistributed",
    },
    "blt": {
        "name": "BLT Research",
        "root": "https://www.bltresearch.com/labreports.php",
        "robots": "https://www.bltresearch.com/robots.txt",
        "terms": "https://www.bltresearch.com/labreports.php",
        "rights": "lab-report citation metadata only; reports and images not redistributed",
    },
}


def clean_text(value: str) -> str:
    value = (value or "").replace("\xa0", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", value).strip()


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", clean_text(value).lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def stable_id(source_id: str, record_url: str, date_iso: str, listing_text: str) -> str:
    material = "|".join((source_id, record_url, date_iso, clean_text(listing_text)))
    return f"sx_{source_id}_{hashlib.sha1(material.encode('utf-8')).hexdigest()[:16]}"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not fieldnames:
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass
class Response:
    status: int
    body: bytes
    content_type: str
    error: str = ""


def request(url: str) -> Response:
    urllib_error = ""
    if os.name != "nt":
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return Response(int(response.status), response.read(), response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as exc:
            return Response(int(exc.code), b"", exc.headers.get("Content-Type", "") if exc.headers else "", str(exc))
        except Exception as exc:
            urllib_error = f"{type(exc).__name__}: {exc}"
    curl = shutil.which("curl.exe" if os.name == "nt" else "curl")
    if not curl:
        return Response(-1, b"", "", urllib_error)
    marker = b"\n__CCA_CURL_META__"
    command = [curl]
    if os.name == "nt":
        # Schannel's certificate verification remains enabled; this only avoids
        # an unavailable revocation endpoint in some managed Windows runtimes.
        command.append("--ssl-no-revoke")
    command.extend([
        "-L", "--max-time", "30", "--compressed", "-sS",
        "-A", USER_AGENT, "-H", "Accept: text/html,text/plain;q=0.9",
        "-w", marker.decode() + "%{http_code}\t%{content_type}", url,
    ])
    result = subprocess.run(command, capture_output=True, check=False)
    if marker not in result.stdout:
        error = clean_text(result.stderr.decode("utf-8", errors="replace")) or urllib_error
        return Response(-1, b"", "", error)
    body, metadata = result.stdout.rsplit(marker, 1)
    fields = metadata.decode("utf-8", errors="replace").split("\t", 1)
    try:
        status = int(fields[0])
    except ValueError:
        status = -1
    content_type = fields[1] if len(fields) > 1 else ""
    error = clean_text(result.stderr.decode("utf-8", errors="replace"))
    return Response(status, body if status == 200 else b"", content_type, error)


def cache_path(source_id: str, url: str, content_type: str = "") -> Path:
    suffix = ".txt" if "text/plain" in content_type or url.endswith("robots.txt") else ".html"
    return RAW / source_id / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}{suffix}"


def cached_or_fetch(source_id: str, url: str, kind: str, *, refresh: bool, robots_decision: str) -> tuple[dict, bytes]:
    path = cache_path(source_id, url)
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if path.exists() and not refresh:
        body = path.read_bytes()
        response = Response(200, body, "text/plain" if path.suffix == ".txt" else "text/html")
        fetch_state = "cached"
    elif robots_decision != "allowed":
        response = Response(0, b"", "", f"not fetched: robots decision {robots_decision}")
        fetch_state = "not_requested"
    else:
        response = request(url)
        body = response.body
        if response.status == 200 and body:
            content_type = response.content_type.lower()
            if "text/html" not in content_type and "text/plain" not in content_type and not url.endswith(".htm") and not url.endswith(".html"):
                response = Response(0, b"", response.content_type, "non-HTML response rejected")
            else:
                path = cache_path(source_id, url, response.content_type)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
        fetch_state = "network"
    body = response.body
    row = {
        "source_id": source_id,
        "url": url,
        "fetch_kind": kind,
        "robots_decision": robots_decision,
        "http_status": response.status,
        "fetch_state": fetch_state,
        "retrieved_at": retrieved_at,
        "sha256": hashlib.sha256(body).hexdigest() if body else "",
        "bytes": len(body),
        "content_type": response.content_type,
        "cache_path": path.relative_to(ROOT).as_posix() if body and path.exists() else "",
        "error": response.error,
    }
    return row, body


def robots_policy(source_id: str, *, refresh: bool) -> tuple[dict, urllib.robotparser.RobotFileParser | None]:
    url = SOURCES[source_id]["robots"]
    path = cache_path(source_id, url, "text/plain")
    if path.exists() and not refresh:
        body = path.read_bytes()
        response = Response(200, body, "text/plain")
        state = "cached"
    else:
        response = request(url)
        body = response.body
        state = "network"
        if response.status == 200 and body:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
    parser = None
    if response.status == 200:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(url)
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        decision = "policy_loaded"
    elif response.status in {404, 410}:
        decision = "missing_no_declared_restrictions"
    else:
        decision = "unavailable_fail_closed"
    row = {
        "source_id": source_id,
        "url": url,
        "fetch_kind": "robots",
        "robots_decision": decision,
        "http_status": response.status,
        "fetch_state": state,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sha256": hashlib.sha256(body).hexdigest() if body else "",
        "bytes": len(body),
        "content_type": response.content_type,
        "cache_path": path.relative_to(ROOT).as_posix() if body and path.exists() else "",
        "error": response.error,
    }
    return row, parser


def can_fetch(policy_row: dict, parser: urllib.robotparser.RobotFileParser | None, url: str) -> str:
    status = int(policy_row["http_status"])
    if status == 200 and parser is not None:
        return "allowed" if parser.can_fetch(USER_AGENT, url) else "disallowed"
    if status in {404, 410}:
        return "allowed"
    return "robots_unavailable_fail_closed"


def html_links(body: bytes, base_url: str) -> list[tuple[str, str]]:
    if not body:
        return []
    try:
        doc = html.fromstring(body, base_url=base_url)
    except Exception:
        return []
    return [(urllib.parse.urljoin(base_url, anchor.get("href", "")), clean_text(" ".join(anchor.itertext())))
            for anchor in doc.xpath("//a[@href]")]


def run_fetch(*, refresh: bool = False, delay: float = 0.35) -> list[dict]:
    manifest: list[dict] = []
    policies: dict[str, tuple[dict, urllib.robotparser.RobotFileParser | None]] = {}
    for source_id in SOURCES:
        row, parser = robots_policy(source_id, refresh=refresh)
        manifest.append(row)
        policies[source_id] = (row, parser)
        if row["fetch_state"] == "network":
            time.sleep(delay)

    roots: dict[str, bytes] = {}
    for source_id, spec in SOURCES.items():
        policy_row, parser = policies[source_id]
        decision = can_fetch(policy_row, parser, spec["root"])
        row, body = cached_or_fetch(source_id, spec["root"], "root_index", refresh=refresh, robots_decision=decision)
        manifest.append(row)
        roots[source_id] = body
        if row["fetch_state"] == "network":
            time.sleep(delay)
        if spec["terms"] != spec["root"]:
            decision = can_fetch(policy_row, parser, spec["terms"])
            terms_row, _ = cached_or_fetch(source_id, spec["terms"], "terms", refresh=refresh, robots_decision=decision)
            manifest.append(terms_row)
            if terms_row["fetch_state"] == "network":
                time.sleep(delay)

    connector_urls: list[str] = []
    connector_roots: dict[int, bytes] = {}
    for year in range(2014, 2027):
        url = f"https://cropcircleconnector.com/{year}/{year}.html"
        policy_row, parser = policies["connector"]
        decision = can_fetch(policy_row, parser, url)
        row, body = cached_or_fetch("connector", url, "season_root", refresh=refresh, robots_decision=decision)
        manifest.append(row)
        connector_roots[year] = body
        if row["fetch_state"] == "network":
            time.sleep(delay)
        for linked, _ in html_links(body, url):
            parsed = urllib.parse.urlparse(linked)
            match = re.fullmatch(rf"/{year}/(?:April|May|June|July|August|September){year}\.html", parsed.path, re.I)
            if parsed.hostname in {"cropcircleconnector.com", "www.cropcircleconnector.com"} and match:
                connector_urls.append(linked.replace("http://", "https://").replace("www.cropcircleconnector.com", "cropcircleconnector.com"))
    for url in sorted(set(connector_urls)):
        policy_row, parser = policies["connector"]
        decision = can_fetch(policy_row, parser, url)
        row, _ = cached_or_fetch("connector", url, "season_event_index", refresh=refresh, robots_decision=decision)
        manifest.append(row)
        if row["fetch_state"] == "network":
            time.sleep(delay)

    dcca_urls = []
    for linked, _ in html_links(roots.get("dcca", b""), SOURCES["dcca"]["root"]):
        parsed = urllib.parse.urlparse(linked)
        if parsed.hostname in {"dcca.nl", "www.dcca.nl"} and re.fullmatch(r"/(?:19|20)\d{2}/[^/]+-uk\.htm", parsed.path, re.I):
            dcca_urls.append(linked.replace("http://", "https://"))
    for url in sorted(set(dcca_urls)):
        policy_row, parser = policies["dcca"]
        decision = can_fetch(policy_row, parser, url)
        row, _ = cached_or_fetch("dcca", url, "year_event_index", refresh=refresh, robots_decision=decision)
        manifest.append(row)
        if row["fetch_state"] == "network":
            time.sleep(delay)

    cccrn_urls = []
    for linked, _ in html_links(roots.get("cccrn", b""), SOURCES["cccrn"]["root"]):
        parsed = urllib.parse.urlparse(linked)
        if parsed.hostname in {"ufobc.ca", "www.ufobc.ca"} and re.fullmatch(r"/Supernatural/Cropcircles/cccrn[^/]+\.htm", parsed.path, re.I):
            if not parsed.path.lower().endswith("cccrnnews.htm"):
                cccrn_urls.append(linked.replace("http://", "https://"))
    for url in sorted(set(cccrn_urls)):
        policy_row, parser = policies["cccrn"]
        decision = can_fetch(policy_row, parser, url)
        row, _ = cached_or_fetch("cccrn", url, "newsletter_detail", refresh=refresh, robots_decision=decision)
        manifest.append(row)
        if row["fetch_state"] == "network":
            time.sleep(delay)

    manifest.sort(key=lambda row: (row["source_id"], row["fetch_kind"], row["url"]))
    write_csv(DATA / "source_expansion_crawl_manifest.csv", manifest)
    return manifest


def assertion_template(source_id: str, source_url: str, record_url: str, slot: int,
                       year: int, month: int | str, day: int | str, date_iso: str,
                       precision: str, place: str, region: str, country: str,
                       country_code: str, listing_text: str) -> dict:
    return {
        "assertion_id": stable_id(source_id, record_url, date_iso, listing_text),
        "source_name": SOURCES[source_id]["name"],
        "source_url": source_url,
        "source_record_url": record_url,
        "retrieved_at": "2026-07-21",
        "source_page": source_url,
        "source_slot": slot,
        "year": year,
        "month": month,
        "day": day,
        "date_iso": date_iso,
        "date_precision": precision,
        "date_qualifier": "",
        "place": clean_text(place),
        "region": clean_text(region),
        "country": country,
        "country_code": country_code,
        "county": "",
        "crop": "",
        "size_text": "",
        "classification": "unreviewed",
        "thumbnail_url": "",
        "notes": "Metadata-only index assertion; source images and article text are not redistributed.",
        "expansion_source_id": source_id,
        "source_listing_text": clean_text(listing_text),
        "alternate_place": "",
        "canonical_match_status": "unreconciled",
        "matched_baseline_assertion_id": "",
        "rights_scope": SOURCES[source_id]["rights"],
        "parser_version": PARSER_VERSION,
    }


def country_from_parts(parts: list[str], default_country: str = "England", default_code: str = "GB") -> tuple[str, str, str, str, list[str]]:
    cleaned = [clean_text(part).strip(" .") for part in parts if clean_text(part).strip(" .")]
    if not cleaned:
        return "", "", default_country, default_code, []
    last_norm = norm(cleaned[-1])
    explicit_country = False
    if last_norm in COUNTRIES:
        country, code = COUNTRIES[last_norm]
        cleaned.pop()
        explicit_country = True
    elif last_norm.endswith(" holland"):
        country, code = "Netherlands", "NL"
        if len(cleaned) == 1:
            cleaned[0] = re.sub(r"\s+(?:the\s+)?holland$", "", cleaned[0], flags=re.I).strip()
        explicit_country = True
    elif any(last_norm.endswith(" " + alias) for alias in COUNTRIES):
        alias = max((alias for alias in COUNTRIES if last_norm.endswith(" " + alias)), key=len)
        country, code = COUNTRIES[alias]
        original_last = cleaned[-1]
        remainder = re.sub(r"\s+" + re.escape(alias) + r"$", "", original_last, flags=re.I).strip()
        if norm(remainder) in {"lower", "upper", "northern", "southern", "eastern", "western", "central"}:
            cleaned[-1] = original_last
        elif norm(remainder) in {"in", "near", "nr"}:
            cleaned.pop()
        else:
            cleaned[-1] = remainder
        explicit_country = True
    elif last_norm in ENGLISH_COUNTIES:
        country, code = "England", "GB"
    elif last_norm in CANADIAN_PROVINCES:
        country, code = "Canada", "CA"
    elif last_norm in US_REGIONS:
        country, code = "United States", "US"
    else:
        country, code = default_country, default_code
    if not cleaned:
        return "", "", country, code, []
    region = cleaned[-1] if len(cleaned) >= 2 else ""
    place = cleaned[0]
    middle = cleaned[1:-1] if len(cleaned) >= 2 else []
    if explicit_country and len(cleaned) == 1 and code == "DE":
        for state in GERMAN_REGIONS:
            if norm(place).endswith(" " + state):
                place = re.sub(r"\s+" + re.escape(state) + r"$", "", place, flags=re.I).strip()
                region = state.title()
                break
    if explicit_country and region and re.match(r"^(?:nr\.?|near)\s+", region, re.I):
        middle.append(region)
        region = ""
    return place, region, country, code, middle


CONNECTOR_DATE_RE = re.compile(
    r"\b(?:reported|discovered|found)\s+(?:on\s+)?"
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:\s*/\s*(\d{1,2})(?:st|nd|rd|th)?)?\s+"
    r"([A-Za-z]+)(?:\s+(\d{4}))?\b",
    re.I,
)
CONNECTOR_QUALIFIED_DATE_RE = re.compile(
    r"\b(?:reported|discovered|found)\s+"
    r"(?:(early|mid|late|end\s+of|at\s+the\s+end\s+of)\s+)?([A-Za-z]+)\b",
    re.I,
)


def connector_month(token: str, page_url: str) -> int | None:
    token = token.lower()
    if token in MONTHS:
        return MONTHS[token]
    english = {name: value for name, value in MONTHS.items() if len(name) > 3 and name not in {"januari", "februari", "maart", "mei", "juni", "juli", "augustus", "oktober"}}
    candidates = {value for name, value in english.items() if name.startswith(token)}
    page_name = Path(urllib.parse.urlparse(page_url).path).name.lower()
    page_candidates = {value for name, value in english.items() if page_name.startswith(name)}
    if len(candidates) == 1:
        return next(iter(candidates))
    if len(candidates & page_candidates) == 1:
        return next(iter(candidates & page_candidates))
    return None


def parse_connector_page(body: bytes, page_url: str) -> list[dict]:
    year_match = re.search(r"/(20\d{2})/", page_url)
    if not body or not year_match:
        return []
    page_year = int(year_match.group(1))
    doc = html.fromstring(body, base_url=page_url)
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    slot = 0
    for anchor in doc.xpath("//a[@href]"):
        listing = clean_text(" ".join(anchor.itertext()))
        match_text = re.sub(r"\bReported\s+Reported\b", "Reported", listing, flags=re.I)
        match = CONNECTOR_DATE_RE.search(match_text)
        qualified_match = None if match else CONNECTOR_QUALIFIED_DATE_RE.search(match_text)
        if not match and not qualified_match:
            continue
        if match:
            day = int(match.group(1))
            range_end = int(match.group(2)) if match.group(2) else None
            month = connector_month(match.group(3), page_url)
            year = int(match.group(4) or page_year)
            precision = "day_range" if range_end else "day"
            qualifier = f"{day}-{range_end}" if range_end else ""
            date_match = match
        else:
            qualifier = clean_text(qualified_match.group(1) or "").lower().replace("at the ", "")
            month = connector_month(qualified_match.group(2), page_url)
            year = page_year
            day = ""
            range_end = None
            precision = "qualified" if qualifier else "month"
            date_match = qualified_match
        if not month or year != page_year or (day != "" and not 1 <= day <= 31) or (range_end and not day <= range_end <= 31):
            continue
        record_url = urllib.parse.urljoin(page_url, anchor.get("href", ""))
        parsed_url = urllib.parse.urlparse(record_url)
        if parsed_url.hostname not in {"cropcircleconnector.com", "www.cropcircleconnector.com"}:
            continue
        location = match_text[:date_match.start()].strip(" .,:;-–")
        parts = [clean_text(part) for part in re.split(r",|\.(?=\s+[A-ZÀ-Ý])", location)]
        place, region, country, code, middle = country_from_parts(parts)
        alternatives = []
        for item in middle:
            county_match = re.search(r"\b(" + "|".join(re.escape(name) for name in sorted(ENGLISH_COUNTIES, key=len, reverse=True)) + r")$", item, re.I)
            if county_match and not region:
                region = county_match.group(1).title()
                item = item[:county_match.start()].strip(" ,")
            near = re.sub(r"^(?:nr\.?|near)\s+", "", item, flags=re.I).strip()
            if near and near != item:
                alternatives.append(near)
        embedded_near = re.search(r"\b(?:nr\.?|near)\s+(.+)$", place, re.I)
        if embedded_near:
            alternatives.append(embedded_near.group(1).strip())
            place = place[:embedded_near.start()].strip(" ,")
        if not place:
            continue
        date_iso = f"{year:04d}-{month:02d}-{day:02d}" if day != "" else f"{year:04d}-{month:02d}"
        dedupe = (record_url, date_iso)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        slot += 1
        row = assertion_template("connector", page_url, record_url, slot, year, month, day,
                                 date_iso, precision, place, region, country, code, listing)
        row["date_qualifier"] = qualifier
        row["alternate_place"] = "; ".join(dict.fromkeys(alternatives))
        rows.append(row)
    return rows


def parse_dcca_date(text: str, page_year: int) -> tuple[int, int, int | str, str, str] | None:
    text = clean_text(text).strip(" .")
    numeric = re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{4})", text)
    if numeric:
        day, month, year = map(int, numeric.groups())
        if year == page_year and 1 <= month <= 12 and 1 <= day <= 31:
            return year, month, day, f"{year:04d}-{month:02d}-{day:02d}", "day"
        return None
    named = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", text)
    if named and named.group(1).lower() in MONTHS and int(named.group(2)) == page_year:
        month, year = MONTHS[named.group(1).lower()], int(named.group(2))
        return year, month, "", f"{year:04d}-{month:02d}", "month"
    return None


def parse_dcca_page(body: bytes, page_url: str) -> list[dict]:
    year_match = re.search(r"/((?:19|20)\d{2})/", page_url)
    if not body or not year_match:
        return []
    page_year = int(year_match.group(1))
    doc = html.fromstring(body, base_url=page_url)
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    slot = 0
    for anchor in doc.xpath("//a[@href]"):
        listing = clean_text(" ".join(anchor.itertext())).strip(" .")
        parts = [clean_text(part) for part in listing.split(",")]
        country, code = "Netherlands", "NL"
        if len(parts) >= 3:
            date_text = parts[-1]
            place = parts[0].strip()
            region = parts[1].strip()
        else:
            compact = re.fullmatch(r"(.+?)\s+(\d{1,2}-\d{1,2}-\d{4})", listing)
            if not compact:
                continue
            place, date_text = compact.group(1).strip(), compact.group(2)
            region = ""
            if re.search(r"\(D\)$", place, re.I):
                country, code = "Germany", "DE"
        parsed_date = parse_dcca_date(date_text, page_year)
        if not parsed_date:
            continue
        year, month, day, date_iso, precision = parsed_date
        record_url = urllib.parse.urljoin(page_url, anchor.get("href", ""))
        parsed_url = urllib.parse.urlparse(record_url)
        if parsed_url.scheme not in {"http", "https"} or not place:
            continue
        dedupe = (record_url, date_iso)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        slot += 1
        row = assertion_template("dcca", page_url, record_url, slot, year, month, day,
                                 date_iso, precision, place, region, country, code, listing)
        rows.append(row)
    return rows


VIGAY_DATE_RE = re.compile(r":\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})(?:\s*\([^)]*\))?\s*$", re.I)


def parse_vigay_index(body: bytes, page_url: str) -> list[dict]:
    if not body:
        return []
    doc = html.fromstring(body, base_url=page_url)
    rows: list[dict] = []
    slot = 0
    for anchor in doc.xpath("//a[@href]"):
        context = anchor
        while context.getparent() is not None and str(context.tag).lower() != "tr":
            context = context.getparent()
        listing = clean_text(" ".join(context.itertext()))
        match = VIGAY_DATE_RE.search(listing)
        href = anchor.get("href", "")
        record_code = clean_text(" ".join(anchor.itertext())).lower()
        if not match or not re.fullmatch(r"(?:uk|us|is)\d{4}[a-z]{2}", record_code):
            continue
        day, month_name, year = int(match.group(1)), match.group(2).lower(), int(match.group(3))
        month = MONTHS.get(month_name)
        if not month:
            continue
        description = listing[:match.start()].strip(" .")
        if description.lower().startswith(record_code):
            description = description[len(record_code):].strip(" :-")
        description = re.sub(r"\s+-\s+BLT Report\s*$", "", description, flags=re.I)
        parts = [clean_text(part) for part in description.split(",")]
        default_country = "United States" if record_code.startswith("us") else "Israel" if record_code.startswith("is") else "England"
        default_code = "US" if record_code.startswith("us") else "IL" if record_code.startswith("is") else "GB"
        place, region, country, code, _ = country_from_parts(parts, default_country, default_code)
        place = re.sub(r"\s+Formation(?:\s*\([^)]*\))?$", "", place, flags=re.I).strip()
        if norm(region) == "oregan":
            region = "Oregon"
        if record_code.startswith("is") and not region:
            # The index gives only an article-style country description, not a
            # usable event locality; keep it in the access inventory, not as a
            # fabricated place assertion.
            continue
        date_iso = f"{year:04d}-{month:02d}-{day:02d}"
        record_url = urllib.parse.urljoin(page_url, href)
        slot += 1
        rows.append(assertion_template("vigay", page_url, record_url, slot, year, month, day,
                                       date_iso, "day", place, region, country, code, listing))
    return rows


CCCRN_HEADER_RE = re.compile(r"Formation(?: Reports?)?\s*#?\s*([0-9]+(?:\s*[-,]\s*[0-9]+)*)\s*(?:\([^)]*\))?\s*[-–:]\s*([^\n]+)", re.I)
CCCRN_EXACT_DATE_RE = re.compile(
    r"(?:first\s+(?:found|seen)|found|discovered|occurred)\s+(?:by[^.]{0,80}?\s+on\s+|on\s+)?"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:,|\s)+(\d{4})",
    re.I,
)


def parse_cccrn_detail(body: bytes, page_url: str) -> list[dict]:
    """Emit only explicit, single-event reports with an occurrence date.

    Newsletter publication dates are not substituted for formation dates. Pages
    bundling multiple events without individual dates are retained in the crawl
    manifest but intentionally emit no assertions.
    """
    if not body:
        return []
    doc = html.fromstring(body, base_url=page_url)
    text = clean_text(" ".join(doc.itertext()))
    header = CCCRN_HEADER_RE.search(text)
    date_match = CCCRN_EXACT_DATE_RE.search(text)
    if not header or not date_match:
        return []
    report_numbers = re.findall(r"\d+", header.group(1))
    if len(report_numbers) != 1:
        return []
    location = clean_text(header.group(2)).split(" Paul Anderson", 1)[0].strip(" .")
    parts = [clean_text(part) for part in location.split(",")]
    place, region, country, code, _ = country_from_parts(parts, "Canada", "CA")
    if not place or not region:
        return []
    month = MONTHS[date_match.group(1).lower()]
    day, year = int(date_match.group(2)), int(date_match.group(3))
    date_iso = f"{year:04d}-{month:02d}-{day:02d}"
    listing = f"Formation Report #{report_numbers[0]} - {location}; occurrence date {date_iso}"
    return [assertion_template("cccrn", page_url, page_url, 1, year, month, day,
                               date_iso, "day", place, region, country, code, listing)]


def manifest_bodies(manifest: list[dict], source_id: str, kinds: set[str]) -> list[tuple[bytes, str]]:
    result = []
    for row in manifest:
        if row.get("source_id") != source_id or row.get("fetch_kind") not in kinds or str(row.get("http_status")) != "200":
            continue
        path_text = row.get("cache_path", "")
        if not path_text:
            continue
        path = ROOT / path_text
        if path.exists():
            result.append((path.read_bytes(), row["url"]))
    return result


PARSE_INPUT_KINDS = {
    ("connector", "season_event_index"),
    ("dcca", "year_event_index"),
    ("cccrn", "newsletter_detail"),
    ("vigay", "root_index"),
}


def validate_manifest_cache(manifest: list[dict]) -> None:
    """Fail closed before writes when private parse inputs are absent or changed."""
    cache_root = RAW.resolve()
    errors = []
    for row in manifest:
        if (row.get("source_id"), row.get("fetch_kind")) not in PARSE_INPUT_KINDS or str(row.get("http_status")) != "200":
            continue
        relative = row.get("cache_path", "")
        path = (ROOT / relative).resolve() if relative else None
        if path is None or not path.is_relative_to(cache_root):
            errors.append(f"unsafe_or_missing_cache_path:{row.get('url', '')}")
            continue
        if not path.is_file():
            errors.append(f"missing_cache_file:{relative}")
            continue
        body = path.read_bytes()
        try:
            expected_bytes = int(row.get("bytes") or -1)
        except (TypeError, ValueError):
            expected_bytes = -1
        actual_sha = hashlib.sha256(body).hexdigest()
        if len(body) != expected_bytes:
            errors.append(f"byte_count_mismatch:{relative}")
        if actual_sha != row.get("sha256", ""):
            errors.append(f"sha256_mismatch:{relative}")
    if errors:
        raise ValueError("Source-expansion private cache preflight failed; outputs were not changed: " + "; ".join(errors[:12]))


def entity_key(row: dict) -> tuple[str, str, str, str, str, str]:
    return (str(row.get("year", "")), str(row.get("month", "")), str(row.get("day", "")),
            norm(row.get("place", "")), norm(row.get("region", "")), row.get("country_code", ""))


def place_similarity(left: str, right: str) -> float:
    left_norm, right_norm = norm(left), norm(right)
    if not left_norm or not right_norm:
        return 0.0
    left_tokens, right_tokens = set(left_norm.split()), set(right_norm.split())
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return max(jaccard, SequenceMatcher(None, left_norm, right_norm).ratio())


def reconcile_rows(rows: list[dict], baseline: list[dict]) -> dict:
    baseline = [row for row in baseline if not row.get("expansion_source_id") and not row.get("assertion_id", "").startswith("sx_")]
    exact_index: dict[tuple, list[dict]] = defaultdict(list)
    date_region_index: dict[tuple, list[dict]] = defaultdict(list)
    date_country_index: dict[tuple, list[dict]] = defaultdict(list)
    for item in baseline:
        exact_index[entity_key(item)].append(item)
        date_region_index[(str(item.get("year", "")), str(item.get("month", "")), str(item.get("day", "")),
                           norm(item.get("region", "")), item.get("country_code", ""))].append(item)
        date_country_index[(str(item.get("year", "")), str(item.get("month", "")), str(item.get("day", "")),
                            item.get("country_code", ""))].append(item)

    for row in rows:
        matches = exact_index.get(entity_key(row), [])
        if matches:
            row["canonical_match_status"] = "exact_overlap"
            row["matched_baseline_assertion_id"] = matches[0].get("assertion_id", "")
            continue
        aliases = [item.strip() for item in row.get("alternate_place", "").split(";") if item.strip()]
        alias_match = None
        candidates = date_region_index.get((str(row["year"]), str(row.get("month", "")), str(row.get("day", "")),
                                            norm(row.get("region", "")), row.get("country_code", "")), [])
        broad_candidates = date_country_index.get((str(row["year"]), str(row.get("month", "")), str(row.get("day", "")),
                                                    row.get("country_code", "")), [])
        for alias in [row.get("place", ""), *aliases]:
            alias_matches = [item for item in candidates if norm(item.get("place", "")) == norm(alias)]
            if not alias_matches:
                alias_matches = [item for item in broad_candidates if norm(item.get("place", "")) == norm(alias)]
            if len({entity_key(item) for item in alias_matches}) == 1 and alias_matches:
                alias_match = alias_matches[0]
                break
        if alias_match:
            # This is evidence for later adjudication, never authority to
            # rewrite the source's own place or administrative geography.
            row["canonical_match_status"] = "alias_overlap_not_merged"
            row["matched_baseline_assertion_id"] = alias_match.get("assertion_id", "")
            continue
        fuzzy = [item for item in candidates if place_similarity(row.get("place", ""), item.get("place", "")) >= 0.72]
        if len({entity_key(item) for item in fuzzy}) == 1 and fuzzy:
            row["canonical_match_status"] = "probable_overlap_not_merged"
            row["matched_baseline_assertion_id"] = fuzzy[0].get("assertion_id", "")
        else:
            row["canonical_match_status"] = "new_exact_key"

    baseline_keys = set(exact_index)
    expansion_keys = {entity_key(row) for row in rows}
    per_source = {}
    for source_id in SOURCES:
        source_rows = [row for row in rows if row.get("expansion_source_id") == source_id]
        source_keys = {entity_key(row) for row in source_rows}
        per_source[source_id] = {
            "assertions": len(source_rows),
            "distinct_normalized_source_keys": len(source_keys),
            "exact_overlap_normalized_keys": len(source_keys & baseline_keys),
            "new_normalized_source_keys_vs_baseline": len(source_keys - baseline_keys),
            "exact_overlap_assertions": sum(row["canonical_match_status"] == "exact_overlap" for row in source_rows),
            "alias_overlap_not_merged_assertions": sum(row["canonical_match_status"] == "alias_overlap_not_merged" for row in source_rows),
            "probable_overlap_not_merged_assertions": sum(row["canonical_match_status"] == "probable_overlap_not_merged" for row in source_rows),
        }
    return {
        "baseline_assertions": len(baseline),
        "baseline_normalized_keys": len(baseline_keys),
        "expansion_assertions": len(rows),
        "expansion_distinct_normalized_source_keys": len(expansion_keys),
        "exact_overlap_normalized_keys": len(expansion_keys & baseline_keys),
        "new_normalized_source_keys_vs_baseline": len(expansion_keys - baseline_keys),
        "same_normalized_key_assertion_surplus": len(rows) - len(expansion_keys),
        "match_statuses": dict(Counter(row["canonical_match_status"] for row in rows)),
        "per_source": per_source,
    }


def access_rows(manifest: list[dict], assertions: list[dict]) -> list[dict]:
    by_source = defaultdict(list)
    for row in manifest:
        by_source[row["source_id"]].append(row)
    counts = Counter(row.get("expansion_source_id") for row in assertions)
    rows = []
    descriptions = {
        "connector": ("public 2014-2026 season event indexes", "event rows parsed", "membership archive and images excluded"),
        "dcca": ("public year tables linked from archive root", "event rows parsed", "only machine-enumerable dated anchors; no images"),
        "cccrn": ("public UFOBC newsletter mirror", "explicit single-event occurrence dates only", "newsletter date never substituted; multi-event undated pages excluded"),
        "vigay": ("public field-report index", "dated field-report rows parsed", "article corpus is descriptive/enrichment, not bulk events"),
        "blt": ("public lab-report page", "registered; no rows emitted in this run", "DNS unavailable to reproducible local fetch; reports are enrichment, not a complete event catalog"),
    }
    for source_id, spec in SOURCES.items():
        entries = by_source[source_id]
        robots = next((row for row in entries if row["fetch_kind"] == "robots"), {})
        successful = sum(str(row.get("http_status")) == "200" for row in entries)
        failed = sum(str(row.get("http_status")) != "200" for row in entries)
        scope, treatment, boundary = descriptions[source_id]
        rows.append({
            "source_id": source_id,
            "source_name": spec["name"],
            "root_url": spec["root"],
            "robots_url": spec["robots"],
            "robots_http_status": robots.get("http_status", ""),
            "robots_decision": robots.get("robots_decision", ""),
            "evaluated_scope": scope,
            "treatment": treatment,
            "access_boundary": boundary,
            "rights_action": spec["rights"],
            "successful_requests": successful,
            "failed_or_unavailable_requests": failed,
            "assertions_emitted": counts[source_id],
        })
    return rows


def parse_coverage(manifest: list[dict], assertions: list[dict]) -> tuple[list[dict], dict]:
    emitted = {(row["source_url"], row["source_record_url"]) for row in assertions}
    exclusions: list[dict] = []
    connector_candidates: set[tuple[str, str, str]] = set()
    for body, page_url in manifest_bodies(manifest, "connector", {"season_event_index"}):
        doc = html.fromstring(body, base_url=page_url)
        for anchor in doc.xpath("//a[@href]"):
            listing = clean_text(" ".join(anchor.itertext()))
            if not re.search(r"\b(?:reported|found|discovered)\b", listing, re.I):
                continue
            record_url = urllib.parse.urljoin(page_url, anchor.get("href", ""))
            if urllib.parse.urlparse(record_url).hostname not in {"cropcircleconnector.com", "www.cropcircleconnector.com"}:
                continue
            candidate = (page_url, record_url, listing)
            if candidate in connector_candidates:
                continue
            connector_candidates.add(candidate)
            if (page_url, record_url) in emitted:
                continue
            normalized = re.sub(r"\bReported\s+Reported\b", "Reported", listing, flags=re.I)
            has_date = bool(CONNECTOR_DATE_RE.search(normalized) or CONNECTOR_QUALIFIED_DATE_RE.search(normalized))
            exclusions.append({
                "source_id": "connector",
                "source_url": page_url,
                "source_record_url": record_url,
                "source_listing_text": listing,
                "exclusion_reason": "no_usable_locality" if has_date else "no_usable_occurrence_date",
            })

    dcca_candidates: set[tuple[str, str, str]] = set()
    for body, page_url in manifest_bodies(manifest, "dcca", {"year_event_index"}):
        doc = html.fromstring(body, base_url=page_url)
        for anchor in doc.xpath("//a[@href]"):
            listing = clean_text(" ".join(anchor.itertext())).strip(" .")
            if not re.search(r"\b\d{1,2}-\d{1,2}-(?:19|20)\d{2}\b", listing):
                continue
            record_url = urllib.parse.urljoin(page_url, anchor.get("href", ""))
            dcca_candidates.add((page_url, record_url, listing))
    coverage = {
        "connector_event_like_unique_anchors": len(connector_candidates),
        "connector_assertions_emitted": sum(row.get("expansion_source_id") == "connector" for row in assertions),
        "connector_explicit_exclusions": sum(row["source_id"] == "connector" for row in exclusions),
        "dcca_dated_unique_anchors": len(dcca_candidates),
        "dcca_assertions_emitted": sum(row.get("expansion_source_id") == "dcca" for row in assertions),
        "dcca_unparsed_dated_anchors": max(0, len(dcca_candidates) - sum(row.get("expansion_source_id") == "dcca" for row in assertions)),
    }
    return exclusions, coverage


def run_parse(manifest: list[dict] | None = None) -> tuple[list[dict], dict]:
    manifest = manifest or read_csv(DATA / "source_expansion_crawl_manifest.csv")
    validate_manifest_cache(manifest)
    rows: list[dict] = []
    for body, url in manifest_bodies(manifest, "connector", {"season_event_index"}):
        rows.extend(parse_connector_page(body, url))
    for body, url in manifest_bodies(manifest, "dcca", {"year_event_index"}):
        rows.extend(parse_dcca_page(body, url))
    for body, url in manifest_bodies(manifest, "cccrn", {"newsletter_detail"}):
        rows.extend(parse_cccrn_detail(body, url))
    for body, url in manifest_bodies(manifest, "vigay", {"root_index"}):
        rows.extend(parse_vigay_index(body, url))

    unique: dict[str, dict] = {}
    for row in rows:
        if row["assertion_id"] in unique and unique[row["assertion_id"]] != row:
            raise ValueError(f"Assertion ID collision: {row['assertion_id']}")
        unique[row["assertion_id"]] = row
    rows = sorted(unique.values(), key=lambda row: (row["year"], str(row["month"]), str(row["day"]), row["source_name"], row["assertion_id"]))
    baseline = read_csv(DATA / "source_assertions.csv")
    yield_summary = reconcile_rows(rows, baseline)
    write_csv(DATA / "source_expansion_assertions.csv", rows)
    access = access_rows(manifest, rows)
    write_csv(DATA / "source_expansion_access.csv", access)
    exclusions, coverage = parse_coverage(manifest, rows)
    write_csv(DATA / "source_expansion_parse_exclusions.csv", exclusions)

    reconciliation = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "parser_version": PARSER_VERSION,
        "scope_statement": "Bounded public metadata pass, not a claim of global exhaustiveness.",
        "crawl": {
            "manifest_rows": len(manifest),
            "successful_snapshots": sum(str(row.get("http_status")) == "200" for row in manifest),
            "failed_or_unavailable": sum(str(row.get("http_status")) != "200" for row in manifest),
            "images_downloaded": 0,
            "membership_or_api_requests": 0,
        },
        "yield": yield_summary,
        "parse_coverage": coverage,
        "access": {row["source_id"]: {
            "assertions_emitted": int(row["assertions_emitted"]),
            "robots_http_status": row["robots_http_status"],
            "robots_decision": row["robots_decision"],
            "access_boundary": row["access_boundary"],
            "rights_action": row["rights_action"],
        } for row in access},
        "completeness_checks": {
            "all_assertion_ids_unique": len(rows) == len({row["assertion_id"] for row in rows}),
            "all_rows_have_provenance": all(row["source_url"] and row["source_record_url"] and row["rights_scope"] for row in rows),
            "all_rows_have_valid_dates": all(str(row["date_iso"]).startswith(str(row["year"])) for row in rows),
            "no_image_urls_emitted": all(not row.get("thumbnail_url") and not row.get("image_urls") for row in rows),
            "bounded_scope_not_global_exhaustiveness": True,
        },
    }
    (DATA / "source_expansion_reconciliation.json").write_text(
        json.dumps(reconciliation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return rows, reconciliation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="refresh cached HTML within the same bounded scope")
    parser.add_argument("--parse-only", action="store_true", help="do not make network requests")
    parser.add_argument("--delay", type=float, default=0.35, help="seconds between network requests")
    args = parser.parse_args()
    manifest = None if args.parse_only else run_fetch(refresh=args.refresh, delay=max(args.delay, 0.2))
    rows, reconciliation = run_parse(manifest)
    print(json.dumps({"assertions": len(rows), **reconciliation["yield"], "per_source": reconciliation["yield"]["per_source"]}, indent=2))


if __name__ == "__main__":
    main()
