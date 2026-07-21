from __future__ import annotations

import csv
import hashlib
import html as html_module
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote_to_bytes, urljoin, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SNAPSHOT_PATH = DATA / "iccra_snapshots_full.csv"
EDGE_PATH = DATA / "iccra_crawl_edges_full.csv"
ASSERTION_PATH = DATA / "iccra_assertions_full.csv"
INDEX_ENTRY_PATH = DATA / "iccra_index_entries_full.csv"
IMAGE_LINK_PATH = DATA / "iccra_image_links.csv"
REPORT_LINK_PATH = DATA / "iccra_report_links_full.csv"
RECONCILIATION_PATH = DATA / "iccra_reconciliation.json"
RECONCILIATION_MD_PATH = ROOT / "docs" / "ICCRA_RECONCILIATION.md"

BY_YEAR_URL = "https://iccra.org/byyear/usaformations-byyear.htm"
BY_STATE_URL = "https://iccra.org/bystate/usaformations-bystate.htm"

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}
STATE_ABBR_BY_NAME = {name.casefold(): abbr for abbr, name in US_STATES.items()}

UI_IMAGE_NAMES = {
    "iccraheader", "line", "smcc", "bbcc", "mbcc",
    "spacer", "blank", "clear", "clearpixel",
}
IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|gif)(?:$|[?#])", re.I)


def clean_text(value: str) -> str:
    value = html_module.unescape(value or "")
    value = value.replace("\xa0", " ").replace("\u200b", " ")
    value = unicodedata.normalize("NFKC", value)
    if any(marker in value for marker in ("Ã", "Â", "â€", "â€™", "â€œ", "â€”", "â€“")):
        try:
            repaired = value.encode("cp1252").decode("utf-8")
            if repaired.count("�") <= value.count("�"):
                value = repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return re.sub(r"\s+", " ", value).strip()


def norm(value: str) -> str:
    value = clean_text(value).casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def decode_url_path(path: str) -> str:
    raw = unquote_to_bytes(path)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def url_match_key(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    host = parsed.hostname.casefold() if parsed.hostname else ""
    if host == "www.iccra.org":
        host = "iccra.org"
    path = decode_url_path(parsed.path).replace("\xa0", " ").replace("\ufffd", " ")
    path = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", path)).casefold()
    query = clean_text(parsed.query).casefold()
    return f"{host}{path}?{query}" if query else f"{host}{path}"


def resolve_url(base: str, href: str) -> str:
    if not href:
        return ""
    absolute = urljoin(base, html_module.unescape(href.strip()))
    parsed = urlsplit(absolute)
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = (parsed.hostname or "").casefold()
    if host == "www.iccra.org":
        host = "iccra.org"
    netloc = host
    if parsed.port and parsed.port not in {80, 443}:
        netloc += f":{parsed.port}"
    path = quote(parsed.path, safe="/%:@()[],+-_'~")
    scheme = "https" if host == "iccra.org" else parsed.scheme
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def is_iccra_url(url: str) -> bool:
    return (urlsplit(url).hostname or "").casefold() in {"iccra.org", "www.iccra.org"}


def decode_page(path: Path) -> str:
    raw = path.read_bytes()
    # Modern ICCRA pages are UTF-8 while older pages use Windows-1252. Prefer
    # strict UTF-8 and fall back only when the byte stream proves it is legacy.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


@dataclass
class Anchor:
    href: str
    text: str


@dataclass
class ListItem:
    text: str
    anchors: list[Anchor]


@dataclass
class ImageRef:
    src: str
    alt: str = ""
    title: str = ""
    width: str = ""
    height: str = ""
    reference_kind: str = "embedded"


class ArchiveHTML(HTMLParser):
    """Small, dependency-free extractor tolerant of ICCRA's legacy HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.anchors: list[Anchor] = []
        self.images: list[ImageRef] = []
        self.list_items: list[ListItem] = []
        self.blocks: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._li_text: list[str] | None = None
        self._li_anchors: list[Anchor] = []
        self._block_text: list[str] | None = None

    def _flush_li(self) -> None:
        if self._li_text is None:
            return
        text = clean_text(" ".join(self._li_text))
        if text:
            self.list_items.append(ListItem(text=text, anchors=list(self._li_anchors)))
        self._li_text = None
        self._li_anchors = []

    def _flush_block(self) -> None:
        if self._block_text is None:
            return
        text = clean_text(" ".join(self._block_text))
        if text:
            self.blocks.append(text)
        self._block_text = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        attr = {k.casefold(): (v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag == "li":
            # Many pages omit closing LI tags. A new LI deterministically closes
            # the prior record and prevents adjacent formations from merging.
            self._flush_li()
            self._li_text = []
            self._li_anchors = []
        if tag == "a":
            self._anchor_href = attr.get("href", "")
            self._anchor_text = []
        if tag == "img" and attr.get("src"):
            self.images.append(ImageRef(
                src=attr["src"], alt=clean_text(attr.get("alt", "")),
                title=clean_text(attr.get("title", "")), width=attr.get("width", ""),
                height=attr.get("height", ""), reference_kind="embedded",
            ))
        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_block()
            self._block_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.text_parts.append(data)
        if self._in_title:
            self.title_parts.append(data)
        if self._anchor_href is not None:
            self._anchor_text.append(data)
        if self._li_text is not None:
            self._li_text.append(data)
        if self._block_text is not None:
            self._block_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "noscript"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._anchor_href is not None:
            anchor = Anchor(self._anchor_href, clean_text(" ".join(self._anchor_text)))
            self.anchors.append(anchor)
            if self._li_text is not None:
                self._li_anchors.append(anchor)
            self._anchor_href = None
            self._anchor_text = []
        if tag == "li":
            self._flush_li()
        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_block()

    def close(self) -> None:
        self._flush_li()
        self._flush_block()
        super().close()

    @property
    def title(self) -> str:
        return clean_text(" ".join(self.title_parts))

    @property
    def text(self) -> str:
        return clean_text(" ".join(self.text_parts))


@dataclass
class Occurrence:
    index_kind: str
    index_url: str
    ordinal: int
    label: str
    record_url: str = ""
    state_abbr: str = ""
    expected_group_count: int | None = None
    record_aliases: list[str] = field(default_factory=list)
    parsed: dict[str, object] = field(default_factory=dict)


def parse_date_location(label: str, state_hint: str = "", year_hint: int | None = None) -> dict[str, object]:
    original = clean_text(label)
    text = original.replace("–", "-").replace("—", "-")
    location = text
    date_text = ""

    prefix = re.match(
        rf"^(?P<date>(?:(?:early|late|mid|spring|summer|fall|autumn|winter)\s+)?"
        rf"(?:(?:{MONTH_PATTERN})\.?\s*(?:-\s*(?:{MONTH_PATTERN})\.?)?\s*"
        rf"(?:\d{{1,2}}(?:\s*[-/]\s*\d{{1,2}})?\s*,?\s*)?)?"
        rf"(?:18|19|20)\d{{2}}(?:\??))\s*-\s*(?P<location>.+)$",
        text, re.I,
    )
    if prefix:
        date_text = clean_text(prefix.group("date"))
        location = clean_text(prefix.group("location"))
    else:
        suffix = re.match(r"^(?P<location>.+?)\s*\((?P<date>[^()]*(?:18|19|20)\d{2}[^()]*)\)\s*$", text)
        if suffix:
            location = clean_text(suffix.group("location"))
            date_text = clean_text(suffix.group("date"))

    numeric_suffix = re.match(
        r"^(?P<location>.+?)\s+(?P<month>\d{1,2})[-/](?P<day>\d{1,2}),?\s*(?P<year>(?:19|20)\d{2})$",
        location,
    )
    numeric_month = numeric_day = None
    if numeric_suffix:
        location = clean_text(numeric_suffix.group("location"))
        numeric_month = int(numeric_suffix.group("month"))
        numeric_day = int(numeric_suffix.group("day"))
        date_text = f"{numeric_month}/{numeric_day}/{numeric_suffix.group('year')}"

    year_match = re.search(r"\b(18|19|20)\d{2}\b", date_text or text)
    year = int(year_match.group(0)) if year_match else year_hint
    month = None
    for token, value in MONTHS.items():
        if re.search(rf"\b{re.escape(token)}\.?\b", date_text, re.I):
            month = value
            break
    if month is None and numeric_month and 1 <= numeric_month <= 12:
        month = numeric_month
    day = None
    if month:
        day_match = re.search(
            rf"\b(?:{MONTH_PATTERN})\.?\s*(\d{{1,2}})(?!\d)", date_text, re.I
        )
        if day_match and 1 <= int(day_match.group(1)) <= 31:
            day = int(day_match.group(1))
    if day is None and numeric_day and 1 <= numeric_day <= 31:
        day = numeric_day

    qualifier_tokens = re.findall(r"\b(early|late|mid|spring|summer|fall|autumn|winter|unknown|circa)\b", date_text, re.I)
    qualifier = " ".join(dict.fromkeys(x.casefold() for x in qualifier_tokens))
    if "?" in date_text:
        qualifier = clean_text((qualifier + " uncertain").strip())

    state_abbr = state_hint
    trailing = re.search(r",\s*([A-Z]{2})\s*$", location)
    if trailing and trailing.group(1) in US_STATES:
        state_abbr = trailing.group(1)
        location = clean_text(location[:trailing.start()])
    else:
        for state_name, abbr in STATE_ABBR_BY_NAME.items():
            if re.search(rf",?\s*{re.escape(state_name)}\s*$", location, re.I):
                state_abbr = abbr
                location = re.sub(rf",?\s*{re.escape(state_name)}\s*$", "", location, flags=re.I)
                break

    parts = [clean_text(part) for part in location.split(",") if clean_text(part)]
    county = ""
    county_index = None
    for index, part in enumerate(parts):
        if re.search(r"\b(county|parish|borough)\b", part, re.I):
            county = part
            county_index = index
            break
    if county_index is not None:
        place = ", ".join(parts[:county_index]) or county
    else:
        place = ", ".join(parts)

    if year and month and day:
        date_iso = f"{year:04d}-{month:02d}-{day:02d}"
        precision = "day"
    elif year and month:
        date_iso = f"{year:04d}-{month:02d}"
        precision = "month"
    elif year:
        date_iso = f"{year:04d}"
        precision = "year"
    else:
        date_iso = ""
        precision = "unknown"

    location_for_key = re.sub(r"\b(?:county|parish|borough)\b", "", location, flags=re.I)
    signature = ""
    if year and state_abbr and norm(location_for_key):
        signature = "|".join([
            str(year), state_abbr,
            str(month or 0), str(day or 0), norm(qualifier), norm(location_for_key),
        ])
    return {
        "year": year or "", "month": month or "", "day": day or "",
        "date_iso": date_iso, "date_precision": precision,
        "date_qualifier": qualifier, "date_text": date_text,
        "place": place, "county": county, "state_abbr": state_abbr,
        "region": US_STATES.get(state_abbr, state_abbr),
        "country": "Puerto Rico" if state_abbr == "PR" else "United States",
        "country_code": "PR" if state_abbr == "PR" else "US",
        "signature": signature, "location_text": location,
    }


def derive_record_label(
    record_url: str,
    anchor_label: str,
    detail_page: ArchiveHTML | None = None,
    year_hint: int | None = None,
) -> tuple[str, str]:
    """Recover a dated formation label from weak anchors such as ``here``."""
    label = clean_text(anchor_label)
    state_hint = ""
    usable_anchor = (
        label
        and not re.fullmatch(r"(?:18|19|20)\d{2}", label)
        and not re.fullmatch(r"(?i)(?:here\.?|learn more|view|photo gallery)", label)
        and not re.match(r"(?i)^https?://", label)
        and re.search(r"\b(?:18|19|20)\d{2}\b", label)
    )
    if usable_anchor:
        return label, state_hint

    decoded_path = decode_url_path(urlsplit(record_url).path)
    parts = [part for part in decoded_path.strip("/").split("/") if part]
    path_label = ""
    if parts:
        leaf = parts[-1]
        if leaf.casefold() in {"index.htm", "index.html"} and len(parts) >= 3:
            path_label = parts[-3] if parts[-2].casefold() == "photo gallery" else parts[-2]
        else:
            path_label = re.sub(r"(?i)\.(?:html?|pdf)$", "", leaf)

    candidates = []
    if detail_page and detail_page.title:
        candidates.append(detail_page.title)
    if path_label:
        candidates.append(path_label)
    if label:
        candidates.append(label)

    for candidate in candidates:
        candidate = clean_text(candidate.replace("_", " "))
        historical = re.search(
            r"(?i)reported crop circles from\s+((?:18|19|20)\d{2})\s*-\s*(.+)$",
            candidate,
        )
        if historical:
            return f"{historical.group(1)} - {clean_text(historical.group(2))}", state_hint

        prefix = re.match(
            r"(?i)^ICCRA(?:\s+Photo\s+Gallery)?(?:\s*-\s*|_|\s+)([A-Za-z ]{2,20})\s*-\s*(.+)$",
            candidate,
        )
        if prefix:
            state_token = clean_text(prefix.group(1))
            state_hint = (
                state_token.upper() if state_token.upper() in US_STATES
                else STATE_ABBR_BY_NAME.get(state_token.casefold(), "")
            )
            body = clean_text(prefix.group(2))
        else:
            body = re.sub(r"(?i)^ICCRA\s*-\s*", "", candidate).strip()

        # The gallery directory uses 9-13,2008 rather than a written month.
        numeric = re.search(r"\b(\d{1,2})[-/](\d{1,2}),?\s*((?:19|20)\d{2})\b", body)
        if numeric:
            month, day, year = map(int, numeric.groups())
            if 1 <= month <= 12 and 1 <= day <= 31:
                month_name = next(name.title() for name, number in MONTHS.items() if number == month and len(name) > 3)
                body = clean_text(
                    body[:numeric.start()] + f" ({month_name} {day}, {year})" + body[numeric.end():]
                )
        if re.search(r"\b(?:18|19|20)\d{2}\b", body):
            return body, state_hint
        if year_hint and body:
            return f"{body} ({year_hint})", state_hint

    return label or str(year_hint or ""), state_hint


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def context_windows(text: str, pattern: re.Pattern[str], radius: int = 180, limit: int = 8) -> list[str]:
    snippets: list[str] = []
    for match in pattern.finditer(text):
        start = max(0, match.start() - radius)
        end = min(len(text), match.end() + radius)
        snippet = clean_text(text[start:end]).strip(" -:;,.")
        if snippet and snippet not in snippets:
            snippets.append(snippet)
        if len(snippets) >= limit:
            break
    return snippets


COORDINATE_PATTERN = re.compile(
    r"(?i)(?:\bGPS\b|\bcoordinates?\b|\blat(?:itude)?\b|\blon(?:gitude)?\b|"
    r"\b\d{1,2}\s*[°ºo?]\s*\d{1,2}(?:\.\d+)?\s*(?:m|['′])?\s*[NS]\b|"
    r"\b\d{1,3}\s*[°ºo?]\s*\d{1,2}(?:\.\d+)?\s*(?:m|['′])?\s*[EW]\b)"
)
ORIENTATION_PATTERN = re.compile(
    r"(?i)(?:\bbearing\b|\bazimuth\b|\borient(?:ed|ation)?\b|\bcompass\b|"
    r"\btrue north\b|\bmagnetic north\b|"
    r"\b(?:line|axis|arm|point|ray|alignment|tramline)\b.{0,60}\b(?:north|south|east|west)\b|"
    r"\b(?:north|south|east|west)(?:ern|ward)?\b.{0,60}\b(?:line|axis|arm|point|ray|alignment|tramline)\b)"
)
RIGHTS_PATTERN = re.compile(
    r"(?i)(?:©|\bcopyright\b|\ball rights reserved\b|\bpermission\b|\bcourtesy\b|"
    r"\bphoto(?:graph)?\s+by\b|\bimage\s+by\b|\bcredit(?:ed)?\b|\breproduc(?:e|tion)\b)"
)


def extract_coordinate_pair(text: str) -> dict[str, object]:
    result: dict[str, object] = {
        "latitude": "", "longitude": "", "method": "", "uncertainty": "",
        "uncertainty_km": "", "confidence": "", "evidence": "",
    }
    decimal_lat = re.search(
        r"(?i)\blat(?:itude)?\b\s*[:=]?\s*([-+]?\d{1,2}(?:\.\d+)?)\s*"
        r"(?:degrees?|[°º])?\s*([NS])?",
        text,
    )
    decimal_lon = re.search(
        r"(?i)\blon(?:gitude)?\b\s*[:=]?\s*([-+]?\d{1,3}(?:\.\d+)?)\s*"
        r"(?:degrees?|[°º])?\s*([EW])?",
        text,
    )
    if decimal_lat and decimal_lon:
        latitude = float(decimal_lat.group(1))
        longitude = float(decimal_lon.group(1))
        if (decimal_lat.group(2) or "").upper() == "S":
            latitude = -abs(latitude)
        if (decimal_lon.group(2) or "").upper() == "W":
            longitude = -abs(longitude)
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            start = max(0, min(decimal_lat.start(), decimal_lon.start()) - 120)
            end = min(len(text), max(decimal_lat.end(), decimal_lon.end()) + 120)
            result.update({
                "latitude": format(latitude, ".10g"),
                "longitude": format(longitude, ".10g"),
                "method": "source_decimal_degrees",
                "uncertainty": "source precision retained; field accuracy not independently verified",
                "uncertainty_km": "0.1",
                "confidence": "medium_source_reported",
                "evidence": clean_text(text[start:end]).strip(" -:;,.")
            })
            return result

    dmm_lat = re.search(
        r"(?i)\b(\d{1,2})\s*[°ºo?]\s*(\d{1,2}(?:\.\d+)?)\s*"
        r"(?:m|['′])?\s*([NS])\b(?:\s*lat(?:itude)?)?",
        text,
    )
    dmm_lon = re.search(
        r"(?i)\b(\d{1,3})\s*[°ºo?]\s*(\d{1,2}(?:\.\d+)?)\s*"
        r"(?:m|['′])?\s*([EW])\b(?:\s*lon(?:gitude)?)?",
        text,
    )
    if dmm_lat and dmm_lon:
        lat_deg, lat_min = int(dmm_lat.group(1)), float(dmm_lat.group(2))
        lon_deg, lon_min = int(dmm_lon.group(1)), float(dmm_lon.group(2))
        latitude = lat_deg + lat_min / 60.0
        longitude = lon_deg + lon_min / 60.0
        if dmm_lat.group(3).upper() == "S":
            latitude = -latitude
        if dmm_lon.group(3).upper() == "W":
            longitude = -longitude
        if lat_min < 60 and lon_min < 60 and -90 <= latitude <= 90 and -180 <= longitude <= 180:
            start = max(0, min(dmm_lat.start(), dmm_lon.start()) - 120)
            end = min(len(text), max(dmm_lat.end(), dmm_lon.end()) + 160)
            uncertainty = "converted from source degree-decimal-minute coordinates"
            window = text[start:end]
            if re.search(r"(?i)\bapproximately\b", window):
                uncertainty += "; source explicitly says approximately"
            result.update({
                "latitude": format(latitude, ".10g"),
                "longitude": format(longitude, ".10g"),
                "method": "source_degree_decimal_minutes_converted",
                "uncertainty": uncertainty + "; field accuracy not independently verified",
                "uncertainty_km": "0.1",
                "confidence": "medium_source_reported",
                "evidence": clean_text(window).strip(" -:;,.")
            })
    return result


def is_ui_image(url: str) -> bool:
    name = Path(decode_url_path(urlsplit(url).path)).name.casefold()
    stem = Path(name).stem
    if stem in UI_IMAGE_NAMES:
        return True
    return bool(re.fullmatch(
        r"(?:next|prev|previous|back|forward|up|home)(?:[_-]?(?:button|arrow|page))?",
        stem,
    ))


def classify_image(url: str, alt: str = "", title: str = "") -> str:
    text = norm(" ".join((url, alt, title)))
    if any(word in text for word in ("map", "topo", "satellite", "aerial", "overhead")):
        return "map_or_aerial"
    if any(word in text for word in ("diagram", "drawing", "sketch", "layout", "plan")):
        return "diagram"
    return "photograph_or_unspecified"


def choose_snapshot(candidates: list[dict[str, str]]) -> dict[str, str] | None:
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            0 if row.get("http_status", "").startswith("2") else 1,
            -int(row.get("bytes") or 0),
            row.get("url", ""),
        ),
    )[0]


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not SNAPSHOT_PATH.exists() or not EDGE_PATH.exists():
        raise SystemExit("Run scripts/fetch_iccra_full.ps1 before parsing ICCRA.")

    with SNAPSHOT_PATH.open(newline="", encoding="utf-8-sig") as handle:
        snapshots = list(csv.DictReader(handle))
    with EDGE_PATH.open(newline="", encoding="utf-8-sig") as handle:
        edges = list(csv.DictReader(handle))

    by_url = {row["url"]: row for row in snapshots}
    by_match: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in snapshots:
        by_match[url_match_key(row["url"])].append(row)

    page_cache: dict[str, ArchiveHTML] = {}

    def page_for(row: dict[str, str] | None) -> ArchiveHTML | None:
        if not row or not row.get("cache_path") or not row.get("http_status", "").startswith("2"):
            return None
        url = row["url"]
        if url not in page_cache:
            parser = ArchiveHTML()
            parser.feed(decode_page(ROOT / row["cache_path"]))
            parser.close()
            page_cache[url] = parser
        return page_cache[url]

    def snapshots_for_resolved(base: str, href: str) -> list[dict[str, str]]:
        return by_match.get(url_match_key(resolve_url(base, href)), [])

    def resolve_record(base: str, anchors: list[Anchor]) -> tuple[str, list[str]]:
        aliases: list[str] = []
        for anchor in anchors:
            resolved = resolve_url(base, anchor.href)
            if not resolved:
                continue
            path = urlsplit(resolved).path
            if not re.search(r"(?i)(?:\.html?|\.pdf|/index\.htm)$", path):
                continue
            matches = by_match.get(url_match_key(resolved), [])
            aliases.extend(row["url"] for row in matches)
            selected = choose_snapshot(matches)
            if selected and "formation_detail" in selected.get("roles", "").split(";"):
                return selected["url"], sorted(set(aliases))
        if aliases:
            selected = choose_snapshot([by_url[url] for url in set(aliases)])
            return (selected or {}).get("url", ""), sorted(set(aliases))
        return "", []

    byyear_root = page_for(by_url.get(BY_YEAR_URL))
    bystate_root = page_for(by_url.get(BY_STATE_URL))
    if byyear_root is None or bystate_root is None:
        raise SystemExit("Required ICCRA by-year or by-state index snapshot is unavailable.")

    # Restrict expected-count extraction to the archive table and its four
    # early historical links, stopping before the unrelated Fun Facts panel.
    raw_byyear = decode_page(ROOT / by_url[BY_YEAR_URL]["cache_path"])
    visible_byyear = clean_text(re.sub(r"<[^>]+>", " ", raw_byyear))
    start = visible_byyear.casefold().find("early historical reports")
    end = visible_byyear.casefold().find("fun facts")
    if start < 0:
        raise SystemExit("Could not locate ICCRA's Early Historical Reports count scope.")
    count_scope_text = visible_byyear[start:end if end > start else None]
    expected_by_year: dict[int, int] = {}
    for year_text, count_text in re.findall(r"\b((?:18|19|20)\d{2})\s*\((\d+)\)", count_scope_text):
        expected_by_year[int(year_text)] = int(count_text)

    occurrences: list[Occurrence] = []
    year_page_counts: dict[int, int] = Counter()
    state_page_counts: dict[str, int] = {}
    state_list_counts: dict[str, int] = {}
    state_linked_counts: dict[str, int] = {}

    year_rows = [row for row in snapshots if "year_index" in row["roles"].split(";")]
    for row in sorted(year_rows, key=lambda item: item["url"]):
        page = page_for(row)
        year_match = re.search(r"ICCRA_(\d{4})\.(?:html?|HTML?)$", row["url"])
        if page is None or not year_match:
            continue
        year = int(year_match.group(1))
        for ordinal, item in enumerate(page.list_items, 1):
            record_url, aliases = resolve_record(row["url"], item.anchors)
            occurrence = Occurrence(
                index_kind="by_year_page", index_url=row["url"], ordinal=ordinal,
                label=item.text, record_url=record_url, expected_group_count=expected_by_year.get(year),
                record_aliases=aliases,
            )
            occurrence.parsed = parse_date_location(item.text, year_hint=year)
            occurrences.append(occurrence)
            year_page_counts[year] += 1

    # Years represented by a direct detail link instead of a year list page.
    year_index_urls = {row["url"] for row in year_rows}
    seen_direct_urls: set[str] = set()
    for ordinal, anchor in enumerate(byyear_root.anchors, 1):
        if not re.fullmatch(r"(?:18|19|20)\d{2}", clean_text(anchor.text)):
            continue
        year = int(clean_text(anchor.text))
        resolved = resolve_url(BY_YEAR_URL, anchor.href)
        candidates = by_match.get(url_match_key(resolved), [])
        selected = choose_snapshot(candidates)
        if not selected or selected["url"] in year_index_urls:
            continue
        if "formation_detail" not in selected.get("roles", "").split(";"):
            continue
        direct_key = url_match_key(selected["url"])
        if direct_key in seen_direct_urls:
            continue
        seen_direct_urls.add(direct_key)
        detail = page_for(selected)
        label, derived_state = derive_record_label(
            selected["url"], selected.get("anchor_text", "") or anchor.text, detail, year,
        )
        occurrence = Occurrence(
            index_kind="by_year_direct", index_url=BY_YEAR_URL, ordinal=ordinal,
            label=clean_text(label), record_url=selected["url"], state_abbr=derived_state,
            expected_group_count=expected_by_year.get(year),
            record_aliases=sorted({row["url"] for row in candidates}),
        )
        occurrence.parsed = parse_date_location(label, state_hint=derived_state, year_hint=year)
        occurrences.append(occurrence)
        year_page_counts[year] += 1

    state_rows = [row for row in snapshots if "state_index" in row["roles"].split(";")]
    for row in sorted(state_rows, key=lambda item: item["url"]):
        page = page_for(row)
        if page is None:
            continue
        state_name = decode_url_path(urlsplit(row["url"]).path).strip("/").split("/")[1]
        state_abbr = STATE_ABBR_BY_NAME.get(state_name.casefold(), "OH" if state_name.casefold() == "ohio" else "")
        stated_match = re.search(r"\((\d+)\s+reports?\)", page.text, re.I)
        stated = int(stated_match.group(1)) if stated_match else 0
        state_page_counts[state_abbr] = stated
        state_list_counts[state_abbr] = len(page.list_items)
        linked = 0
        for ordinal, item in enumerate(page.list_items, 1):
            record_url, aliases = resolve_record(row["url"], item.anchors)
            if record_url or aliases:
                linked += 1
            occurrence = Occurrence(
                index_kind="by_state_page", index_url=row["url"], ordinal=ordinal,
                label=item.text, record_url=record_url, state_abbr=state_abbr,
                expected_group_count=stated, record_aliases=aliases,
            )
            occurrence.parsed = parse_date_location(item.text, state_hint=state_abbr)
            occurrences.append(occurrence)
        state_linked_counts[state_abbr] = linked

    # Two count cells (1950 and 1960 in the current index) have no year-page or
    # direct link. Preserve those promised slots explicitly. Where the state
    # catalog uniquely identifies the same year (1960), reuse that label/link;
    # otherwise retain a count-only placeholder instead of inventing details.
    count_only_occurrences = 0
    state_occurrences_by_year: dict[int, list[Occurrence]] = defaultdict(list)
    for occurrence in occurrences:
        if occurrence.index_kind == "by_state_page" and str(occurrence.parsed.get("year", "")).isdigit():
            state_occurrences_by_year[int(occurrence.parsed["year"])].append(occurrence)
    for year, expected in sorted(expected_by_year.items()):
        missing = max(0, expected - year_page_counts.get(year, 0))
        candidates = state_occurrences_by_year.get(year, [])
        for offset in range(missing):
            if len(candidates) == expected and offset < len(candidates):
                candidate = candidates[offset]
                label = candidate.label
                record_url = candidate.record_url
                aliases = list(candidate.record_aliases)
                state_abbr = str(candidate.parsed.get("state_abbr", ""))
            else:
                label = f"[ICCRA count-only formation; no listing or link] ({year})"
                record_url = ""
                aliases = []
                state_abbr = ""
            occurrence = Occurrence(
                index_kind="by_year_count_only", index_url=BY_YEAR_URL,
                ordinal=10000 + year * 10 + offset, label=label,
                record_url=record_url, state_abbr=state_abbr,
                expected_group_count=expected, record_aliases=aliases,
            )
            occurrence.parsed = parse_date_location(label, state_hint=state_abbr, year_hint=year)
            occurrences.append(occurrence)
            count_only_occurrences += 1

    # News pages add a few later formation detail links. Only concrete ICCRA
    # detail links are asserted; free-form news prose remains in reconciliation.
    news_urls = {row["url"] for row in snapshots if "news_index" in row["roles"].split(";")}
    news_edges = [
        edge for edge in edges
        if edge["discovered_from"] in news_urls and edge["role"] == "formation_detail"
    ]
    for ordinal, edge in enumerate(sorted(news_edges, key=lambda item: (item["discovered_from"], item["url"])), 1):
        selected = choose_snapshot(by_match.get(url_match_key(edge["url"]), []))
        record_url = selected["url"] if selected else edge["url"]
        detail = page_for(selected)
        label, derived_state = derive_record_label(
            record_url, edge.get("anchor_text", ""), detail,
        )
        occurrence = Occurrence(
            index_kind="news_detail_link", index_url=edge["discovered_from"], ordinal=ordinal,
            label=label, record_url=record_url, state_abbr=derived_state,
            record_aliases=sorted({row["url"] for row in by_match.get(url_match_key(record_url), [])}),
        )
        occurrence.parsed = parse_date_location(label, state_hint=derived_state)
        occurrences.append(occurrence)

    # Drop exact duplicate occurrences caused by repeated anchors, preserving
    # every distinct index/list slot.
    deduped: list[Occurrence] = []
    seen_occurrences: set[tuple[str, int, str, str]] = set()
    for occurrence in occurrences:
        key = (occurrence.index_url, occurrence.ordinal, norm(occurrence.label), url_match_key(occurrence.record_url))
        if key not in seen_occurrences:
            deduped.append(occurrence)
            seen_occurrences.add(key)
    occurrences = deduped

    union_find = UnionFind(len(occurrences))

    def occurrence_record_keys(occurrence: Occurrence) -> set[str]:
        keys = {url_match_key(occurrence.record_url)} if occurrence.record_url else set()
        keys.update(url_match_key(alias) for alias in occurrence.record_aliases)
        keys.discard("")
        return keys

    def compatible_identity(left: Occurrence, right: Occurrence) -> bool:
        left_year = str(left.parsed.get("year", ""))
        right_year = str(right.parsed.get("year", ""))
        if left_year and right_year and left_year != right_year:
            return False
        left_location = {
            token for token in norm(str(left.parsed.get("location_text", ""))).split()
            if token not in {"county", "parish", "borough", "unknown"}
        }
        right_location = {
            token for token in norm(str(right.parsed.get("location_text", ""))).split()
            if token not in {"county", "parish", "borough", "unknown"}
        }
        overlap = 0.0
        if left_location and right_location:
            overlap = len(left_location.intersection(right_location)) / min(len(left_location), len(right_location))
            if overlap < 0.2:
                return False
        left_state = str(left.parsed.get("state_abbr", ""))
        right_state = str(right.parsed.get("state_abbr", ""))
        if (
            left_state and right_state and left_state != right_state
            and left_location and right_location and overlap < 0.8
        ):
            return False
        return True

    # A state-list slot is the archive's most granular formation assertion.
    # Never merge two state slots with each other, even if ICCRA repeats a URL
    # or location/date. Match other indexes onto state slots only when identity
    # is compatible; this prevents bad year-page hrefs from collapsing distinct
    # Manchester/Escanaba, Calvert/Grapevine, and similar records.
    state_indexes = [
        index for index, occurrence in enumerate(occurrences)
        if occurrence.index_kind == "by_state_page"
    ]
    states_by_signature: dict[str, list[int]] = defaultdict(list)
    states_by_record_key: dict[str, list[int]] = defaultdict(list)
    states_by_year_state: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index in state_indexes:
        occurrence = occurrences[index]
        signature = str(occurrence.parsed.get("signature", ""))
        if signature:
            states_by_signature[signature].append(index)
        year_state = (
            str(occurrence.parsed.get("year", "")),
            str(occurrence.parsed.get("state_abbr", "")),
        )
        if all(year_state):
            states_by_year_state[year_state].append(index)
        for key in occurrence_record_keys(occurrence):
            states_by_record_key[key].append(index)

    nonstate_by_signature: dict[str, int] = {}
    nonstate_by_record_key: dict[str, int] = {}
    for index, occurrence in enumerate(occurrences):
        if occurrence.index_kind == "by_state_page":
            continue
        signature = str(occurrence.parsed.get("signature", ""))
        record_keys = occurrence_record_keys(occurrence)
        target: int | None = None
        signature_candidates = states_by_signature.get(signature, []) if signature else []
        if len(signature_candidates) == 1:
            target = signature_candidates[0]
        elif signature_candidates:
            exact = [
                candidate for candidate in signature_candidates
                if record_keys.intersection(occurrence_record_keys(occurrences[candidate]))
            ]
            if len(exact) == 1:
                target = exact[0]
        if target is None and record_keys:
            url_candidates = {
                candidate for key in record_keys for candidate in states_by_record_key.get(key, [])
                if compatible_identity(occurrence, occurrences[candidate])
            }
            if len(url_candidates) == 1:
                target = next(iter(url_candidates))
        if target is None:
            year_state = (
                str(occurrence.parsed.get("year", "")),
                str(occurrence.parsed.get("state_abbr", "")),
            )
            fuzzy_candidates: list[tuple[float, int]] = []
            if all(year_state):
                left_tokens = {
                    token for token in norm(str(occurrence.parsed.get("location_text", ""))).split()
                    if token not in {"county", "parish", "borough", "unknown"}
                }
                for candidate in states_by_year_state.get(year_state, []):
                    right_tokens = {
                        token for token in norm(str(occurrences[candidate].parsed.get("location_text", ""))).split()
                        if token not in {"county", "parish", "borough", "unknown"}
                    }
                    if left_tokens and right_tokens:
                        score = len(left_tokens.intersection(right_tokens)) / min(len(left_tokens), len(right_tokens))
                        if score >= 0.55:
                            fuzzy_candidates.append((score, candidate))
            fuzzy_candidates.sort(reverse=True)
            if fuzzy_candidates and (
                len(fuzzy_candidates) == 1 or fuzzy_candidates[0][0] > fuzzy_candidates[1][0]
            ):
                target = fuzzy_candidates[0][1]
        if target is None and signature and signature in nonstate_by_signature:
            candidate = nonstate_by_signature[signature]
            if compatible_identity(occurrence, occurrences[candidate]):
                target = candidate
        if target is None:
            compatible_url_candidates = {
                nonstate_by_record_key[key] for key in record_keys if key in nonstate_by_record_key
                and compatible_identity(occurrence, occurrences[nonstate_by_record_key[key]])
            }
            if len(compatible_url_candidates) == 1:
                target = next(iter(compatible_url_candidates))
        if target is not None:
            union_find.union(index, target)
        else:
            if signature:
                nonstate_by_signature.setdefault(signature, index)
            for key in record_keys:
                nonstate_by_record_key.setdefault(key, index)

    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(occurrences)):
        groups[union_find.find(index)].append(index)

    assertion_rows: list[dict[str, object]] = []
    occurrence_to_assertion: dict[int, str] = {}
    assertion_detail_urls: dict[str, set[str]] = defaultdict(set)

    for member_indexes in sorted(groups.values(), key=lambda members: min(members)):
        members = [occurrences[index] for index in member_indexes]
        parsed_options = [member.parsed for member in members]
        preferred_parsed = sorted(
            parsed_options,
            key=lambda item: (
                0 if item.get("date_iso") else 1,
                0 if item.get("state_abbr") else 1,
                -len(str(item.get("location_text", ""))),
            ),
        )[0]
        candidate_urls = {
            url for member in members for url in ([member.record_url] + member.record_aliases) if url
        }
        candidate_snapshots: list[dict[str, str]] = []
        for url in candidate_urls:
            candidate_snapshots.extend(by_match.get(url_match_key(url), []))
        candidate_snapshots = [
            row for row in {row["url"]: row for row in candidate_snapshots}.values()
            if "formation_detail" in row.get("roles", "").split(";")
        ]
        detail_snapshot = choose_snapshot(candidate_snapshots)
        detail_page = page_for(detail_snapshot)
        canonical_url = detail_snapshot["url"] if detail_snapshot else (
            sorted(candidate_urls)[0] if candidate_urls else ""
        )
        primary_member = next(
            (member for member in members if member.index_kind == "by_state_page"),
            members[0],
        )
        stable_seed = (
            f"{primary_member.index_kind}|{primary_member.index_url}#"
            f"{primary_member.ordinal}:{primary_member.label}"
        )
        assertion_id = "iccra_" + sha256_text(stable_seed)[:16]
        for index in member_indexes:
            occurrence_to_assertion[index] = assertion_id
        if canonical_url:
            assertion_detail_urls[assertion_id].add(canonical_url)

        title = detail_page.title if detail_page else ""
        detail_text = detail_page.text if detail_page else ""
        coordinate_context = context_windows(detail_text, COORDINATE_PATTERN)
        orientation_evidence = context_windows(detail_text, ORIENTATION_PATTERN)
        rights_evidence = context_windows(detail_text, RIGHTS_PATTERN)
        coordinate_pair = extract_coordinate_pair(detail_text)
        coordinate_evidence = [str(coordinate_pair["evidence"])] if coordinate_pair["evidence"] else []

        image_urls: list[str] = []
        map_diagram_urls: list[str] = []
        if detail_page and canonical_url:
            for image in detail_page.images:
                image_url = resolve_url(canonical_url, image.src)
                if not image_url or is_ui_image(image_url):
                    continue
                if image_url not in image_urls:
                    image_urls.append(image_url)
                if classify_image(image_url, image.alt, image.title) in {"map_or_aerial", "diagram"}:
                    map_diagram_urls.append(image_url)
            for anchor in detail_page.anchors:
                linked = resolve_url(canonical_url, anchor.href)
                if linked and IMAGE_EXT_RE.search(linked) and not is_ui_image(linked) and linked not in image_urls:
                    image_urls.append(linked)
                    if classify_image(linked, anchor.text) in {"map_or_aerial", "diagram"}:
                        map_diagram_urls.append(linked)

        labels = list(dict.fromkeys(member.label for member in members))
        source_indexes = sorted({member.index_url for member in members})
        index_kinds = sorted({member.index_kind for member in members})
        retrieved_at = detail_snapshot.get("retrieved_at", "") if detail_snapshot else ""
        notes = "ICCRA index labels: " + " | ".join(labels)
        if coordinate_evidence:
            notes += "; coordinate evidence: " + " | ".join(coordinate_evidence)
        elif coordinate_context:
            notes += "; coordinate context without a usable pair: " + " | ".join(coordinate_context)
        if orientation_evidence:
            notes += "; orientation evidence: " + " | ".join(orientation_evidence)
        if rights_evidence:
            notes += "; rights evidence: " + " | ".join(rights_evidence)

        assertion_rows.append({
            "assertion_id": assertion_id,
            "source_name": "ICCRA",
            "source_url": source_indexes[0] if source_indexes else BY_STATE_URL,
            "source_record_url": canonical_url,
            "retrieved_at": retrieved_at,
            "source_page": "",
            "source_slot": min(member.ordinal for member in members),
            "year": preferred_parsed.get("year", ""),
            "month": preferred_parsed.get("month", ""),
            "day": preferred_parsed.get("day", ""),
            "date_iso": preferred_parsed.get("date_iso", ""),
            "date_precision": preferred_parsed.get("date_precision", "unknown"),
            "date_qualifier": preferred_parsed.get("date_qualifier", ""),
            "place": preferred_parsed.get("place", ""),
            "region": preferred_parsed.get("region", ""),
            "country": preferred_parsed.get("country", "United States"),
            "country_code": preferred_parsed.get("country_code", "US"),
            "county": preferred_parsed.get("county", ""),
            "crop": "",
            "size_text": "",
            "classification": "unreviewed",
            "thumbnail_url": image_urls[0] if image_urls else "",
            "notes": notes,
            "index_kinds": ";".join(index_kinds),
            "index_urls": ";".join(source_indexes),
            "index_labels": " | ".join(labels),
            "index_occurrence_count": len(members),
            "record_url_aliases": ";".join(sorted(candidate_urls)),
            "detail_http_status": detail_snapshot.get("http_status", "") if detail_snapshot else "",
            "detail_sha256": detail_snapshot.get("sha256", "") if detail_snapshot else "",
            "detail_cache_path": detail_snapshot.get("cache_path", "") if detail_snapshot else "",
            "detail_title": title,
            "latitude": coordinate_pair["latitude"],
            "longitude": coordinate_pair["longitude"],
            "has_actual_coordinate_pair": bool(coordinate_pair["latitude"] and coordinate_pair["longitude"]),
            "coordinate_method": coordinate_pair["method"],
            "coordinate_uncertainty": coordinate_pair["uncertainty"],
            "coordinate_uncertainty_km": coordinate_pair["uncertainty_km"],
            "coordinate_confidence": coordinate_pair["confidence"],
            "coordinate_source_url": canonical_url if coordinate_pair["evidence"] else "",
            "coordinate_evidence": " | ".join(coordinate_evidence),
            "coordinate_context": " | ".join(coordinate_context),
            "orientation_evidence": " | ".join(orientation_evidence),
            "rights_evidence": " | ".join(rights_evidence),
            "image_count": len(image_urls),
            "image_urls": ";".join(image_urls),
            "map_diagram_urls": ";".join(dict.fromkeys(map_diagram_urls)),
        })

    assertion_by_id = {row["assertion_id"]: row for row in assertion_rows}

    # Two detailed field reports contain DMM coordinates that are not repeated
    # on their shorter state pages. Associate report coordinates by year,
    # state, date, and location-token agreement; ties remain unassigned.
    coordinate_report_matches: list[dict[str, str]] = []
    report_coordinate_snapshots = [
        row for row in snapshots
        if "report_document" in row.get("roles", "").split(";")
        and row.get("http_status", "").startswith("2")
        and re.search(r"(?i)\.html?$", urlsplit(row["url"]).path)
    ]
    for report_snapshot in report_coordinate_snapshots:
        report_page = page_for(report_snapshot)
        if report_page is None:
            continue
        report_pair = extract_coordinate_pair(report_page.text)
        if not report_pair["latitude"] or not report_pair["longitude"]:
            continue
        report_identity = clean_text(report_page.title + " " + decode_url_path(urlsplit(report_snapshot["url"]).path))
        year_match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", report_identity)
        report_year = int(year_match.group(1)) if year_match else None
        report_state = ""
        for state_name, abbreviation in STATE_ABBR_BY_NAME.items():
            if re.search(rf"\b{re.escape(state_name)}\b", report_identity, re.I):
                report_state = abbreviation
                break
        report_month = report_day = None
        written_date = re.search(rf"\b({MONTH_PATTERN})\.?\s+(\d{{1,2}}),?\s+((?:19|20)\d{{2}})\b", report_identity, re.I)
        if written_date:
            report_month = MONTHS[written_date.group(1).casefold().rstrip(".")]
            report_day = int(written_date.group(2))
            report_year = int(written_date.group(3))
        report_tokens = {
            token for token in norm(report_identity).split()
            if len(token) >= 4 and token not in {"iccra", "initial", "field", "report", "circle", "formation", "county"}
        }
        scored: list[tuple[int, dict[str, object]]] = []
        for assertion in assertion_rows:
            if report_year and str(assertion["year"]) != str(report_year):
                continue
            if report_state and assertion["region"] != US_STATES.get(report_state):
                continue
            assertion_tokens = {
                token for token in norm(str(assertion["place"]) + " " + str(assertion["county"])).split()
                if len(token) >= 4 and token not in {"county", "township"}
            }
            score = len(report_tokens.intersection(assertion_tokens)) * 2
            if report_month and str(assertion["month"]) == str(report_month):
                score += 2
            if report_day and str(assertion["day"]) == str(report_day):
                score += 3
            if score:
                scored.append((score, assertion))
        if not scored:
            continue
        scored.sort(key=lambda item: (-item[0], str(item[1]["assertion_id"])))
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            continue
        assertion = scored[0][1]
        if assertion["has_actual_coordinate_pair"]:
            continue
        assertion["latitude"] = report_pair["latitude"]
        assertion["longitude"] = report_pair["longitude"]
        assertion["has_actual_coordinate_pair"] = True
        assertion["coordinate_method"] = "report_" + str(report_pair["method"])
        assertion["coordinate_uncertainty"] = report_pair["uncertainty"]
        assertion["coordinate_uncertainty_km"] = report_pair["uncertainty_km"]
        assertion["coordinate_confidence"] = report_pair["confidence"]
        assertion["coordinate_source_url"] = report_snapshot["url"]
        assertion["coordinate_evidence"] = report_pair["evidence"]
        report_context = " | ".join(context_windows(report_page.text, COORDINATE_PATTERN))
        assertion["coordinate_context"] = report_context
        assertion["notes"] = str(assertion["notes"]) + "; report coordinate evidence: " + str(report_pair["evidence"])
        coordinate_report_matches.append({
            "assertion_id": str(assertion["assertion_id"]),
            "report_url": report_snapshot["url"],
            "latitude": str(report_pair["latitude"]),
            "longitude": str(report_pair["longitude"]),
        })

    index_entry_rows: list[dict[str, object]] = []
    for index, occurrence in enumerate(occurrences):
        aliases = set(occurrence.record_aliases)
        if occurrence.record_url:
            aliases.add(occurrence.record_url)
        snapshots_for_entry = [
            row for alias in aliases for row in by_match.get(url_match_key(alias), [])
        ]
        selected = choose_snapshot(snapshots_for_entry)
        assertion_id = occurrence_to_assertion[index]
        assertion = assertion_by_id[assertion_id]
        index_entry_rows.append({
            "index_entry_id": "iccra_idx_" + sha256_text(
                f"{occurrence.index_url}|{occurrence.ordinal}|{occurrence.label}"
            )[:16],
            "assertion_id": assertion_id,
            "index_kind": occurrence.index_kind,
            "index_url": occurrence.index_url,
            "ordinal": occurrence.ordinal,
            "label": occurrence.label,
            "state_abbr": occurrence.parsed.get("state_abbr", ""),
            "year": occurrence.parsed.get("year", ""),
            "expected_group_count": occurrence.expected_group_count or "",
            "record_url": occurrence.record_url,
            "record_url_aliases": ";".join(sorted(aliases)),
            "record_http_status": selected.get("http_status", "") if selected else "",
            "record_sha256": selected.get("sha256", "") if selected else "",
            "record_cache_path": selected.get("cache_path", "") if selected else "",
            "has_link": bool(aliases),
            "linked_url_http_success": bool(selected and selected.get("http_status", "").startswith("2")),
            "assertion_detail_http_status": assertion.get("detail_http_status", ""),
            "has_successful_detail": str(assertion.get("detail_http_status", "")).startswith("2"),
        })

    # Image-link inventory includes every non-navigation image referenced by a
    # formation detail, report HTML page, state index, or news page. External
    # images are recorded but not fetched by the ICCRA crawler.
    image_source_roles = {
        "formation_detail", "report_document", "formation_supporting_document",
        "state_index", "news_index",
    }
    detail_key_to_assertions: dict[str, set[str]] = defaultdict(set)
    for row in assertion_rows:
        for alias in str(row["record_url_aliases"]).split(";"):
            if alias:
                detail_key_to_assertions[url_match_key(alias)].add(str(row["assertion_id"]))

    image_rows: list[dict[str, object]] = []
    seen_images: set[tuple[str, str, str]] = set()
    excluded_ui_references = 0
    for source_snapshot in snapshots:
        roles = set(source_snapshot.get("roles", "").split(";"))
        if not roles.intersection(image_source_roles):
            continue
        if not source_snapshot.get("http_status", "").startswith("2"):
            continue
        if not re.search(r"(?i)\.html?$", urlsplit(source_snapshot["url"]).path):
            continue
        page = page_for(source_snapshot)
        if page is None:
            continue
        rights = " | ".join(context_windows(page.text, RIGHTS_PATTERN))
        references: list[ImageRef] = list(page.images)
        references.extend(
            ImageRef(src=anchor.href, alt=anchor.text, reference_kind="linked")
            for anchor in page.anchors if IMAGE_EXT_RE.search(anchor.href)
        )
        for image in references:
            image_url = resolve_url(source_snapshot["url"], image.src)
            if not image_url:
                continue
            if is_ui_image(image_url):
                excluded_ui_references += 1
                continue
            key = (source_snapshot["url"], image_url, image.reference_kind)
            if key in seen_images:
                continue
            seen_images.add(key)
            image_snapshot = choose_snapshot(by_match.get(url_match_key(image_url), []))
            linked_assertions = sorted(detail_key_to_assertions.get(url_match_key(source_snapshot["url"]), set()))
            image_rows.append({
                "image_link_id": "iccra_img_" + sha256_text("|".join(key))[:16],
                "assertion_ids": ";".join(linked_assertions),
                "source_page_url": source_snapshot["url"],
                "source_page_roles": source_snapshot["roles"],
                "image_url": image_url,
                "reference_kind": image.reference_kind,
                "image_kind": classify_image(image_url, image.alt, image.title),
                "alt_text": image.alt,
                "title_text": image.title,
                "width": image.width,
                "height": image.height,
                "is_iccra_hosted": is_iccra_url(image_url),
                "fetch_policy": "robots_allowed_private_raw_cache" if is_iccra_url(image_url) else "external_not_fetched",
                "http_status": image_snapshot.get("http_status", "") if image_snapshot else "",
                "sha256": image_snapshot.get("sha256", "") if image_snapshot else "",
                "bytes": image_snapshot.get("bytes", "") if image_snapshot else "",
                "cache_path": image_snapshot.get("cache_path", "") if image_snapshot else "",
                "rights_evidence": rights,
                "public_redistribution_status": "not_cleared",
            })

    report_rows: list[dict[str, object]] = []
    report_roles = {"report_document", "formation_supporting_document", "historical_evidence"}
    for row in snapshots:
        roles = set(row.get("roles", "").split(";"))
        if not roles.intersection(report_roles):
            continue
        report_rows.append({
            "url": row["url"], "roles": row["roles"], "anchor_text": row.get("anchor_text", ""),
            "discovered_from": row.get("discovered_from", ""), "retrieved_at": row.get("retrieved_at", ""),
            "http_status": row.get("http_status", ""), "sha256": row.get("sha256", ""),
            "bytes": row.get("bytes", ""), "cache_path": row.get("cache_path", ""),
            "content_type": row.get("content_type", ""), "error": row.get("error", ""),
        })

    assertion_fields = [
        "assertion_id", "source_name", "source_url", "source_record_url", "retrieved_at",
        "source_page", "source_slot", "year", "month", "day", "date_iso", "date_precision",
        "date_qualifier", "place", "region", "country", "country_code", "county", "crop",
        "size_text", "classification", "thumbnail_url", "notes", "index_kinds", "index_urls",
        "index_labels", "index_occurrence_count", "record_url_aliases", "detail_http_status",
        "detail_sha256", "detail_cache_path", "detail_title", "latitude", "longitude",
        "has_actual_coordinate_pair", "coordinate_method", "coordinate_uncertainty",
        "coordinate_uncertainty_km", "coordinate_confidence", "coordinate_source_url",
        "coordinate_evidence", "coordinate_context",
        "orientation_evidence", "rights_evidence", "image_count",
        "image_urls", "map_diagram_urls",
    ]
    index_fields = [
        "index_entry_id", "assertion_id", "index_kind", "index_url", "ordinal", "label",
        "state_abbr", "year", "expected_group_count", "record_url", "record_url_aliases",
        "record_http_status", "record_sha256", "record_cache_path", "has_link",
        "linked_url_http_success", "assertion_detail_http_status", "has_successful_detail",
    ]
    image_fields = [
        "image_link_id", "assertion_ids", "source_page_url", "source_page_roles", "image_url",
        "reference_kind", "image_kind", "alt_text", "title_text", "width", "height",
        "is_iccra_hosted", "fetch_policy", "http_status", "sha256", "bytes", "cache_path",
        "rights_evidence", "public_redistribution_status",
    ]
    report_fields = [
        "url", "roles", "anchor_text", "discovered_from", "retrieved_at", "http_status",
        "sha256", "bytes", "cache_path", "content_type", "error",
    ]
    assertion_rows.sort(key=lambda row: (str(row["date_iso"]), str(row["region"]), str(row["place"]), str(row["assertion_id"])))
    index_entry_rows.sort(key=lambda row: (str(row["index_url"]), int(row["ordinal"])))
    image_rows.sort(key=lambda row: (str(row["source_page_url"]), str(row["image_url"]), str(row["reference_kind"])))
    report_rows.sort(key=lambda row: str(row["url"]))
    write_csv(ASSERTION_PATH, assertion_rows, assertion_fields)
    write_csv(INDEX_ENTRY_PATH, index_entry_rows, index_fields)
    write_csv(IMAGE_LINK_PATH, image_rows, image_fields)
    write_csv(REPORT_LINK_PATH, report_rows, report_fields)

    assertions_by_year = Counter(int(row["year"]) for row in assertion_rows if str(row["year"]).isdigit())
    by_year_reconciliation = []
    for year in sorted(expected_by_year):
        actual_year_occurrences = year_page_counts.get(year, 0)
        captured = assertions_by_year.get(year, 0)
        by_year_reconciliation.append({
            "year": year, "index_stated_count": expected_by_year[year],
            "byyear_list_or_direct_count": actual_year_occurrences,
            "canonical_assertions_for_year": captured,
            "byyear_delta": actual_year_occurrences - expected_by_year[year],
            "captured_at_least_stated": captured >= expected_by_year[year],
        })

    by_state_reconciliation = []
    for state_abbr in sorted(state_list_counts):
        by_state_reconciliation.append({
            "state_abbr": state_abbr, "state": US_STATES.get(state_abbr, state_abbr),
            "page_stated_count": state_page_counts.get(state_abbr, 0),
            "parsed_list_items": state_list_counts[state_abbr],
            "linked_list_items": state_linked_counts.get(state_abbr, 0),
            "unlinked_list_items": state_list_counts[state_abbr] - state_linked_counts.get(state_abbr, 0),
            "delta": state_list_counts[state_abbr] - state_page_counts.get(state_abbr, 0),
        })

    formation_snapshots = [row for row in snapshots if "formation_detail" in row["roles"].split(";")]
    failed_formation_snapshots = [row for row in formation_snapshots if not row["http_status"].startswith("2")]
    failed_index_entries = [row for row in index_entry_rows if row["has_link"] and not row["has_successful_detail"]]
    unlinked_index_entries = [row for row in index_entry_rows if not row["has_link"]]
    hosted_images = [row for row in image_rows if row["is_iccra_hosted"]]
    successful_hosted_images = [row for row in hosted_images if str(row["http_status"]).startswith("2")]
    unique_image_urls = {str(row["image_url"]) for row in image_rows}

    scope_index_roles = {
        "byyear_index", "bystate_index", "year_index", "state_index",
        "reports_index", "historical_index", "news_index", "formation_landing",
    }
    scope_document_roles = {"report_document", "historical_evidence", "formation_supporting_document"}
    present_roles = {
        role
        for row in snapshots
        for role in row["roles"].split(";")
        if role
    }
    all_core_indexes_successful = scope_index_roles.issubset(present_roles) and all(
        row["http_status"].startswith("2")
        for row in snapshots
        if set(row["roles"].split(";")).intersection(scope_index_roles)
    )
    all_scope_documents_successful = scope_document_roles.issubset(present_roles) and all(
        row["http_status"].startswith("2")
        for row in snapshots
        if set(row["roles"].split(";")).intersection(scope_document_roles)
    )
    raw_year_inventory_count = sum(
        1 for row in index_entry_rows if row["index_kind"] in {"by_year_page", "by_year_direct"}
    )
    every_index_slot_accounted = (
        sum(state_list_counts.values()) == sum(1 for row in index_entry_rows if row["index_kind"] == "by_state_page")
        and sum(year_page_counts.values()) == raw_year_inventory_count
        and len(index_entry_rows) == len(occurrences)
        and all(row["assertion_id"] in assertion_by_id for row in index_entry_rows)
    )
    index_inventory_complete = all_core_indexes_successful and every_index_slot_accounted
    scope_inventory_complete = index_inventory_complete and all_scope_documents_successful
    detail_pages_available = not failed_index_entries
    complete = scope_inventory_complete and detail_pages_available
    snapshot_cutoff = max(
        (row.get("retrieved_at", "") for row in snapshots if row.get("retrieved_at")),
        default=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    reconciliation = {
        "schema_version": "1.0.0",
        "generated_at": snapshot_cutoff,
        "scope": "ICCRA by-year, by-state, reports, historical references, and news archive",
        "robots_policy": "https://iccra.org/robots.txt explicitly allows /",
        "status": "complete" if complete else (
            "index_inventory_complete_with_unavailable_detail_pages"
            if scope_inventory_complete else "index_inventory_incomplete"
        ),
        "complete": complete,
        "totals": {
            "byyear_index_stated_formations": sum(expected_by_year.values()),
            "byyear_year_groups_with_counts": len(expected_by_year),
            "byyear_list_and_direct_occurrences": sum(year_page_counts.values()),
            "byyear_count_only_placeholders": count_only_occurrences,
            "bystate_pages": len(state_list_counts),
            "bystate_page_stated_sum": sum(state_page_counts.values()),
            "bystate_parsed_list_items": sum(state_list_counts.values()),
            "bystate_linked_list_items": sum(state_linked_counts.values()),
            "bystate_unlinked_list_items": sum(state_list_counts.values()) - sum(state_linked_counts.values()),
            "all_index_occurrences": len(index_entry_rows),
            "parsed_index_occurrences_excluding_count_only_placeholders": len(index_entry_rows) - count_only_occurrences,
            "canonical_assertions": len(assertion_rows),
            "formation_detail_urls_discovered": len(formation_snapshots),
            "formation_detail_urls_http_success": sum(row["http_status"].startswith("2") for row in formation_snapshots),
            "formation_detail_urls_failed": len(failed_formation_snapshots),
            "index_entries_with_unresolved_detail": len(failed_index_entries),
            "actual_coordinate_pair_assertions": sum(bool(row["has_actual_coordinate_pair"]) for row in assertion_rows),
            "coordinate_context_assertions": sum(bool(row["coordinate_context"]) for row in assertion_rows),
            "report_coordinate_matches": len(coordinate_report_matches),
            "orientation_evidence_assertions": sum(bool(row["orientation_evidence"]) for row in assertion_rows),
            "rights_evidence_assertions": sum(bool(row["rights_evidence"]) for row in assertion_rows),
            "image_references": len(image_rows),
            "unique_image_urls": len(unique_image_urls),
            "iccra_hosted_image_references": len(hosted_images),
            "iccra_hosted_image_references_http_success": len(successful_hosted_images),
            "excluded_repeated_ui_image_references": excluded_ui_references,
            "report_and_historical_documents": len(report_rows),
        },
        "completeness_checks": {
            "all_core_indexes_http_success": all_core_indexes_successful,
            "all_report_historical_news_documents_http_success": all_scope_documents_successful,
            "every_parsed_index_slot_accounted": every_index_slot_accounted,
            "index_inventory_complete": index_inventory_complete,
            "scope_inventory_complete": scope_inventory_complete,
            "detail_pages_available": detail_pages_available,
            "every_linked_index_entry_has_successful_detail": not failed_index_entries,
            "public_image_redistribution_cleared": False,
        },
        "by_year": by_year_reconciliation,
        "by_state": by_state_reconciliation,
        "failed_formation_urls": [
            {key: row.get(key, "") for key in ("url", "http_status", "roles", "anchor_text", "discovered_from", "error")}
            for row in failed_formation_snapshots
        ],
        "unresolved_index_entries": [
            {key: row.get(key, "") for key in ("index_entry_id", "assertion_id", "index_url", "ordinal", "label", "record_url", "record_http_status")}
            for row in failed_index_entries
        ],
        "unlinked_index_entries": [
            {key: row.get(key, "") for key in ("index_entry_id", "assertion_id", "index_url", "ordinal", "label", "state_abbr", "year")}
            for row in unlinked_index_entries
        ],
        "report_coordinate_matches": coordinate_report_matches,
        "artifacts": {
            "assertions": ASSERTION_PATH.relative_to(ROOT).as_posix(),
            "index_entries": INDEX_ENTRY_PATH.relative_to(ROOT).as_posix(),
            "snapshots": SNAPSHOT_PATH.relative_to(ROOT).as_posix(),
            "images": IMAGE_LINK_PATH.relative_to(ROOT).as_posix(),
            "reports": REPORT_LINK_PATH.relative_to(ROOT).as_posix(),
        },
    }
    RECONCILIATION_PATH.write_text(json.dumps(reconciliation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    mismatched_years = [row for row in by_year_reconciliation if row["byyear_delta"]]
    mismatched_states = [row for row in by_state_reconciliation if row["delta"]]
    md_lines = [
        "# ICCRA Archive Reconciliation",
        "",
        f"Generated: `{reconciliation['generated_at']}`",
        "",
        f"Status: **{reconciliation['status']}**. Index inventory and detail-page availability are reported independently.",
        "",
        "## Exact totals",
        "",
        f"- By-year index stated total: **{sum(expected_by_year.values())}** formations.",
        f"- By-year list/direct occurrences parsed: **{sum(year_page_counts.values())}**.",
        f"- Count-only year placeholders: **{count_only_occurrences}** (the index states a count but supplies no year listing/link).",
        f"- By-state page stated sum: **{sum(state_page_counts.values())}** reports.",
        f"- By-state list items actually parsed: **{sum(state_list_counts.values())}** ({sum(state_linked_counts.values())} linked; {sum(state_list_counts.values()) - sum(state_linked_counts.values())} unlinked).",
        f"- Canonical assertions after cross-index reconciliation: **{len(assertion_rows)}**.",
        f"- Unique formation-detail URLs: **{len(formation_snapshots)}** ({sum(row['http_status'].startswith('2') for row in formation_snapshots)} successful; {len(failed_formation_snapshots)} failed URL variants).",
        f"- Index entries still lacking a successful detail page: **{len(failed_index_entries)}**.",
        "",
        "## Enrichment evidence",
        "",
        f"- Actual coordinate pairs: **{reconciliation['totals']['actual_coordinate_pair_assertions']}** assertions; coordinate/GPS context without necessarily containing a pair: **{reconciliation['totals']['coordinate_context_assertions']}**.",
        f"- North/bearing/orientation evidence: **{reconciliation['totals']['orientation_evidence_assertions']}** assertions.",
        f"- Non-navigation image references: **{len(image_rows)}** across **{len(unique_image_urls)}** unique URLs.",
        f"- ICCRA-hosted image references fetched successfully: **{len(successful_hosted_images)} / {len(hosted_images)}**.",
        "- Image public redistribution status: **not cleared**; cached files are research inputs only.",
        "",
        "## Count mismatches preserved from ICCRA",
        "",
        "### By year",
        "",
        "| Year | Index stated | Parsed list/direct | Delta |",
        "|---:|---:|---:|---:|",
    ]
    md_lines.extend(
        f"| {row['year']} | {row['index_stated_count']} | {row['byyear_list_or_direct_count']} | {row['byyear_delta']:+d} |"
        for row in mismatched_years
    )
    md_lines.extend([
        "",
        "### By state",
        "",
        "| State | Page stated | Parsed list items | Delta |",
        "|---|---:|---:|---:|",
    ])
    md_lines.extend(
        f"| {row['state']} | {row['page_stated_count']} | {row['parsed_list_items']} | {row['delta']:+d} |"
        for row in mismatched_states
    )
    md_lines.extend([
        "",
        "## Unresolved linked entries",
        "",
    ])
    if failed_index_entries:
        md_lines.extend(
            f"- `{row['record_http_status'] or 'no response'}` — {row['label']} — {row['record_url']}"
            for row in failed_index_entries
        )
    else:
        md_lines.append("- None.")
    md_lines.extend([
        "",
        "The machine-readable reconciliation, including every failed URL variant and every unlinked list item, is in `data/iccra_reconciliation.json`.",
        "",
    ])
    RECONCILIATION_MD_PATH.write_text("\n".join(md_lines), encoding="utf-8")

    print(json.dumps({
        "status": reconciliation["status"],
        "byyear_stated": sum(expected_by_year.values()),
        "byyear_occurrences": sum(year_page_counts.values()),
        "bystate_stated": sum(state_page_counts.values()),
        "bystate_list_items": sum(state_list_counts.values()),
        "canonical_assertions": len(assertion_rows),
        "formation_detail_success": reconciliation["totals"]["formation_detail_urls_http_success"],
        "formation_detail_failed": len(failed_formation_snapshots),
        "unresolved_index_entries": len(failed_index_entries),
        "image_references": len(image_rows),
        "actual_coordinate_pairs": reconciliation["totals"]["actual_coordinate_pair_assertions"],
        "coordinate_context": reconciliation["totals"]["coordinate_context_assertions"],
        "orientation_evidence": reconciliation["totals"]["orientation_evidence_assertions"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
