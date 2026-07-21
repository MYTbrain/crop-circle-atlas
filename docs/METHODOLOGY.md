# Methodology

## Entity model

`source_assertions.csv` retains what each source says. `formations.csv` is a
derived entity table. Records merge only when date, normalized locality,
country, and (when available) region agree. Ambiguous near-matches remain
separate for later review.

Dates carry an explicit precision (`day`, `month`, `year`, or `qualified`).
Coordinates carry a method and uncertainty class. Current automated coordinates
are locality centroids from GeoNames, not field locations.

## Direction and orientation

The following concepts must not be collapsed:

1. `has_straight_component`: a visible straight segment exists.
2. `diagram_angle_deg`: angle in an unreferenced drawing or photograph.
3. `azimuth_true_deg`: geographic bearing clockwise from true north.
4. `azimuth_uncertainty_deg`: reviewer's uncertainty.

Only item 3 can generate a geographic ray. Orientation methods should be one of
`survey`, `north_arrow`, `georeferenced_photo`, `landmark_registration`, or
`other_documented`.

## Alignment testing

Exploratory hits use great-circle cross-track distance and along-track range.
The production study should preregister:

- maximum range and corridor width;
- whether rays are one-way or bidirectional;
- date ordering (earlier source to later target, later to earlier, or both);
- treatment of multiple rays per formation;
- minimum coordinate and orientation quality;
- a null model preserving spatial density, year, country, and source coverage;
- false-discovery correction across all tested rays.

Useful nulls include bearing rotation within each source formation, permutation
within spatial/temporal strata, and matched random points drawn from arable-land
masks. Report effect sizes and uncertainty, not just hit counts.

## Image overlays

Public overlays require a rights record in `data/image_assets.csv`. Four or more
ground control points should be used for skewed aerial photographs. Store the
original image hash, control points, coordinate reference system, transform
residuals, reviewer, and license. The initial browser tool supports local,
session-only placement so copyrighted images do not leave the user's machine.

