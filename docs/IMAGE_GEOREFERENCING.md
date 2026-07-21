# Projective image georeferencing

`web/georef.html` is a standalone, local-only registration lab for aerial crop-
formation images. It corrects rotation, scale, skew, and perspective with a
projective homography from four or more control points. It does not upload the
selected image.

## Reviewer workflow

1. Serve `web/` over local HTTP and open `georef.html`. Do not open it with a
   `file://` URL because browser security rules block module and dataset loads.
2. Select the original local image and record its formation, source URL, rights
   holder, license or permission, and reviewer.
3. For each of at least four landmarks, click the landmark in the image and then its
   exact counterpart on the map. Use fixed features spread around the image,
   such as road intersections or building corners. A catalog locality centroid
   is not a ground-control point.
4. Solve the registration and generate the north-up overlay. Switch to satellite
   imagery, adjust opacity, and visually inspect all four landmarks plus at least
   one independent feature that was not used as a control point.
5. If the formation contains a straight component, choose **Mark endpoints**,
   click endpoint A and endpoint B in the original image, enter realistic ground-
   control and click uncertainty, and explicitly choose A-to-B, B-to-A, or both
   directions. The lab transforms both pixels to geographic coordinates and
   computes true-north azimuth.
6. Export the registration JSON, north-up PNG, KML sidecar, orientation CSV, and
   ray KML. The standalone ray is labeled an unreviewed experimental projection
   until it passes the atlas evidence gate. Keep local-analysis artifacts
   private unless the recorded image rights authorize publication.

Four control points exactly determine a homography, so a near-zero residual is
expected. Additional pairs are fit by least squares and expose internal mismatch,
but even that residual is **not** an independent accuracy measurement. The uncertainty
shown for a straight component propagates the transform residual, the reviewer-
entered ground-control uncertainty, and image endpoint click uncertainty. It
does not account for undocumented camera distortion, terrain relief, or an
incorrect landmark match.

The homography and north-up raster remain in EPSG:3857. Raster bounds and pixel
size therefore use **projected EPSG:3857 metres**, which are deliberately labeled
as projected units. Control-point residuals, measured component length, click-
scale propagation, and ray-origin uncertainty use spherical geodesic distance
and are reported in **physical ground metres**. This distinction is material at
high latitude, where 1,000 projected metres spans far less than 1,000 ground
metres.

## Deterministic PNG, world file, KML, and KMZ export

The browser exports a north-up PNG and a KML sidecar as separate downloads.
The companion local command verifies the image hash, recomputes the transform,
and packages a deterministic, self-contained KMZ:

```powershell
python scripts/georeference_image.py `
  --registration "C:\path\formation.registration.json" `
  --image "C:\path\original-aerial.jpg" `
  --output-dir "C:\path\georef-output"
```

The output directory contains:

- a transparent north-up PNG in EPSG:3857;
- `.pgw` and `.prj` files for GIS software;
- standalone KML referencing the sibling PNG;
- self-contained KMZ with `doc.kml`, the image, and resolved metadata;
- recomputed registration metadata; and
- a SHA-256 export manifest.

Every standalone overlay KML embeds the recorded rights status, rights holder,
license, proof reference, and source URL. This metadata does not itself grant
publication permission; local-analysis exports say so explicitly.

Add `--public-export` only for a publication package. That option fails closed
unless rights status is one of `public_domain`, `cc0`, `cc_by`, `cc_by_sa`,
`licensed`, `permission_granted`, or
`owner_supplied_publication_authorized`. Every publication status requires an
explicit license or permission proof reference; license-based statuses require
a license identifier, and attribution/permission statuses require a rights
holder. The ambiguous legacy value `open_license` is not publication-authorized.
Without `--public-export`, the generated image/KMZ remains a local-analysis
artifact even when the metadata contains a publication-compatible rights record.

## Ingest into the combined atlas KMZ

After inspecting the resolved registration and warped PNG, ingest them into the
atlas image-assets registry:

```powershell
python scripts/ingest_georeference.py `
  --registration "C:\path\georef-output\formation.registration.json" `
  --warped-png "C:\path\georef-output\formation_north_up.png" `
  --repo-root "."
python scripts/generate_kml.py
```

