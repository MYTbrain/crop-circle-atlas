# Field-resolution campaign

Evaluated 2026-07-21. This protocol turns locality-level report references into
reviewable field-location evidence without presenting an automated geocode as
the formation site.

## Current evidence boundary

The catalog contains 8,391 source assertions and 7,745 conservative entities
after four accepted report-alias merges. Every entity has one location role:

| Location role | Count | Meaning |
|---|---:|---|
| Field candidates/sites | 407 | Four corroborated fields, 397 candidate fields, and six registered sites |
| Locality reference | 3,894 | Approximate place centroid retained for finding the report, not the field |
| Unresolved | 3,444 | No coordinate suitable even as a locality reference, or evidence deliberately rejected |
| Total | 7,745 | Complete location-work index |

These counts describe evidence roles, not completion of 7,745 exact
geolocations. A `registered_site` may be based on a source-reported coordinate
that has not yet been independently reproduced. `corroborated_field` means the
field is supported by reviewed evidence; it does not necessarily mean every
feature boundary or formation center is survey-grade. `candidate_field` is a
bounded hypothesis. Unresolved records remain unresolved.

The working queue is `data/location_work_queue.csv`. Nineteen reviewed field-level
decisions are recorded separately in `data/site_resolutions.csv`; 384 more
candidate points come from explicit publisher map targets and remain
non-accepted. Review,
spatial confidence, and image-publication rights cannot be conflated.

## Whiskey Hill correction and demonstration case

The Whiskey Hill, Oregon evidence exposed two different failure modes in the
initial atlas: locality geocoding selected an unrelated Whiskey Hill in
California, and report dates/names prevented obvious aliases from merging.

Three alias reviews are now accepted:

1. Crop Circle Center's 1998-07-21 Whiskey Hill row is an occurrence/date alias
   of ICCRA's 1998-07-23 Whiskey Hill / Hubbard report.
2. Crop Circle Center's 2000-08-05 Whiskey Hill row is the same report as
   ICCRA's Hubbard / Woodburn / Whiskey Hill formation.
3. Paul Vigay's 2000-08-07 listing uses the report-submission date for the same
   formation reported by ICCRA on August 5.

All source assertions remain preserved. The three duplicate Whiskey Hill
entities were merged, reducing the catalog from 7,749 to 7,746 entities. A
fourth review merges the same-date Crop Circle Center and ICCRA Aloha 1994
entries, leaving 7,745 entities. The false
California coordinates are no longer treated as formation locations.

The reviewed spatial evidence is intentionally tiered:

| Report | Status | Reviewed center | Uncertainty | Evidence boundary |
|---|---|---|---:|---|
| 1998 | Corroborated field | 45.1714056, -122.7264972 | 35 m | User-supplied aerial-photo registration and same-field evidence; not directly visible in the referenced 2000 frame |
| 1999 | Candidate field | 45.1713, -122.7263 | 200 m | ICCRA says the field subsequently hosted a 1999 formation, but gives no exact position in the field |
| 2000 | Corroborated field | 45.1711639, -122.7260611 | 25 m | Formation directly visible in the supplied historical-imagery view and matched to the source aerial photograph |

The 2000 center is approximately 43.5 m southeast of the registered 1998
center, agreeing with the preserved report's same-field description. The
historical frame is labeled 2000-07-28 while the formation was reported on
August 5. The frame date is retained exactly as displayed and is not silently
substituted for the event date; Google notes that aerial mosaics and historical
imagery dates can require provider-level interpretation.

The straight component marked in the user-supplied north-up 1998 registration
defines a provisional 110°/290° true-north axis with a conservative ±3°
uncertainty. It remains
`provisional_pending_independent_checkpoints`, is excluded from formal
alignment calculations, and has no demonstrated predictive validity. The
registration's automated inlier features are useful reconstruction evidence,
but they are not a substitute for independently selected ground checkpoints.

## Additional reviewed US candidates

The first campaign pass added six evidence-reviewed US cases. A second bounded
image-placement wave promoted Wavra Farm and both Rockville cases to explicit,
reproducible provisional scene overlays while retaining their formal-analysis
exclusions.

