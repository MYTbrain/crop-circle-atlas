# Crop Circle Atlas

A provenance-first catalog and geospatial workbench for reported crop
formations. This build combines a user-supplied 309-page Crop Circle Center
catalog, current Crop Circle Center listings, an exhaustive reconciliation of
the US-focused ICCRA archive, and bounded public metadata passes over Crop
Circle Connector, DCCA, Paul Vigay's field-report index, and the CCCRN mirror.

**Live atlas:** https://mytbrain.github.io/crop-circle-atlas/

## Current build

- 8,390 source assertions resolved into 7,749 conservative catalog entities.
  Near matches remain separate, so this is not a claim of 7,749 physically
  distinct formations.
- 4,027 mapped entities: 4,023 labeled GeoNames locality centroids and four
  source-reported ICCRA coordinates, all with method and uncertainty.
- 953 United States entities, plus one Puerto Rico record retained separately.
- The bounded expansion contributes 639 metadata assertions. It contains 189
  exact baseline-key overlaps and 450 new normalized source keys; the latter
  are not claimed as 450 proven-new formations. Another 167 alias and 83
  probable overlaps remain explicitly unmerged for review.
- Every 1,169 parsed ICCRA index occurrence and two count-only placeholders is
  accounted for in 607 canonical assertions. One indexed entity, Mount Airy,
  North Carolina (1965), has no surviving detail page because its ICCRA URL
  returns 404.
- 681 non-navigation ICCRA image references inventoried. All 669 successfully
  cached hosted images (526 unique SHA-256 values) were analyzed privately;
  six external references were not fetched and six hosted URLs returned 404.
  The public review queue is metadata-only because publication rights have not
  been cleared. Its 157 high, 85 medium, and 86 low row-level tiers are
  unvalidated review priorities, not confirmed straight components.
- All 5,978 supplied catalog diagrams analyzed for straight components: 974
  high, 344 medium, 1,925 low, and 2,735 none. On a 104-item internal
  convenience sample from six selected pages, the high-or-medium threshold
  measured 88.89% precision and 64.86% recall; retaining all candidate tiers
  measured 91.89% recall. This is pipeline QA, not random out-of-sample
  validation.
- Five evidence-qualified local true-north observations across three
  formations. Their five long-distance extensions are clearly labeled
  experimental: 16 catalog points enter a centerline corridor, but none passes
  the declared coordinate-and-bearing uncertainty gate. Diagram angles remain
  image-space measurements and never become geographic bearings without
  independent orientation evidence.
- The perspective-correct registration and GroundOverlay pipeline is complete,
  but the public KMZ contains zero ICCRA image overlays because publication
  rights have not been cleared. Local-only registration remains available.

## Products

- `data/formations.csv`: canonical formation entities.
- `data/source_assertions.csv`: loss-minimizing source statements.
- `data/source_expansion_assertions.csv`: bounded metadata expansion, with
  non-merged overlap status and source geography preserved.
- `data/iccra_index_entries_full.csv`: every ICCRA index occurrence and its
  assertion mapping.
- `data/straight_component_candidates.csv`: automated diagram review queue.
- `data/iccra_image_straight_candidates.csv`: metadata-only, unvalidated ICCRA
  source-image review queue; no source or derived pixels are included.
- `data/orientation_observations.csv`: human-reviewed true-north bearings.
- `data/alignment_hits.csv`: centerline corridor hits with coordinate and
  bearing-uncertainty eligibility fields.
- `web/`: static interactive atlas plus a local-only perspective-correct image
  registration lab.
- `exports/crop_circle_atlas.kml` and `.kmz`: Google Earth points, experimental
  extensions from reviewed local orientations, and only rights-cleared
  registered overlays.
- `outputs/initial-build/crop_circle_atlas.xlsx`: research workbook.

## Scientific boundary

A mapped point is a report location, not proof of cause or an exact field. Ray
hits are exploratory. Archive coverage, repeated reporting, field and road
geometry, settlement density, coordinate error, angular error, and multiple
testing can all create apparent alignments. No current output is a validated
prediction of past or future crop formations.

## Rebuild

```powershell
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts/fetch_sources.ps1
powershell -ExecutionPolicy Bypass -File scripts/fetch_iccra_full.ps1
python scripts/parse_iccra_full.py
python scripts/source_expansion.py
python scripts/detect_straight_components.py --pdf "C:\path\to\COMBINED.pdf"
python scripts/detect_iccra_image_straight_components.py
python scripts/build_dataset.py --pdf "C:\path\to\COMBINED.pdf"
python scripts/merge_snapshots.py
python scripts/generate_kml.py
$env:NODE_OPTIONS='--max-old-space-size=8192'
node scripts/build_workbook.mjs
python scripts/verify.py
python -m http.server 8000 --directory web
```

Open <http://localhost:8000>. Raw source caches are excluded from Git. Public
tables preserve URLs, hashes, retrieval timestamps, methods, and rights status.

See `docs/METHODOLOGY.md`, `docs/ICCRA_RECONCILIATION.md`,
`docs/SOURCE_EXPANSION.md`, and `docs/IMAGE_GEOREFERENCING.md` for the evidence,
access, and qualification rules.

## Scope boundary

This is a strong initial corpus, not yet a literal repository of every crop
formation record on the web. Six archive families currently contribute event
assertions: Crop Circle Center, ICCRA, Crop Circle Connector, DCCA, Paul Vigay's
archive, and the CCCRN mirror. Other high-value holdings remain permission-,
membership-, robots-, DNS-, or interface-limited. The accessible expansion
showed sharply lower yield at Vigay/CCCRN after the Connector and DCCA indexes,
but 450 new normalized keys means global diminishing returns have not been
proved. The source register states each boundary rather than implying complete
coverage of inaccessible holdings.
