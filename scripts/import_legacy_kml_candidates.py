#!/usr/bin/env python3
"""Import user-supplied legacy KML coordinates without executing remote content.

The importer never extracts archive members and never performs network I/O.  It
reads bounded ZIP/KMZ members in memory, rejects unsafe paths and active XML,
turns HTML descriptions into inert text, and retains URL strings only as data.
Every imported point remains an unverified candidate: it cannot become a site,
overlay, alignment origin, or publication asset through this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import os
import re
import tempfile
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Iterator
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "data" / "legacy_kml_candidates.json"
DEFAULT_CSV = ROOT / "data" / "legacy_kml_candidate_queue.csv"

MAX_ARCHIVE_DEPTH = 2
MAX_MEMBER_BYTES = 5_000_000
MAX_SOURCE_ARCHIVE_BYTES = 25_000_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 25_000_000
MAX_CUMULATIVE_EXPANDED_BYTES = 25_000_000
MAX_COMPRESSION_RATIO = 500
DUPLICATE_RADIUS_M = 200.0

PRIMARY_CROP_COLLECTIONS = {
    "132_cropcirclecollection.kml",
    "alien-crop-circles.kml",
    "crop-circles.kml",
}
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
CROP_NAME_RE = re.compile(r"\bcrop[\s_-]*circles?\b", re.IGNORECASE)
ACTIVE_XML_RE = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
ACTIVE_XML_TEXT_RE = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def direct_child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in list(element) if local_name(child) == name), None)


def direct_text(element: ET.Element, name: str) -> str:
    child = direct_child(element, name)
    if child is None:
        return ""
    return "".join(child.itertext()).strip()


def descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if local_name(child) == name]


def number_or_none(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def unique_in_order(values: Iterator[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


class _InertTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div", "li", "tr"}:
            self.parts.append("\n")


def inert_description(fragment: str) -> str:
    parser = _InertTextParser()
    parser.feed(html.unescape(fragment))
    parser.close()
    text = " ".join("".join(parser.parts).replace("\x00", "").split())
    return text.strip()


def description_fragment(placemark: ET.Element) -> str:
    description = direct_child(placemark, "description")
    if description is None:
        return ""
    parts = [description.text or ""]
    for child in list(description):
        parts.append(ET.tostring(child, encoding="unicode", method="xml"))
    return "".join(parts)


def contains_active_xml(payload: bytes) -> bool:
    """Reject DTD/entity declarations even when the XML uses UTF-16/32."""
    if ACTIVE_XML_RE.search(payload) or ACTIVE_XML_RE.search(payload.replace(b"\x00", b"")):
        return True
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"):
        try:
            decoded = payload.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if ACTIVE_XML_TEXT_RE.search(decoded):
            return True
    return False


def url_strings(placemark: ET.Element, description_html: str) -> list[str]:
    """Collect literal placemark URLs without serializing namespace declarations."""
    fragments = [description_html]
    for node in placemark.iter():
        if local_name(node).lower() in {"href", "url"}:
            fragments.append("".join(node.itertext()))
        for attribute_name, value in node.attrib.items():
            if local_name(ET.Element(attribute_name)).lower() in {"href", "src", "url"}:
                fragments.append(value)

    discovered: list[str] = []
    for fragment in fragments:
        decoded = html.unescape(html.unescape(fragment))
        for match in URL_RE.finditer(decoded):
            value = html.unescape(match.group(0))
            value = value.split("&lt;", 1)[0].split("<", 1)[0]
            value = value.rstrip(".,);]}>")
            if value:
                discovered.append(value)
    return unique_in_order(iter(discovered))


def safe_member_name(filename: str) -> str | None:
    normalized = filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    if path.parts and re.match(r"^[A-Za-z]:", path.parts[0]):
        return None
    return path.as_posix()


def iter_kml_documents(
    archive_bytes: bytes,
    archive_label: str,
    audit: Counter,
    *,
    depth: int = 0,
    expanded_budget: dict[str, int] | None = None,
) -> Iterator[tuple[str, bytes]]:
    """Yield bounded KML members from ZIP/KMZ containers without extraction."""
    if expanded_budget is None:
        expanded_budget = {"bytes": 0}
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile:
        audit["invalid_nested_archives_skipped"] += 1
        return
    with archive:
        members = archive.infolist()
        total_uncompressed = sum(info.file_size for info in members)
        if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ValueError(
                f"archive exceeds uncompressed safety cap: {archive_label} "
                f"({total_uncompressed} bytes)"
            )
        for info in members:
            audit["archive_entries_seen"] += 1
            if info.is_dir():
                continue
            expanded_budget["bytes"] += info.file_size
            if expanded_budget["bytes"] > MAX_CUMULATIVE_EXPANDED_BYTES:
                raise ValueError(
                    "nested archives exceed cumulative expanded-byte safety cap "
                    f"({expanded_budget['bytes']} bytes)"
                )
            member = safe_member_name(info.filename)
            if member is None:
                audit["unsafe_archive_paths_skipped"] += 1
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                audit["oversized_members_skipped"] += 1
                continue
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > MAX_COMPRESSION_RATIO:
                audit["high_ratio_members_skipped"] += 1
                continue
            suffix = PurePosixPath(member).suffix.lower()
            if suffix == ".url":
                audit["url_shortcut_entries_skipped"] += 1
                continue
            if suffix not in {".kml", ".kmz", ".zip"}:
                audit["non_kml_entries_ignored"] += 1
                continue
            data = archive.read(info)
            label = member if not archive_label else f"{archive_label}!{member}"
            if suffix == ".kml":
                audit["kml_documents_inspected"] += 1
                yield label, data
            elif depth < MAX_ARCHIVE_DEPTH:
                audit["nested_archives_inspected"] += 1
                yield from iter_kml_documents(
                    data,
                    label,
                    audit,
                    depth=depth + 1,
                    expanded_budget=expanded_budget,
                )
            else:
                audit["nested_archives_depth_limited"] += 1


def point_coordinate(placemark: ET.Element) -> tuple[str, float, float, float | None] | None:
    points = [node for node in placemark.iter() if local_name(node) == "Point"]
    if len(points) != 1:
        return None
    coordinate_nodes = [
        node for node in points[0].iter() if local_name(node) == "coordinates"
    ]
    if len(coordinate_nodes) != 1:
        return None
    coordinate_node = coordinate_nodes[0]
    raw = "" if coordinate_node is None else (coordinate_node.text or "").strip()
    if not raw:
        return None
    tokens = raw.split()
    if len(tokens) != 1:
        return None
    token = tokens[0]
    pieces = [piece.strip() for piece in token.split(",")]
    if len(pieces) < 2:
        return None
    longitude = number_or_none(pieces[0])
    latitude = number_or_none(pieces[1])
    altitude = number_or_none(pieces[2]) if len(pieces) > 2 else None
    if longitude is None or latitude is None:
        return None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None
    return token, latitude, longitude, altitude


def namespace_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def look_at_values(
    placemark: ET.Element,
) -> tuple[dict[str, float | str | None], dict[str, str], list[dict[str, str]]]:
    look_at = next((node for node in placemark.iter() if local_name(node) == "LookAt"), None)
    fields = ("longitude", "latitude", "altitude", "heading", "range", "tilt")
    if look_at is None:
        return (
            {**{field: None for field in fields}, "altitude_mode": ""},
            {**{field: "" for field in fields}, "altitude_mode": ""},
            [],
        )
    originals = {field: direct_text(look_at, field) for field in fields}
    children = [
        {
            "tag": local_name(child),
            "namespace": namespace_name(child.tag),
            "text": "".join(child.itertext()).strip(),
        }
        for child in list(look_at)
    ]
    altitude_modes = [
        child["text"] for child in children if child["tag"] == "altitudeMode"
    ]
    originals["altitude_mode"] = altitude_modes[0] if altitude_modes else ""
    values: dict[str, float | str | None] = {
        field: number_or_none(originals[field]) for field in fields
    }
    values["altitude_mode"] = originals["altitude_mode"]
    return values, originals, children


def walk_placemarks(root: ET.Element) -> Iterator[tuple[ET.Element, list[str]]]:
    def walk(node: ET.Element, folders: list[str]) -> Iterator[tuple[ET.Element, list[str]]]:
        node_name = local_name(node)
        next_folders = folders
        if node_name in {"Document", "Folder"}:
            folder_name = direct_text(node, "name")
            if folder_name:
                next_folders = folders + [folder_name]
        if node_name == "Placemark":
            yield node, folders
            return
        if node_name == "NetworkLink":
            return
        for child in list(node):
            yield from walk(child, next_folders)

    yield from walk(root, [])


def collection_is_crop_related(kml_label: str, root: ET.Element) -> bool:
    leaf = kml_label.split("!")[-1].rsplit("/", 1)[-1].lower()
    if leaf in PRIMARY_CROP_COLLECTIONS:
        return True
    collection_names = [
        direct_text(node, "name")
        for node in root.iter()
        if local_name(node) in {"Document", "Folder"}
    ]
    return any("crop circle collection" in normalized_text(name) for name in collection_names)


def priority_for(record: dict) -> tuple[int, str]:
    name = normalized_text(record["placemark_name"])
    context = normalized_text(
        " ".join(
            [record["placemark_name"], record["folder"], record["description_inert_text"]]
        )
    )
    latitude = record["latitude"]
    longitude = record["longitude"]
    if "darfield" in context:
        return 1, "darfield"
    if "panocchia" in context:
        return 2, "panocchia"
    if "house springs" in context or (
        38.35 <= latitude <= 38.45 and -90.68 <= longitude <= -90.56
    ):
        return 3, "house_springs_missouri"
    if "hexton" in context:
        return 4, "hexton"
    if "windmill" in context:
        return 5, "windmill_hill"
    if "hackpen" in context:
        return 6, "hackpen_hill"
    if "waden" in context or "jingjang" in name:
        return 7, "waden_hill"
    if any(place in context for place in ("barnsley", "dodworth", "ossett")) or (
        53.45 <= latitude <= 53.75 and -1.70 <= longitude <= -1.20
    ):
        return 8, "south_yorkshire_cluster"
    questioned = (
        "old or iffy" in context
        or "?" in record["placemark_name"]
        or any(
            token in context
            for token in ("possibly", "possible ", "iffy", "unfinished", "ghost", "once", "alien")
        )
    )
    if questioned:
        return 10, "old_iffy_or_questioned"
    return 9, "remaining_ordinary_crop_circle_placemark"


def confidence_for(record: dict) -> str:
    context = normalized_text(
        " ".join(
            [record["placemark_name"], record["folder"], record["description_inert_text"]]
        )
    )
    if "firefox" in context:
        return "tier_3_known_constructed_or_promotional"
    if (
        "old or iffy" in context
        or "?" in record["placemark_name"]
        or any(token in context for token in ("possibly", "possible ", "iffy", "unfinished", "ghost", "alien"))
    ):
        return "tier_3_questioned_or_iffy_legacy"
    if record["priority_rank"] <= 4:
        return "tier_1_named_specific_legacy"
    return "tier_2_named_or_cluster_legacy"


def haversine_m(first: dict, second: dict) -> float:
    latitude_1 = math.radians(first["latitude"])
    latitude_2 = math.radians(second["latitude"])
    delta_latitude = latitude_2 - latitude_1
    delta_longitude = math.radians(second["longitude"] - first["longitude"])
    half_chord = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(half_chord))


def add_duplicate_groups(records: list[dict]) -> list[dict]:
    parents = list(range(len(records)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        root_first = find(first)
        root_second = find(second)
        if root_first != root_second:
            parents[root_second] = root_first

    for first in range(len(records)):
        for second in range(first + 1, len(records)):
            if haversine_m(records[first], records[second]) <= DUPLICATE_RADIUS_M:
                union(first, second)

    grouped: dict[int, list[int]] = {}
    for index in range(len(records)):
        grouped.setdefault(find(index), []).append(index)

    summaries: list[dict] = []
    for indexes in grouped.values():
        if len(indexes) < 2:
            for index in indexes:
                records[index].update(
                    {
                        "possible_duplicate_group_id": "",
                        "possible_duplicate_group_size": 1,
                        "duplicate_group_method": "",
                        "duplicate_review_status": "not_applicable",
                    }
                )
            continue
        member_ids = sorted(records[index]["legacy_candidate_id"] for index in indexes)
        group_id = "ldup_" + hashlib.sha256("|".join(member_ids).encode("utf-8")).hexdigest()[:12]
        distances = [
            haversine_m(records[first], records[second])
            for position, first in enumerate(indexes)
            for second in indexes[position + 1 :]
        ]
        group_priority = min(records[index]["priority_rank"] for index in indexes)
        for index in indexes:
            record = records[index]
            if group_priority <= 8 and record["priority_rank"] > group_priority:
                record["priority_rank"] = group_priority
                record["priority_label"] = "inherited_from_possible_duplicate_group"
                record["priority_inherited_from_duplicate_group"] = True
            record.update(
                {
                    "possible_duplicate_group_id": group_id,
                    "possible_duplicate_group_size": len(indexes),
                    "duplicate_group_method": f"coordinate_proximity_{int(DUPLICATE_RADIUS_M)}m_review_required",
                    "duplicate_review_status": "unreviewed_do_not_merge",
                }
            )
        summaries.append(
            {
                "possible_duplicate_group_id": group_id,
                "member_candidate_ids": member_ids,
                "member_names": [records[index]["placemark_name"] for index in indexes],
                "member_count": len(indexes),
                "maximum_pair_distance_m": round(max(distances), 3),
                "method": f"coordinate_proximity_{int(DUPLICATE_RADIUS_M)}m_review_required",
                "review_status": "unreviewed_do_not_merge",
            }
        )
    return sorted(summaries, key=lambda group: group["possible_duplicate_group_id"])


def parse_kml_document(
    kml_label: str,
    payload: bytes,
    archive_filename: str,
    archive_sha256: str,
    audit: Counter,
) -> tuple[list[dict], dict]:
    kml_sha256 = sha256_bytes(payload)
    document_audit = {
        "kml_filename": kml_label,
        "kml_sha256": kml_sha256,
        "bytes": len(payload),
        "placemarks_seen": 0,
        "candidates_imported": 0,
        "network_links_skipped": 0,
        "href_nodes_not_loaded": 0,
        "active_xml_rejected": False,
    }
    if contains_active_xml(payload):
        audit["active_xml_documents_rejected"] += 1
        document_audit["active_xml_rejected"] = True
        return [], document_audit
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        audit["malformed_kml_documents_skipped"] += 1
        document_audit["malformed"] = True
        return [], document_audit

    network_links = len(descendants(root, "NetworkLink"))
    href_nodes = len(descendants(root, "href"))
    document_audit["network_links_skipped"] = network_links
    document_audit["href_nodes_not_loaded"] = href_nodes
    audit["network_links_skipped"] += network_links
    audit["href_nodes_not_loaded"] += href_nodes

    crop_collection = collection_is_crop_related(kml_label, root)
    records: list[dict] = []
    for placemark_index, (placemark, folder_path) in enumerate(walk_placemarks(root), start=1):
        document_audit["placemarks_seen"] += 1
        audit["placemarks_seen"] += 1
        name = direct_text(placemark, "name") or "Untitled Placemark"
        if not crop_collection and not CROP_NAME_RE.search(name):
            audit["irrelevant_placemarks_skipped"] += 1
            continue
        coordinate = point_coordinate(placemark)
        if coordinate is None:
            audit["crop_related_nonpoint_or_invalid_placemarks_skipped"] += 1
            continue
        coordinate_original, latitude, longitude, altitude = coordinate
        description_html = description_fragment(placemark)
        urls = url_strings(placemark, description_html)
        look_at, look_at_original, look_at_children = look_at_values(placemark)
        candidate_key = "|".join(
            [kml_sha256, str(placemark_index), name, coordinate_original]
        )
        record = {
            "legacy_candidate_id": "lkml_"
            + hashlib.sha256(candidate_key.encode("utf-8")).hexdigest()[:16],
            "source_archive_filename": archive_filename,
            "source_archive_sha256": archive_sha256,
            "original_kml_filename": kml_label,
            "original_kml_sha256": kml_sha256,
            "source_placemark_index": placemark_index,
            "placemark_name": name,
            "folder_path": folder_path,
            "folder": " / ".join(folder_path),
            "coordinate_original": coordinate_original,
            "latitude": latitude,
            "longitude": longitude,
            "altitude_m": altitude,
            "look_at": look_at,
            "look_at_original": look_at_original,
            "look_at_children": look_at_children,
            "description_inert_text": inert_description(description_html),
            "description_had_html": bool(re.search(r"<\s*[A-Za-z]", description_html)),
            "original_url_strings": urls,
            "remote_content_executed": False,
            "network_links_executed": False,
            "legacy_location_status": "legacy_exact_field_candidate",
            "review_status": "queued_unverified",
            "site_status": "candidate_field_only",
            "alignment_eligible": False,
            "overlay_eligible": False,
            "publication_eligible": False,
            "coordinate_accuracy_status": "legacy_point_precision_not_validated_accuracy",
            "coordinate_uncertainty_m": None,
            "priority_inherited_from_duplicate_group": False,
        }
        record["priority_rank"], record["priority_label"] = priority_for(record)
        record["confidence_tier"] = confidence_for(record)
        records.append(record)
        document_audit["candidates_imported"] += 1
        audit["candidates_imported"] += 1
        audit["url_strings_preserved_inert"] += len(urls)
    return records, document_audit


def validate_payload(payload: dict) -> None:
    if payload.get("schema_version") != "legacy-kml-candidate-source-v1":
        raise ValueError("unexpected legacy KML schema version")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    security_policy = payload.get("security_policy", {})
    for forbidden_execution in (
        "archive_extraction_performed",
        "network_links_executed",
        "url_shortcuts_executed",
        "remote_icons_loaded",
        "embedded_html_images_loaded",
        "external_urls_visited",
    ):
        if security_policy.get(forbidden_execution) is not False:
            raise ValueError(f"legacy import security gate must fail closed: {forbidden_execution}")
    if security_policy.get("offline_only") is not True:
        raise ValueError("legacy import must remain offline-only")

    candidate_policy = payload.get("candidate_policy", {})
    for forbidden_promotion in (
        "automatic_site_promotion",
        "automatic_overlay_creation",
        "automatic_alignment_eligibility",
        "automatic_publication_eligibility",
    ):
        if candidate_policy.get(forbidden_promotion) is not False:
            raise ValueError(f"legacy candidate promotion gate must fail closed: {forbidden_promotion}")
    if candidate_policy.get("possible_duplicate_groups_are_not_automatic_merges") is not True:
        raise ValueError("legacy proximity groups cannot be automatic merges")

    seen: set[str] = set()
    for record in candidates:
        candidate_id = record.get("legacy_candidate_id")
        if not candidate_id or candidate_id in seen:
            raise ValueError(f"duplicate or missing candidate id: {candidate_id!r}")
        seen.add(candidate_id)
        if record.get("legacy_location_status") != "legacy_exact_field_candidate":
            raise ValueError(f"candidate changed location class: {candidate_id}")
        if record.get("review_status") != "queued_unverified":
            raise ValueError(f"legacy candidate bypassed review queue: {candidate_id}")
        if record.get("site_status") != "candidate_field_only":
            raise ValueError(f"legacy candidate changed site status: {candidate_id}")
        for gate in ("alignment_eligible", "overlay_eligible", "publication_eligible"):
            if record.get(gate) is not False:
                raise ValueError(f"legacy candidate gate must fail closed: {candidate_id} {gate}")
        if record.get("remote_content_executed") is not False:
            raise ValueError(f"remote content execution is forbidden: {candidate_id}")
        if record.get("network_links_executed") is not False:
            raise ValueError(f"NetworkLink execution is forbidden: {candidate_id}")
        if "<img" in record.get("description_inert_text", "").lower():
            raise ValueError(f"description is not inert: {candidate_id}")
        latitude = record.get("latitude")
        longitude = record.get("longitude")
        if not isinstance(latitude, (int, float)) or not -90 <= latitude <= 90:
            raise ValueError(f"invalid latitude: {candidate_id}")
        if not isinstance(longitude, (int, float)) or not -180 <= longitude <= 180:
            raise ValueError(f"invalid longitude: {candidate_id}")

    summary = payload.get("summary", {})
    if summary.get("candidate_count") != len(candidates):
        raise ValueError("legacy candidate summary count does not match records")
    recomputed_zero_counts = {
        "accepted_site_count": sum(
            record.get("site_status") not in {"candidate_field_only"} for record in candidates
        ),
        "overlay_count": sum(bool(record.get("overlay_eligible")) for record in candidates),
        "alignment_eligible_count": sum(
            bool(record.get("alignment_eligible")) for record in candidates
        ),
        "publication_eligible_count": sum(
            bool(record.get("publication_eligible")) for record in candidates
        ),
    }
    for count_name, recomputed in recomputed_zero_counts.items():
        if summary.get(count_name) != recomputed or recomputed != 0:
            raise ValueError(f"legacy candidate summary gate is not zero: {count_name}")


def build_payload(archive_path: Path) -> dict:
    archive_size = archive_path.stat().st_size
    if archive_size > MAX_SOURCE_ARCHIVE_BYTES:
        raise ValueError(
            f"source archive exceeds safety cap: {archive_size} bytes"
        )
    archive_bytes = archive_path.read_bytes()
    archive_sha256 = sha256_bytes(archive_bytes)
    audit: Counter = Counter()
    records: list[dict] = []
    kml_documents: list[dict] = []
    for label, payload in iter_kml_documents(archive_bytes, "", audit):
        parsed, document_audit = parse_kml_document(
            label, payload, archive_path.name, archive_sha256, audit
        )
        records.extend(parsed)
        kml_documents.append(document_audit)

    duplicate_groups = add_duplicate_groups(records)
    for record in records:
        record["confidence_tier"] = confidence_for(record)
    records.sort(
        key=lambda record: (
            record["priority_rank"],
            record["confidence_tier"],
            normalized_text(record["placemark_name"]),
            record["legacy_candidate_id"],
        )
    )
    summary = {
        "candidate_count": len(records),
        "possible_duplicate_group_count": len(duplicate_groups),
        "possible_duplicate_member_count": sum(
            group["member_count"] for group in duplicate_groups
        ),
        "priority_counts": dict(
            sorted(Counter(str(record["priority_rank"]) for record in records).items())
        ),
        "confidence_tier_counts": dict(
            sorted(Counter(record["confidence_tier"] for record in records).items())
        ),
        "accepted_site_count": 0,
        "overlay_count": 0,
        "alignment_eligible_count": 0,
        "publication_eligible_count": 0,
    }
    payload = {
        "schema_version": "legacy-kml-candidate-source-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {
            "archive_filename": archive_path.name,
            "archive_size_bytes": len(archive_bytes),
            "archive_sha256": archive_sha256,
            "source_classification": "user_supplied_legacy_coordinate_candidates_unverified",
            "rights_status": "unknown_not_cleared_for_redistribution",
        },
        "security_policy": {
            "offline_only": True,
            "archive_extraction_performed": False,
            "network_links_executed": False,
            "url_shortcuts_executed": False,
            "remote_icons_loaded": False,
            "embedded_html_images_loaded": False,
            "external_urls_visited": False,
            "descriptions_stored_as_inert_text": True,
            "url_strings_preserved_as_inert_data": True,
            "maximum_archive_depth": MAX_ARCHIVE_DEPTH,
            "maximum_source_archive_bytes": MAX_SOURCE_ARCHIVE_BYTES,
            "maximum_member_bytes": MAX_MEMBER_BYTES,
            "maximum_archive_uncompressed_bytes": MAX_ARCHIVE_UNCOMPRESSED_BYTES,
            "maximum_cumulative_expanded_bytes": MAX_CUMULATIVE_EXPANDED_BYTES,
        },
        "candidate_policy": {
            "location_status": "legacy_exact_field_candidate",
            "automatic_site_promotion": False,
            "automatic_overlay_creation": False,
            "automatic_alignment_eligibility": False,
            "automatic_publication_eligibility": False,
            "coordinate_precision_is_not_accuracy": True,
            "possible_duplicate_groups_are_not_automatic_merges": True,
        },
        "summary": summary,
        "audit": dict(sorted(audit.items())),
        "kml_documents": sorted(kml_documents, key=lambda document: document["kml_filename"]),
        "possible_duplicate_groups": duplicate_groups,
        "candidates": records,
    }
    validate_payload(payload)
    return payload


CSV_FIELDS = [
    "legacy_candidate_id",
    "priority_rank",
    "priority_label",
    "confidence_tier",
    "placemark_name",
    "latitude",
    "longitude",
    "altitude_m",
    "coordinate_original",
    "coordinate_accuracy_status",
    "coordinate_uncertainty_m",
    "folder",
    "original_kml_filename",
    "original_kml_sha256",
    "source_archive_filename",
    "source_archive_sha256",
    "possible_duplicate_group_id",
    "possible_duplicate_group_size",
    "duplicate_group_method",
    "duplicate_review_status",
    "look_at_heading",
    "look_at_range",
    "look_at_tilt",
    "description_inert_text",
    "original_url_strings_json",
    "legacy_location_status",
    "review_status",
    "site_status",
    "alignment_eligible",
    "overlay_eligible",
    "publication_eligible",
]


def write_outputs(payload: dict, json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for record in payload["candidates"]:
        row = {field: record.get(field, "") for field in CSV_FIELDS}
        row["look_at_heading"] = record["look_at"]["heading"]
        row["look_at_range"] = record["look_at"]["range"]
        row["look_at_tilt"] = record["look_at"]["tilt"]
        row["original_url_strings_json"] = json.dumps(
            record["original_url_strings"], ensure_ascii=False
        )
        writer.writerow(row)

    temporary_paths: list[Path] = []
    try:
        for destination, content in (
            (json_path, json_text),
            (csv_path, csv_buffer.getvalue()),
        ):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                delete=False,
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_paths.append(Path(handle.name))
        temporary_paths[0].replace(json_path)
        temporary_paths[1].replace(csv_path)
        temporary_paths.clear()
    finally:
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload(args.archive)
    write_outputs(payload, args.output_json, args.output_csv)
    summary = payload["summary"]
    print(
        json.dumps(
            {
                "archive_sha256": payload["source"]["archive_sha256"],
                "candidate_count": summary["candidate_count"],
                "possible_duplicate_group_count": summary[
                    "possible_duplicate_group_count"
                ],
                "accepted_site_count": summary["accepted_site_count"],
                "overlay_count": summary["overlay_count"],
                "network_links_skipped": payload["audit"].get(
                    "network_links_skipped", 0
                ),
                "url_shortcut_entries_skipped": payload["audit"].get(
                    "url_shortcut_entries_skipped", 0
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