| Report | Published result | Uncertainty | Evidence boundary |
|---|---|---:|---|
| Wausau, Wisconsin, 1997-08-13 | Candidate field plus provisional follow-up-scene placement | 100 m | A contemporaneous investigator map is fitted to named road controls and checked against persistent roads, a farmstead, drainage, and field boundaries in the ICCRA-linked 1998 USGS frame; the formation is not clearly visible in that later frame |
| Wausau, Wisconsin, 1997-08-16 | Candidate field | 100 m | The second symbol on the same investigator map constrains the field west of North 41st Street; no independent projective image fit is accepted |
| Rockville 1, California, 2003-06-28 | Candidate field plus provisional source-photo placement | 60 m | Named intersection plus road, field, parking, roof, and tree controls support a two-control similarity display fit; no independent checkpoint |
| Rockville 2, California, 2003-06-28 | Candidate field plus provisional source-photo placement | 60 m | Solano Community College tennis courts, campus buildings, parking, arterial road, and field corner constrain the oblique scene; no independent checkpoint |
| Wavra Farm / Salem–Silver Creek Falls, Oregon, 1997-06-28 | Corroborated field plus user-supplied Google Earth KMZ registration | 20 m | The exact rotated KML LatLonBox, source-pixel anchor, 2000-07-23 historical frame, highway, curved drives, tree rows, buildings, and field edges replace the rejected placement 1,428 metres away |
| Bedford, Indiana, 2008-09-13 | Candidate field/search scene | 1,200 m | The source's approximate location-map pin is fitted to named-community controls and checked against the Sandpit/Mitchell road clue; ground photographs do not support corners or orientation |

These classifications are search improvements, not survey-grade formation
coordinates. Their uncertainty values, evidence methods, and exclusions remain
visible in the site ledger.

The second wave also adds photo footprints for Miamisburg 2004,
Hopewell/Chillicothe 2012, and Albion/Starr 2002. It narrows Fresno, Vacaville,
New Park, Northwood, and Burnsville to candidate search areas while deliberately
leaving their source photographs at PIC-only status because the visible
landmarks did not select a unique field and transform.

The first worldwide placement wave adds nine exact publisher map references as
candidate fields and a distinct Diessenhofen, Switzerland event dated
2008-07-15. Nine open-license Commons aerials document that event; one frame has
a four-control landmark display registration. The remaining international
images keep null corners where historical imagery and visible controls did not
support a reproducible projective transform.

## US-first source hierarchy

The first campaign pass prioritizes United States reports because several
official programs provide dated, reproducible aerial imagery. Use source
metadata and collection identifiers rather than screenshots whenever an
official product covers the required place and time.