The ingest command verifies schema, PNG content and dimensions, north-up
EPSG:3857 metadata, reviewer/date, rights proof, and hashes. For an authorized
derivative it copies the exact PNG bytes to `assets/registered-overlays/` and
adds deterministic bounds metadata to `data/image_assets.csv`. The combined KMZ
then contains a `GroundOverlay` plus the image itself. For
`local_analysis_only` or `permission_pending`, ingest records the derivative
hash but leaves `local_path` empty and does not copy private pixels into the
repository; the combined-KMZ generator excludes it.

The publication packager independently repeats the path, formation, rights,
hash, review, bounds, physical-unit, and transform checks. Its current public
quality gate rejects control-point RMSE above 25 physical ground metres; use a
tighter project-specific threshold when the intended analysis requires it.
There are currently zero packaged ICCRA image files because no source-image
publication rights have been cleared. The combined KML/KMZ contains two
off-by-default provisional GroundOverlays for Whiskey Hill/Hubbard 1998 and
2000. They link to the source host and package no source pixels. The 2000
close-up is an approximate visual three-lobe match.
`data/registered_overlay_observations.json` preserves its image hashes,
detector settings, lobe controls, affine matrix, manually read road controls,
pixel-to-WGS84 formulas, orientation-permutation check, and sensitivity study.
The stated 35 m is a conditional detector-sensitivity envelope, not a
confidence interval; without an independent fourth ground-control point the
overlay remains excluded from formal alignment analysis.

## Atlas integration hooks

The lab accepts a formation deep link:

```text
georef.html?formation_id=<formation_id>
```

When a straight component is complete, the lab exposes the current results as:

```javascript
window.CropCircleGeoref.getRegistrationMetadata()
window.CropCircleGeoref.getOrientationObservation()
```

It also dispatches `crop-circle-atlas:orientation-ready` in the lab window and,
when opened by the atlas, sends a same-origin `postMessage` with this shape:

```javascript
{
  type: "crop-circle-atlas:orientation-ready",
  orientation: {
    observation_id,
    formation_id,
    origin_latitude,
    origin_longitude,
    origin_uncertainty_m,
    origin_coordinate_method: "registered_component_midpoint",
    evidence_sha256,
    azimuth_true_deg,
    azimuth_uncertainty_deg,
    directionality, // "forward" or "bidirectional"
    max_range_km,
    corridor_km,
    orientation_method: "landmark_registration"
  },
  registration
}
```

The qualified ray origin is the registered midpoint of the two measured
straight-component endpoints. `origin_uncertainty_m` conservatively uses the
larger propagated endpoint position uncertainty. If the reviewer selects B-to-A
in the lab, the exported azimuth is the B-to-A bearing and export directionality
is normalized to `forward`; `selected_direction=reverse` remains in `notes` and
the registration metadata retains the explicit `reverse` selection. This keeps
the qualified-ray generator's directionality contract unambiguous.

`web/georef-atlas-adapter.mjs` provides a ready-made bridge. The parent page can
install it once and open the lab from a selected formation:

```javascript
import {
  installOrientationBridge,
  openRegistrationLab,
} from "./georef-atlas-adapter.mjs";

installOrientationBridge({
  onOrientation(observation, registration) {
    // Persist only after the project's human-review and rights checks.
    console.log(observation, registration.registration_id);
  },
});

openRegistrationLab(selected.properties.formation_id);
```

The bridge copies the reviewed true bearing, normalized directionality, range, and corridor
into the existing alignment-lab inputs. It does not automatically click **Draw
and test ray**, because the user must inspect the imported bearing and select the
correct formation origin first.

The registration JSON contract is defined by
`schemas/georeference-registration-v1.schema.json`. An orientation CSV row uses
the exact column order in `data/orientation_observations.csv`.

## Image rights

The software license does not relicense source photographs. Keep the original
image on the reviewer's device, preserve the source URL and SHA-256 digest, and
do not commit or publish image pixels or derivative overlays until permission
or an applicable license and its proof are documented in
`data/image_assets.csv`. The registration metadata contains no image pixels or
local source path.
