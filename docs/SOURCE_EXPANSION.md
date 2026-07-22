# Bounded source-expansion pass

Evaluated 2026-07-21. This is a reproducible, rights-aware metadata pass, not a
claim that every crop-circle archive on the web has been exhausted.

## Result

| Source | Assertions | Exact normalized-key overlaps | New normalized source keys | Boundary |
|---|---:|---:|---:|---|
| Crop Circle Connector, public 2014-2026 season indexes | 442 | 103 | 339 | Membership archive and all images excluded |
| Dutch Crop Circle Archive linked year tables | 184 | 83 | 101 | Dated machine-enumerable rows only; images excluded |
| CCCRN newsletter mirror | 1 | 1 | 0 | Only an explicit single-event occurrence date; newsletter dates are never substituted |
| Paul Vigay field-report index | 12 | 3 | 9 | Dated field-report index rows only; articles/images excluded |
| BLT Research | 0 | 0 | 0 | DNS was unavailable to the reproducible local fetch; registered as enrichment, not invented as events |
| **Total** | **639** | **190** | **449** | 639 distinct normalized source keys |

The 449 new normalized source keys are not asserted to be 449 proven-new
formations. Of the 639 assertions, 167 have a documented alias-overlap candidate
and 83 have a probable overlap; neither class is auto-merged. Source place,
region, country, and occurrence designators such as `(1)`, `(2)`, `(1C)`, and
`(2S)` are preserved. Only 190 exact normalized-key matches merge automatically.

The Connector coverage inventory found 447 unique event-like anchors: 442 were
emitted and five were explicitly excluded for missing a usable occurrence date
or locality. DCCA emitted 184 dated rows, including two edge cases recovered
from a cross-border compact label and an externally linked report.

## Access and rights controls

- Connector robots.txt allowed the evaluated paths and disallowed `/forum/`;
  no forum, API, membership, or image request was made.
- DCCA and UFOBC returned no robots file (HTTP 404), which is recorded as
  “missing, no declared restrictions,” not as affirmative licensing.
- Vigay robots.txt allowed crawling; only the field-report index metadata was
  parsed.
- BLT robots and page requests failed closed because DNS was unavailable.
- The 127-row crawl manifest records request status, byte count, SHA-256, and
  private cache path. It contains 121 successful requests and six failed or
  unavailable requests. Images downloaded: zero.

## Reproduction and clean-clone behavior

The repository commits the derived CSV/JSON outputs but intentionally ignores
raw third-party HTML under `data/raw/`. A clean clone can consume the committed
`data/source_expansion_assertions.csv` directly through `build_dataset.py`.

To regenerate the expansion artifacts, first run:

```powershell
python scripts/source_expansion.py
```

After the private HTML cache exists, an offline deterministic parse is:

```powershell
python scripts/source_expansion.py --parse-only
```

`--parse-only` fails before writing anything if any required cached page is
missing, outside the private cache root, or differs from the manifest byte count
or SHA-256. The current assertion CSV SHA-256 is
`d0aee1fcb2e0aab3b4c5248b5621ead895d48ef3bb00cefb4ad0e01dfa4bb4e5`.

Auditable outputs:

- `data/source_expansion_assertions.csv`
- `data/source_expansion_access.csv`
- `data/source_expansion_crawl_manifest.csv`
- `data/source_expansion_parse_exclusions.csv`
- `data/source_expansion_reconciliation.json`
