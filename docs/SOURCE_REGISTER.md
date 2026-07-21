# Source register and current crawl boundary

Evaluated 2026-07-21. Ten catalog/reference sources are registered and a Project
Argus appendix was also evaluated. Six archive families now contribute event
assertions. The crawl is paused at a practical access boundary, not declared
globally exhaustive: several holdings require permission, membership,
robots-compliant access, a working host, or a permitted structured interface.

| Source | Approximate scope | Unique value | Current treatment |
|---|---:|---|---|
| Crop Circle Center | 7,152 listed records, historical through 2026 | Broadest event backbone and diagrams | 309-page supplied catalog plus 2010-2026 monthly pages ingested |
| ICCRA | 607 canonical assertions from 1,171 index rows; 681 non-UI image references | County/state detail, reports, coordinates, orientation evidence, and aerial images | All parsed index occurrences reconciled; one entity has only a dead detail URL; images are link-only pending rights |
| Crop Circle Connector | Public 2014-2026 seasons; older picture archive membership-gated | Current-season cross-checks, aerial photographs, field access notes | 442 metadata assertions ingested from 447 event-like anchors; five exclusions documented; images not copied |
| Crop Circle Research Archive | About 2,850 formations and nearly 17,000 linked items | Surveys, first-hand reports, science, correspondence, ~8,000 photos | High-value enrichment target; database is not exposed as an open bulk table |
| BLT Research | More than 100 plant/soil lab reports | Physical measurement enrichment | DNS unavailable in the reproducible pass; failed closed; not treated as a bulk event catalog |
| Dutch Crop Circle Archive (DCCA) | Netherlands and international archive | Dutch reports and literature with attribution terms | 184 dated metadata assertions ingested; source geography and numbered event designators preserved; images excluded |
| Paul Vigay archive | Articles and field reports | Contemporary UK analysis and historical context | 12 dated field-report index assertions ingested; articles and images excluded |
| CCCRN mirror | Canadian news and formation reports | Canada-specific detail | One explicit single-event occurrence assertion ingested; newsletter dates never substituted |
| CropDecoder | 4,739 records through 2024 | Classification and node-anomaly claims | Public UI evaluated; `/api/` is disallowed by robots.txt and was not crawled |
| Project Argus appendix | 1992 Great Britain table | Historical dates/locations | Useful validation sample, not a net-new large catalog |
| GeoNames | Worldwide places plus full US feature file | Reproducible offline locality centroids | Used for approximate mapping under CC BY 4.0 |

## Measured return

- Current ingestion: 8,390 source assertions became 7,745 conservative catalog
  entities after four evidence-reviewed report aliases were accepted and
  merged; this is not a claim of 7,745 physically distinct formations. All
  source assertions remain preserved.
- Location evidence is separated into eight field candidates/sites, 4,017
  locality references, and 3,720 unresolved entities. The locality references
  are search aids, not claimed formation fields.
- 949 entities are US reports; one Puerto Rico record is retained separately.
- ICCRA reconciliation covers all 1,169 parsed index occurrences plus two
  count-only placeholders. Its by-year index states and parses 559 occurrences;
  state pages state 595 but contain 601 actual list items.
- The ICCRA image inventory contains 681 references across 548 unique URLs.
  Of these, 669 hosted rows were cached and analyzed privately (526 unique
  SHA-256 values), six external references were not fetched, and six hosted
  references returned 404. Public analysis is metadata-only and redistribution
  is not cleared.
- The bounded expansion emitted 639 assertions from four additional archives:
  442 Connector, 184 DCCA, 12 Vigay, and one CCCRN. There are 189 exact
  normalized-key overlaps and 450 new normalized source keys. The latter are
  not confirmed-new formations; 167 alias candidates and 83 probable overlaps
  remain deliberately unmerged. The 127-request manifest records 121 successes
  and six failed/unavailable requests, with zero images or membership/API calls.
- The later accessible sources yielded only 13 assertions after Connector and
  DCCA, but high-value inaccessible holdings remain. The Crop Circle Research
  Archive advertises roughly 2,850 formations/17,000 linked items, and
  CropDecoder advertises 4,739 classified records; neither is presently a
  permitted bulk input.

The next high-return work is permission/API acquisition plus targeted parsers,
followed by the US-first field-resolution campaign, licensed aerial images,
field-report measurements, and reviewed true-north orientations. Exact fields
are not considered complete: unresolved reports remain unresolved until
repeatable evidence supports a stronger location status.
