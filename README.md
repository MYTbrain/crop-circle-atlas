# Crop Circle Atlas

A provenance-first catalog and geospatial workbench for reported crop
formations. This build combines a user-supplied 309-page Crop Circle Center
catalog, current Crop Circle Center listings, an exhaustive reconciliation of
the US-focused ICCRA archive, and bounded public metadata passes over Crop
Circle Connector, DCCA, Paul Vigay's field-report index, and the CCCRN mirror.

**Live atlas:** https://mytbrain.github.io/crop-circle-atlas/

## Exact-field geolocator MVP

The repository now includes a local, fail-closed exact-field research worker under `services/geolocator/` and an integrated reviewer at `web/geolocation-review.html`. It searches only bounded polygons, normalizes historical imagery metadata, generates physical tiles, ranks candidates, proposes SIFT/RANSAC registrations, validates independent checkpoints in metres, persists explicit human decisions, and generates rights-gated local KML/KMZ overlays. Machine output never mutates canonical atlas coordinates.

Start with [setup](docs/GEOLOCATOR_SETUP.md), then read the [architecture](docs/GEOLOCATOR_ARCHITECTURE.md), [evidence rules](docs/GEOLOCATOR_EVIDENCE_RULES.md), [benchmark](docs/GEOLOCATOR_BENCHMARK.md), and [license audit](docs/GEOLOCATOR_LICENSES.md). The benchmark currently proves synthetic mathematics only; it does not establish real-world crop-circle geolocation effectiveness.

## Current build

- 8,391 source assertions resolved into 7,745 conservative catalog entities
  after four evidence-reviewed report aliases were merged. Near matches remain
  separate, so this is not a claim of 7,745 physically distinct formations.
- Location evidence is separated by role: 407 field candidates/sites,
  3,894 labeled locality references, and 3,444 unresolved entities. Nineteen of the
  field-level records are explicit reviewed overrides; 384 more are publisher
  map targets retained as non-accepted candidate fields. A locality reference
  supports discovery and search; it is not presented as the field.
- 949 United States entities, plus one Puerto Rico record retained separately.
- The bounded expansion contributes 639 metadata assertions. It contains 190
  exact baseline-key overlaps and 449 new normalized source keys; the latter
  are not claimed as 449 proven-new formations. Another 167 alias and 83
  probable overlaps remain explicitly unmerged for review.
- Every 1,169 parsed ICCRA index occurrence and two count-only placeholders is
  accounted for in 607 canonical assertions. One indexed entity, Mount Airy,
  North Carolina (1965), has no surviving detail page because its ICCRA URL
  returns 404.
- The normalized per-report archive exposes 7,889 unique image links across
  1,913 reports, represented by 8,042 formation-image relationships. Of those,
  512 belong to US reports, 7,313 to known non-US reports, and 64 still lack a
  country assignment. The 7,398 global publisher links were enumerated from
  report pages but their image URLs were not independently fetched; they are
  explicitly counted as unverified, rights-gated links rather than copied
  images or registered overlays. Eleven Wikimedia Commons relationships are
  open-license records. The underlying ICCRA crawl
  inventoried 681 non-navigation references; all 669 successfully cached hosted
  rows (526 unique SHA-256 values) were analyzed privately, six external
  references were not fetched, and six hosted URLs returned 404. The public
  review queue is metadata-only because publication rights have not been
  cleared. Its 157 high, 85 medium, and 86 low row-level tiers are unvalidated
  review priorities, not confirmed straight components.
- All 5,978 supplied catalog diagrams analyzed for straight components: 974
  high, 344 medium, 1,925 low, and 2,735 none. On a 104-item internal
  convenience sample from six selected pages, the high-or-medium threshold
  measured 88.89% precision and 64.86% recall; retaining all candidate tiers
  measured 91.89% recall. This is pipeline QA, not random out-of-sample
  validation.
- Five evidence-qualified local true-north observations across three
  formations. Their five long-distance extensions are clearly labeled
  experimental. The earlier 16 corridor matches came from rough locality
  centroids and are now excluded; accepted rays tested against the two currently
  alignment-eligible sites produce zero corridor matches. The other 20
  candidates/sites are excluded by the quality gate. Diagram angles remain
  image-space measurements and never become geographic bearings without
  independent orientation evidence.