1. [USGS EarthExplorer](https://earthexplorer.usgs.gov/) is the primary search
   surface for the USGS EROS collections.
2. [Digital Orthophoto Quadrangles (DOQ)](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-digital-orthophoto-quadrangle-doqs)
   provide orthorectified coverage principally from 1987-2006, useful for many
   1990s and early-2000s reports.
3. [High Resolution Orthoimagery (HRO)](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-high-resolution-orthoimagery-hro)
   provides orthorectified imagery of 1 m or finer from 2000-2016 where
   available.
4. [Aerial Photo Single Frames](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-aerial-photo-single-frames)
   reach back to 1937. These frames may be unreferenced, rotated, tilted, or
   distorted and therefore require explicit registration and checkpoints.
5. [USGS-distributed NAIP](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-agriculture-imagery-program-naip)
   supplies growing-season orthophotography from 2003 onward. Consult USDA's
   [NAIP program guidance](https://www.fpacbc.usda.gov/geospatial-services/geospatial-technology-coordination-and-project-execution/program-management),
   [historical-film holdings](https://www.fpacbc.usda.gov/geospatial-services/data-inspection-enhancement-and-delivery/production-services),
   and guide to
   [ordering geospatial data and historical aerial imagery](https://www.fsa.usda.gov/sites/default/files/documents/howtoorderaerialimagery-rev2021_02_.pdf)
   when holdings are not downloadable through EarthExplorer.
6. Google Earth historical imagery is a manual verification surface only. Use
   Google's instructions to [view a map over time](https://support.google.com/earth/answer/15468379?hl=en)
   and its explanation of [how imagery and dates are collected](https://support.google.com/earth/answer/6327779?hl=en).
   Do not scrape Google Earth, treat its display as a bulk dataset, or copy its
   pixels into this repository.

## Semi-automated workflow

### 1. Normalize and rank the queue

- Preserve every source assertion and reconcile obvious place/date/report
  aliases before spatial work.
- Prioritize US records with day-level dates, aerial photographs, dimensions,
  road/farm/airport names, power lines, watercourses, field boundaries, or a
  source map.
- Penalize ambiguous place names and reject automatic admin-area mismatches.
- Search a date window wide enough to distinguish formation imagery from
  harvest marks, later field work, and unrelated circular features.

Automation may prepare bounding boxes, date windows, official collection
queries, candidate-frame lists, image hashes, and clue summaries. It may not
promote a candidate to an accepted field without review.

### 2. Acquire reproducible imagery metadata

For every candidate frame, record the collection, entity/frame identifier,
provider, acquisition date or date range, coordinate reference system, pixel
size or source scale, access URL, retrieval date, file hash when downloaded,
and item-specific rights statement. Prefer an orthorectified product near the
report date. Retain older and newer frames when they help verify roads,
structures, field boundaries, and seasonal change.

Single frames and oblique source photographs are not maps. Their approximate
catalog coordinates only identify likely coverage and must not be copied into
the formation coordinate fields.

### 3. Select controls and held-out checkpoints

- Use 8–12 well-distributed controls for the production registration even
  though four points are the mathematical minimum for a projective transform.
- Cover the full image footprint and its corners. Avoid collinear controls or
  controls clustered on one side of the formation.
- Prefer persistent, sharply identifiable features: road intersections,
  building corners known to survive the date interval, bridge or canal
  crossings, utility-line intersections, and distinctive fixed boundaries.
- Do not use the crop formation, vehicle positions, shadows, temporary tracks,
  crop rows, or the same feature twice.
- Reserve at least three additional landmarks as independent checkpoints.
  Checkpoints are never used to solve or tune the transform.

Every control and checkpoint records both image pixels and map coordinates,
feature description, reference imagery/product, estimated landmark
uncertainty, and reviewer.

### 4. Solve, test, and quantify uncertainty

Solve the projective transform with the control set, then measure ground error
at the held-out checkpoints. Record control residuals and checkpoint residuals
separately. A low fit residual is not an accuracy test when no independent
checkpoints exist.

The reported coordinate uncertainty must be conservative and include at least
the held-out checkpoint error, landmark-selection error, reference-product
accuracy, source-image resolution, and formation-center interpretation. Reject
or downgrade registrations with poor spatial distribution, unstable features,
unexplained residual structure, incompatible acquisition dates, or a result
that cannot be reproduced by another reviewer.

### 5. Adjudicate without forced completion

- `registered_site`: a source reports coordinates with method and uncertainty;
  independent imagery verification may still be pending.
- `corroborated_field`: reviewed evidence establishes the field or bounded
  site, with uncertainty and at least two compatible evidence types.
- `candidate_field`: evidence narrows the report to a plausible field but does
  not establish the exact formation position.
- `locality_reference`: a place centroid retained only for discovery/search.
- `unresolved`: evidence is absent, contradictory, inaccessible, or too weak.

No-record and unresolved outcomes are valid results. A report does not receive
an exact coordinate merely because an automated lookup or a visually similar
field is available.

### 6. Orient straight components only after registration

Image-space detector angles are review priorities, not compass bearings. A
true-north axis requires an accepted or explicitly provisional registration,
two documented component endpoints, transform-derived azimuth, coordinate and
angular uncertainty, evidence hashes, and human review. Provisional axes remain
visually distinct and excluded from formal alignment statistics.

## Source-photo display and publication rights

The per-report archive exposes 480 unique ICCRA-linked source images across 266
formations through 517 formation-image links. A source link is not a
georegistration. The public site contains no packaged ICCRA photographs, and
only defensibly registered images receive map footprints. Each source-photo
overlay is disabled until a user explicitly chooses to show it; the browser
then requests the rights-restricted image directly from the source host and
applies the atlas's corner metadata locally. The footprints follow the active
search, year, and country filters. Twelve reviewed placements are currently
available: Whiskey Hill/Hubbard 1998 and 2000, Wausau 1997,
Mayville/Kekoskee 2003, Howell Township 2003, Jupiter 2005, Wavra Farm 1997,
both Rockville 2003 reports, Miamisburg 2004, Hopewell/Chillicothe 2012, and
Albion/Starr 2002. For Hubbard
2000, `data/registered_overlay_observations.json` makes the approximate display
geometry reproducible while recording that its 35 m detector-sensitivity
envelope is not a confidence interval and that it lacks an independent ground
checkpoint. Mayville and Howell retain provisional source-coordinate display
geometry; Jupiter retains a coordinate anchor while explicitly leaving image
orientation unresolved. Wausau registers an ICCRA-linked USGS follow-up frame
from the contemporaneous road map and persistent scene controls, but remains
provisional because the formation is not clearly visible and no independent
checkpoint set has reproduced the transform. The repository does not proxy,
cache for publication, bundle, or redistribute those pixels. Cross-origin or
source-host failure remains a visible failure; it is not bypassed.

An opt-in browser display is not permission to republish. The current KML/KMZ
packages zero source-photo files and carries thirteen disabled provisional
GroundOverlay URLs to the source host. A packaged GroundOverlay remains excluded
until the specific asset has a verified license or written permission,
rights-holder attribution, proof reference, permitted use, source URL, hash,
reviewer, and review date. Official USGS/USDA products also retain item-level
source and rights metadata rather than relying on a blanket assumption.

## Completion rule

This campaign is iterative and US-first, not a declaration that all remaining
formations have been exactly located. Publish progress by status and evidence
tier. The unresolved count should fall only when reproducible evidence supports
a better classification; it must never be reduced by relabeling locality
centroids as fields.
