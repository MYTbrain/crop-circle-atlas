from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["url", "retrieved_at", "http_status", "sha256", "bytes", "cache_path"]


def read_rows(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    primary_path = ROOT / "data" / "source_snapshots.csv"
    iccra_path = ROOT / "data" / "iccra_snapshots_full.csv"
    expansion_path = ROOT / "data" / "source_expansion_crawl_manifest.csv"
    rows_by_url = {}
    order = []
    for row in read_rows(primary_path) + read_rows(iccra_path) + read_rows(expansion_path):
        url = (row.get("url") or "").strip()
        if not url:
            continue
        if url not in rows_by_url:
            order.append(url)
        normalized = {field: row.get(field, "") for field in FIELDS}
        normalized["cache_path"] = row.get("cache_path") or row.get("local_path") or ""
        rows_by_url[url] = normalized
    with primary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows_by_url[url] for url in order)
    successes = sum(1 for row in rows_by_url.values() if str(row["http_status"]).startswith("2"))
    print(f"snapshots={len(rows_by_url)} successful={successes} failed={len(rows_by_url) - successes}")


if __name__ == "__main__":
    main()
