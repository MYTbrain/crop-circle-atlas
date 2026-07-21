# Source register and crawl stop decision

Evaluated 2026-07-20. The crawl stops when another search pass yields no open,
machine-readable event catalog that materially expands the canonical entity
count, while newly found sources mostly add reports, measurements, photographs,
or commentary to already-known formations.

| Source | Approximate scope | Unique value | Current treatment |
|---|---:|---|---|
| Crop Circle Center | 7,152 listed records, historical through 2026 | Broadest event backbone and diagrams | 309-page supplied catalog plus 2010-2026 monthly pages ingested |
| ICCRA | 457 parsed US assertions | County/state detail and direct field-report links | Ingested and merged conservatively; US priority source |
| Crop Circle Connector | Public 2014-2026 seasons; older picture archive membership-gated | Current-season cross-checks, aerial photographs, field access notes | Season indexes cached; images not copied because rights remain with contributors |
| Crop Circle Research Archive | About 2,850 formations and nearly 17,000 linked items | Surveys, first-hand reports, science, correspondence, ~8,000 photos | High-value enrichment target; database is not exposed as an open bulk table |
| BLT Research | More than 100 plant/soil lab reports | Physical measurement enrichment | Register and link at formation level; not a bulk event catalog |
| Dutch Crop Circle Archive (DCCA) | Netherlands and international archive | Dutch reports and literature with attribution terms | Enrichment backlog; expected event overlap is high |
| Paul Vigay archive | Articles and field reports | Contemporary UK analysis and historical context | Enrichment backlog |
| CCCRN mirror | Canadian news and formation reports | Canada-specific detail | Enrichment backlog; high overlap with backbone dates/places |
| CropDecoder | 4,739 records through 2024 | Classification and node-anomaly claims | Public UI evaluated; `/api/` is disallowed by robots.txt and was not crawled |
| Project Argus appendix | 1992 Great Britain table | Historical dates/locations | Useful validation sample, not a net-new large catalog |
| GeoNames | Worldwide places plus full US feature file | Reproducible offline locality centroids | Used for approximate mapping under CC BY 4.0 |

## Measured return

- Primary ingestion: 7,600 source assertions became 7,160 distinct entities.
- 3,831 entities received an approximate locality-centroid coordinate.
- 814 entities are US reports; 721 of those currently have a mappable centroid.
- The second discovery pass found valuable evidence archives, but no additional
  openly crawlable event table larger than the current 7,160-entity catalog.

The next high-return work is not another indiscriminate crawl. It is targeted
enrichment: exact field coordinates, licensed aerial images, field-report
measurements, and reviewed true-north orientations for formations with straight
components.

