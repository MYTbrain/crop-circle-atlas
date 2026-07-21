#!/usr/bin/env python3
"""Inventory cached ICCRA pages for geographic-orientation evidence.

This is a candidate finder, not an azimuth generator.  It records source text
that combines directional language and, where available, coordinates.  A human
review is still required before adding a row to orientation_observations.csv.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "data" / "iccra_snapshots_full.csv"
OUTPUT = ROOT / "data" / "orientation_evidence_candidates.csv"
SUMMARY = ROOT / "outputs" / "straight-components" / "orientation_evidence_scan.json"

DIRECTION = r"(?:true\s+north|magnetic\s+north|north|south|east|west|cardinal|N\s*/\s*S|E\s*/\s*W|NE|NW|SE|SW|E\s*/\s*NE|W\s*/\s*SW)"
ORIENTATION_PATTERNS = [
    re.compile(rf"(?i)\b(?:oriented|aligned|alignment|axis|facing)\b.{{0,120}}\b{DIRECTION}\b"),
    re.compile(rf"(?i)\b{DIRECTION}\b.{{0,120}}\b(?:oriented|aligned|alignment|axis|facing)\b"),
    re.compile(rf"(?i)\b(?:straight\s+)?pathways?\b.{{0,140}}\b{DIRECTION}\b"),
    re.compile(rf"(?i)\b{DIRECTION}\b.{{0,140}}\b(?:straight\s+)?pathways?\b"),
    re.compile(r"(?i)\bcardinal\s+(?:directions?|points?)\b"),
    re.compile(r"(?i)\b(?:due\s+)?(?:north|south|east|west)\s*\(magnetic\)"),
]
COORDINATE_PATTERNS = [
    re.compile(r"(?i)\b(?:GPS|latitude|longitude|coordinates?)\b.{0,180}\b\d{2,3}\D{0,5}\d{1,2}(?:\.\d+)?\D{0,18}[NSEW]\b"),
    re.compile(r"(?i)\blocation\s*:.{0,160}\b\d{2,3}\D{0,5}\d{1,2}(?:\.\d+)?\D{0,18}[NSEW]\b"),
]


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def decode_html(path: Path) -> str:
    payload = path.read_bytes()
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            source = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    parser = VisibleTextParser()
    parser.feed(source)
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


def snippets(text: str, patterns: list[re.Pattern[str]], limit: int = 8) -> list[str]:
    results: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            snippet = text[max(0, match.start() - 100) : min(len(text), match.end() + 100)].strip()
            if snippet not in results:
                results.append(snippet)
            if len(results) >= limit:
                return results
    return results


def main() -> int:
    if not SNAPSHOTS.exists():
        raise SystemExit(f"Snapshot manifest not found: {SNAPSHOTS}")
    with SNAPSHOTS.open(encoding="utf-8-sig", newline="") as handle:
        snapshots = list(csv.DictReader(handle))

    rows: list[dict[str, str]] = []
    html_success = 0
    missing_cache = 0
    for snapshot in snapshots:
        cache_path = ROOT / snapshot["cache_path"]
        if snapshot["http_status"] != "200" or cache_path.suffix.lower() not in {".htm", ".html"}:
            continue
        html_success += 1
        if not cache_path.exists():
            missing_cache += 1
            continue
        text = decode_html(cache_path)
        orientation = snippets(text, ORIENTATION_PATTERNS)
        coordinates = snippets(text, COORDINATE_PATTERNS)
        if not orientation and not coordinates:
            continue
        identity = f"{snapshot['url']}|{snapshot['sha256']}"
        priority = "high" if orientation and coordinates else "medium" if orientation else "coordinate_only"
        rows.append(
            {
                "evidence_candidate_id": "oe_" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16],
                "url": snapshot["url"],
                "roles": snapshot["roles"],
                "sha256": snapshot["sha256"],
                "cache_path": snapshot["cache_path"],
                "orientation_signal": " || ".join(orientation),
                "coordinate_signal": " || ".join(coordinates),
                "has_orientation_signal": "yes" if orientation else "no",
                "has_coordinate_signal": "yes" if coordinates else "no",
                "priority": priority,
                "review_status": "pending_human_review",
                "caveat": "candidate text only; not a qualified true-north azimuth",
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "evidence_candidate_id", "url", "roles", "sha256", "cache_path",
        "orientation_signal", "coordinate_signal", "has_orientation_signal",
        "has_coordinate_signal", "priority", "review_status", "caveat",
    ]
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": utc_now(),
        "snapshot_manifest": str(SNAPSHOTS.relative_to(ROOT)).replace("\\", "/"),
        "snapshots_total": len(snapshots),
        "http_200_html_pages": html_success,
        "missing_cache_files": missing_cache,
        "candidate_pages": len(rows),
        "priority_counts": dict(sorted(Counter(row["priority"] for row in rows).items())),
        "qualified_rows_created_automatically": 0,
        "reason": "all geographic azimuth rows require human evidence review",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
