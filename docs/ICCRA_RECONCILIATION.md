# ICCRA Archive Reconciliation

Generated: `2026-07-21T07:39:04Z`

Status: **index_inventory_complete_with_unavailable_detail_pages**. Index inventory and detail-page availability are reported independently.

## Exact totals

- By-year index stated total: **559** formations.
- By-year list/direct occurrences parsed: **559**.
- Count-only year placeholders: **2** (the index states a count but supplies no year listing/link).
- By-state page stated sum: **595** reports.
- By-state list items actually parsed: **601** (567 linked; 34 unlinked).
- Canonical assertions after cross-index reconciliation: **607**.
- Unique formation-detail URLs: **579** (571 successful; 8 failed URL variants).
- Index entries still lacking a successful detail page: **2**.

## Enrichment evidence

- Actual coordinate pairs: **4** assertions; coordinate/GPS context without necessarily containing a pair: **6**.
- North/bearing/orientation evidence: **22** assertions.
- Non-navigation image references: **681** across **548** unique URLs.
- ICCRA-hosted image references fetched successfully: **669 / 675**.
- Image public redistribution status: **not cleared**; cached files are research inputs only.

## Count mismatches preserved from ICCRA

### By year

| Year | Index stated | Parsed list/direct | Delta |
|---:|---:|---:|---:|
| 1950 | 1 | 0 | -1 |
| 1960 | 1 | 0 | -1 |
| 1996 | 31 | 32 | +1 |
| 1998 | 23 | 24 | +1 |

### By state

| State | Page stated | Parsed list items | Delta |
|---|---:|---:|---:|
| California | 25 | 27 | +2 |
| Illinois | 23 | 22 | -1 |
| Ohio | 41 | 44 | +3 |
| Pennsylvania | 22 | 21 | -1 |
| South Dakota | 6 | 7 | +1 |
| Washington | 20 | 21 | +1 |
| Wyoming | 1 | 2 | +1 |

## Unresolved linked entries

- `404` — Mount Airy, Surry County, NC (August 19, 1965) — https://iccra.org/bystate/North%20Carolina/ICCRA%20-%20NC%20-%20Mount%20Airy,%20Surry%20County%20(August%2019,%201965).htm
- `404` — August 19, 1965 - Mount Airy, Surry County, NC — https://iccra.org/bystate/North%20Carolina/ICCRA%20-%20NC%20-%20Mount%20Airy,%20Surry%20County%20(August%2019,%201965).htm

The machine-readable reconciliation, including every failed URL variant and every unlinked list item, is in `data/iccra_reconciliation.json`.