- The perspective-correct registration and GroundOverlay pipeline is complete,
  but the public KMZ packages zero image files. The web map and KML/KMZ contain
  twenty-two opt-in,
  source-hosted placements: Whiskey Hill/Hubbard 1998 and 2000,
  Wausau 1997, Mayville/Kekoskee 2003, Howell Township 2003, Jupiter 2005,
  Wavra Farm 1997, both Rockville 2003 formations, Miamisburg 2004,
  Hopewell/Chillicothe 2012, Albion/Starr 2002, and nine openly licensed
  same-flight frames of the Diessenhofen, Switzerland formation of 2008-07-15.
  Wausau uses a contemporaneous investigator road map and an ICCRA-linked USGS
  follow-up frame; Mayville and Howell have provisional display geometry tied
  to source coordinates; Jupiter is explicitly a coordinate-anchored scene
  whose orientation remains unresolved. Only images with defensible placement
  evidence receive map footprints. Rights-restricted pixels are requested from
  the source host only after an explicit user action; the repository contains
  and redistributes no source-photo pixels. Local-only registration remains
  available.

## Exact-field resolution status

Exact-field work has begun, but it is not complete. The current ledger contains
408 field candidates/sites; 3,894 other coordinates are explicitly labeled
locality references and 3,443 entities remain unresolved. Twenty field-level
decisions are preserved as reviewed overrides.

The first reviewed case is Whiskey Hill, Oregon. The 1998 Crop Circle Center
row was merged into the ICCRA 1998 entity, and the Crop Circle Center and Paul
Vigay rows for 2000 were merged into the ICCRA 2000 entity. A fourth accepted
alias merge combines the same-date Crop Circle Center and ICCRA Aloha 1994
reports. The erroneous automatic matches to Whiskey Hill, California are no
longer treated as formation locations.

- 1998 is a corroborated field location derived from the user-supplied
  source-photo registration and same-field evidence; the formation itself is
  not directly visible in the referenced 2000 historical frame.
- 1999 is only a candidate field. ICCRA reports that the field hosted a 1999
  formation, but no exact position within the field is established.
- 2000 is directly visible in the supplied historical-imagery view and is
  corroborated by the aerial source photo. Its close-up source photograph now
  has an approximate visual overlay based on the three matching lobes, a
  low-tier row-orientation comparison, and two manually read road controls.
  `data/registered_overlay_observations.json` preserves the image hashes,
  detected controls, affine matrix, pixel-to-WGS84 formulas, and sensitivity
  envelope. Because no independent fourth ground-control point is available,
  the 35 m figure is not a confidence interval and the overlay is excluded from
  formal alignment analysis.
- The 1998 straight component is displayed provisionally on the 110°/290°
  true-north axis with a conservative ±3° uncertainty. It is excluded
  from formal alignment calculations until independent checkpoints reproduce
  the registration; it has no demonstrated predictive validity.

The next reviewed US pass registers the ICCRA-linked Wausau August 13, 1997
USGS follow-up scene against a contemporaneous investigator road map and
persistent road/field landmarks. The formation is not unambiguously visible in
that later frame, so its center remains a candidate field and the placement is
excluded from alignment tests. Wausau August 16, Rockville 1, Rockville 2,
Wavra Farm, and Bedford are also published as bounded candidate fields or
candidate scenes with explicit uncertainty. The current placement wave adds
reproducible, opt-in photo footprints for Wavra Farm and both Rockville cases,
plus Miamisburg, Hopewell/Chillicothe, and Albion/Starr. Bedford and Wausau
August 16 remain point/search evidence only. Fresno, Vacaville, New Park,
Northwood, and Burnsville now have bounded candidate search areas but no
invented image corners where a unique landmark match could not be reproduced.
Wavra now reproduces the user-supplied Google Earth KMZ exactly: its rotated
LatLonBox, source-pixel anchor, 2000-07-23 historical-imagery date, and 50.2%
opacity replace the rejected placement 1,428 metres away. The international
wave also adds nine exact publisher map references as candidate fields and nine
open-license Diessenhofen display overlays: one four-control reference frame
and eight center-constrained same-flight transfers. All remain provisional and
excluded from alignment calculations; image corners were
rejected for the nine rights-restricted cases that lacked sufficient controls.

