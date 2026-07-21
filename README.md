# Crop Circle Atlas

An open, provenance-first catalog and geospatial workbench for reported crop
formations. The initial build combines a 309-page Crop Circle Center catalog
supplied by the project owner, current Crop Circle Center listings, and the
US-focused ICCRA archive.

## What this build does

- preserves every source assertion before entity merging;
- prioritizes ICCRA's county-level US records;
- assigns approximate locality centroids from GeoNames, never fabricated field
  coordinates;
- exports CSV, GeoJSON, KML, KMZ, and a research workbook;
- provides an interactive satellite/street map, search, filters, local-image
  overlay placement, and an experimental bearing-alignment lab;
- keeps directional-shape detection separate from geographic orientation.

## Scientific interpretation

A point on the map is a report location, not proof of origin or cause. A
locality-centroid geocode can be many kilometres from the actual field. A line
projection is created only when an orientation observation includes an azimuth
relative to true north and its method/uncertainty. Apparent alignments are
hypotheses; clustered reporting, roads, field geometry, population, archive
coverage, and multiple-testing can all create false positives.

## Rebuild

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/fetch_sources.ps1
python scripts/build_dataset.py --pdf "C:\path\to\COMBINED.pdf"
python scripts/generate_kml.py
python scripts/verify.py
python -m http.server 8000 --directory web
```

Open <http://localhost:8000>. The raw web cache is excluded from Git; the
normalized outputs retain URLs, hashes, and retrieval timestamps.

## Main outputs

- `data/formations.csv`: canonical formation entities.
- `data/source_assertions.csv`: loss-minimizing source records.
- `data/source_snapshots.csv`: retrieval provenance and hashes.
- `data/orientation_observations.csv`: reviewed bearings only.
- `web/data/formations.geojson`: browser map layer.
- `exports/crop_circle_atlas.kml` and `.kmz`: Google Earth layers.
- `docs/METHODOLOGY.md`: field definitions and statistical safeguards.

