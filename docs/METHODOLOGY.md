# Methodology

## Provenance and entity resolution

`source_assertions.csv` retains what each source says. `formations.csv` is a
derived table. Records merge only when date, normalized locality, country, and,
when available, region agree. Ambiguous near-matches remain separate. Assertion
and formation identifiers are unique and all relationships are verified as
foreign keys.

The bounded expansion preserves each source's place, region, country, and event
designator. Only 190 exact normalized keys merge automatically. The 167 alias
and 83 probable-overlap candidates remain separate, and the 449 new normalized
source keys are not promoted to a claim of 449 proven-new physical formations.

The ICCRA inventory reconciles its by-year and by-state indexes at occurrence
level. “Index inventory complete” does not imply that every old page still
exists: one Mount Airy 1965 entity has a dead detail URL. The public
reconciliation preserves site count mismatches, unlinked list entries, failed
URL variants, and count-only placeholders instead of silently inventing detail.

## Coordinates

Dates retain `day`, `month`, `year`, or `qualified` precision. Coordinates
retain method, confidence, and uncertainty. US locality geocoding fails closed
when GeoNames’ state conflicts with the source state. Most points remain
locality centroids. Four ICCRA coordinate pairs were parsed automatically; a
fifth, Aloha, was recovered by evidence review and retained with 1.5 km
uncertainty. All carry their source method and uncertainty separately.

Locality centroids are appropriate for browsing and candidate retrieval, not a
narrow-corridor spatial test. An evidence-qualified local orientation requires
an exact or registered origin rather than borrowing a locality centroid.

## Straight components and true orientation

These concepts are deliberately separate:

1. `has_straight_component`: automated candidate or reviewed line/axis evidence.
2. `diagram_angle_deg`: an axis in an image with no assumed north reference.
3. `source_image_straight_tier`: an unvalidated automated review priority from
   an ICCRA source photograph, map, aerial, or diagram. It is stored separately
   and never changes `has_straight_component` or ray qualification.
4. `azimuth_true_deg`: a geographic bearing clockwise from true north.
5. `azimuth_uncertainty_deg`: documented angular uncertainty.

The OpenCV detector processed all 5,978 PDF assertions. Its high-or-medium tier
has measured precision 0.8889, recall 0.6486, and F1 0.75 on 104 manually
classified items drawn as an internal convenience sample from six selected
pages. These figures are pipeline QA, not random out-of-sample validation. The
low tier is retained to increase review recall, not as a claim that every item
contains a line. Diagram angles use the image x-axis and have no geographic
interpretation.

The ICCRA source-image pass is a distinct, unvalidated detector. It accounted
for all 681 inventory rows: 669 successfully cached hosted images were analyzed
from a private cache (526 unique byte hashes), six external references were not
fetched, and six hosted references returned HTTP 404. Row-level results were
157 high, 85 medium, 86 low, and 341 none; duplicate page references deliberately
remain visible in those row counts. The detector uses stricter coherence gates
for photographs, maps, and aerials than for diagrams, rejects likely image-frame
edges, and caps processing resolution deterministically. These thresholds have
not been validated against a human-labeled ICCRA-image sample, so every tier is
only a review queue. The public CSV contains URLs, SHA-256 hashes, image-space
axes, diagnostics, and exclusion statuses; it contains no source or derived
pixels and creates no true-north bearing.

A geographic projection is exported only when the observation has a supported method,
true azimuth, uncertainty, reviewed evidence, date/reviewer, exact or registered
origin, valid range/corridor, and an assertion attached to the same formation.
Current methods are `survey`, `north_arrow`, `georeferenced_photo`,
`landmark_registration`, and `other_documented`.

Qualification applies to the local orientation evidence, not to the claim that
the feature physically "points" hundreds of kilometres. Every long-distance
extension is labeled experimental and has no demonstrated predictive validity.

## Alignment calculations

Rays and hits use great-circle destinations plus spherical cross-track and
along-track distances, including antimeridian-safe bearing normalization.
Current hit rows are centerline-corridor candidates. Statistical eligibility
also requires the sum of source-origin uncertainty, target-coordinate
uncertainty, and distance-dependent lateral bearing uncertainty to fit inside
the declared corridor. Rows that fail remain explicit exploratory results.
The earlier mixed-coordinate build produced 16 corridor matches against rough
locality centroids. Those points are not formation sites and are now excluded.
The evidence-separated rebuild tests accepted rays only against the two
currently alignment-eligible sites and produces zero corridor matches. The
other 417 site/candidate records, unresolved reports, and locality references
are excluded by the current quality gate.

Before any prediction study, preregister range, corridor, directionality, date
ordering, coordinate/orientation thresholds, duplicate-event handling, and the
number of tested rays. Use null models that preserve spatial density, year,
country, arable-land availability, and source coverage; then correct for
multiple testing and report effect sizes with uncertainty.

## Image registration and overlays

The local lab uses four to twelve paired image/map control points and a
projective homography to correct rotation, scale, skew, and perspective. Pixels
stay in the browser. Exports retain the original SHA-256, control points,
transform residuals, rights evidence, reviewer, and registration metadata.
Homography/raster coordinates and pixel size remain EPSG:3857 projected units;
reported residuals, component lengths, and propagated positional uncertainty are
spherical geodesic physical ground metres rather than raw Web Mercator deltas.

A public combined KMZ must fail closed unless the registered image has an
in-repository path, matching hash, valid formation, reviewed transform, and
explicit publication authorization with license or permission evidence. ICCRA
source images are link-only/private-cache research inputs until rights holders
authorize redistribution.
The current combined KML/KMZ packages zero image files. It contains 25
rights-compatible remote-linked GroundOverlays whose URLs point to source
hosts; those linked displays are not publication authorization and may be
blocked by the host. When an authorized packaged overlay is added, the combined KML embeds its
rights holder, license, proof reference, and source URL in both the description
and ExtendedData.