Rockville 1's earlier two-point similarity display fit has now been rejected and
replaced with a three-control affine road registration. It aligns both approaches
to the Rockville Road/Suisun Valley Road intersection and permits the shear and
unequal scale visible in the oblique aerial photograph, but remains provisional
because no independent checkpoint or same-date orthophoto is available.

The source-image catalog also includes 54 live-checked, link-only photographs
from 23 specifically matched U.S. reports in the Crop Circle Archives 2002â€“2006
North America pages. These additions raise the catalog to 7,945 unique image
links, including 566 associated with U.S. reports. They create source-evidence
PIC records, not image overlays or exact site claims.

The US-first resolution campaign uses official USGS and USDA imagery for
repeatable evidence, with Google Earth as a manual verification surface only.
See `docs/FIELD_RESOLUTION_CAMPAIGN.md` for the acceptance rules, imagery
sources, control-point requirements, and unresolved-state policy.

## Products

- `data/formations.csv`: canonical formation entities.
- `data/location_work_queue.csv`: every catalog entity classified as a field
  candidate/site, locality reference, or unresolved work item.
- `data/site_resolutions.csv`: reviewed field-level overrides with evidence,
  uncertainty, review, and rights fields kept separate.
- `data/source_assertions.csv`: loss-minimizing source statements.
- `data/source_expansion_assertions.csv`: bounded metadata expansion, with
  non-merged overlap status and source geography preserved.
- `data/iccra_index_entries_full.csv`: every ICCRA index occurrence and its
  assertion mapping.
- `data/straight_component_candidates.csv`: automated diagram review queue.
- `data/iccra_image_straight_candidates.csv`: metadata-only, unvalidated ICCRA
  source-image review queue; no source or derived pixels are included.
- `web/data/formation_images.json`: normalized per-report source-image archive,
  with 7,889 unique image links, 1,913 linked reports, 8,042 relationships,
  rights/display policy, and link-verification status.
- `data/orientation_observations.csv`: human-reviewed true-north bearings.
- `data/alignment_hits.csv`: centerline corridor hits with coordinate and
  bearing-uncertainty eligibility fields.
- `web/`: static interactive atlas plus a local-only perspective-correct image
  registration lab.
- `exports/crop_circle_atlas.kml` and `.kmz`: Google Earth points, experimental
  extensions from reviewed local orientations, zero packaged image files, and
  twenty-one disabled provisional GroundOverlay links to source-hosted images,
  including nine CC BY-SA 3.0 international placements. Packaged
  overlays remain rights-cleared only.
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
python scripts/build_global_source_image_links.py --live-details --allow-source-invalid-chain
python scripts/build_commons_crop_circle_images.py
python scripts/detect_straight_components.py --pdf "C:\path\to\COMBINED.pdf"
python scripts/detect_iccra_image_straight_components.py
python scripts/build_dataset.py --pdf "C:\path\to\COMBINED.pdf"
python scripts/build_formation_image_catalog.py
python scripts/build_provisional_image_scene_placements.py
python scripts/build_formation_image_catalog.py
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
`docs/SOURCE_EXPANSION.md`, `docs/IMAGE_GEOREFERENCING.md`, and
`docs/FIELD_RESOLUTION_CAMPAIGN.md` for the evidence, access, resolution, and
qualification rules.

## Scope boundary

This is a strong initial corpus, not yet a literal repository of every crop
formation record on the web. Six archive families currently contribute event
assertions: Crop Circle Center, ICCRA, Crop Circle Connector, DCCA, Paul Vigay's
archive, and the CCCRN mirror. Other high-value holdings remain permission-,
membership-, robots-, DNS-, or interface-limited. The accessible expansion
showed sharply lower yield at Vigay/CCCRN after the Connector and DCCA indexes,
but 449 new normalized keys means global diminishing returns have not been
proved. The source register states each boundary rather than implying complete
coverage of inaccessible holdings.
