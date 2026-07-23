# Crop Circle Geolocator architecture

## Scope and claim boundary

The geolocator is a local, deterministic research worker for turning one report's bounded locality evidence into reviewable exact-field candidates. It does not claim to resolve every crop circle, does not make a language model inspect thousands of fields, and cannot promote a machine match into the canonical atlas.

The static GitHub Pages atlas remains independent. `web/geolocation-review.html` is a control/review surface that can connect to a localhost API, while all credentials, raster reads, feature extraction, matching, and persistence remain in Python.

```text
Atlas report and assertions
        |
        v
versioned job -> bounded search polygon -> normalized imagery items
        |                                    |
        |                                    v
        |                            reusable physical tiles
        |                                    |
        v                                    v
structured clues -> CPU retrieval -> SIFT/RANSAC candidates
                                      |
                                      v
                         controls != held-out checkpoints
                                      |
                                      v
                         explicit human review and rights gate
                                      |
                         +------------+-------------+
                         |                          |
                 local KML/KMZ            separate promotion proposal
```

## Components

- `models.py`, `workflow.py`, and six JSON Schemas define typed, append-only state and artifact contracts.
- `service.py` contains the ordinary orchestration logic. The CLI, MCP server, and FastAPI module are adapters around it.
- `imagery/` implements local GeoTIFF/COG discovery and cutouts, generic STAC normalization, Planetary Computer signing, and USGS M2M search/download-option boundaries.
- `tiles.py` produces metre-based, overlapping, scale/rotation/representation variants with physical footprints and content-addressed cache keys.
- `retrieval/cpu_baseline.py` ranks scene structure with a deterministic edge/gradient descriptor. AnyLoc and MegaLoc are disabled adapter boundaries only.
- `matching/opencv_sift.py` supplies the required CPU baseline: SIFT, ratio filtering, RANSAC, homography diagnostics, spatial-distribution scoring, fold-over rejection, and normalized candidate records. LightGlue and VisMatch are disabled until code and weight terms are selected explicitly.
- `validation/` keeps controls separate from checkpoints, reports ground error in metres, rejects unstable geometry, propagates conservative uncertainty, and enforces human/publication gates.
- `overlay.py` creates deterministic PNG/KML/KMZ local artifacts. Public derivatives fail closed on rights.
- `orientation/` transforms reviewed endpoints to true-north azimuth and keeps the observation provisional.
- `benchmark/` isolates input manifests from evaluator coordinates and provides a deterministic synthetic mathematical test.

## State machine

The states are `queued`, `clues_extracted`, `search_area_ready`, `imagery_cataloged`, `tiles_generated`, `candidates_ranked`, `registrations_proposed`, `review_required`, `rejected`, `deferred`, `unresolved`, `candidate_field`, `corroborated_field`, `registered_site`, and `publication_eligible`.

Only validated edges in `workflow.TRANSITIONS` are allowed. A machine cannot enter `corroborated_field`, `registered_site`, or `publication_eligible`. `corroborated_field` requires an accepted review, two compatible evidence types, passing independent checkpoints, no unresolved contradiction, and conservative uncertainty. Publication is a second gate based on recorded rights, not spatial confidence.

## Persistence and provenance

The default cache is outside the repository at `%LOCALAPPDATA%/crop-circle-atlas/geolocator`. Each job version is immutable and each event is appended to `events.jsonl`. Content-addressed artifacts live below `artifacts/`; repeated identical work reuses safe outputs. Job records include software/Python/platform fingerprints. Run manifests record stages, timestamps, duration, counts, bytes, cache activity, device, model versions, errors, retries, limits, and final status.

Negative outcomes are persisted as artifacts and events. A rejected field should be retried only if report evidence, imagery vintage/coverage, or algorithm version changes.

## Security and scale boundaries

- The API binds to loopback by default and allows only specific localhost CORS origins. Container-wide binding requires the explicit `CROP_CIRCLE_GEO_ALLOW_CONTAINER_BIND=true` flag and the supplied Compose file publishes it only on host loopback.
- Browser code contains no provider credentials. MCP returns compact JSON and artifact paths, not rasters.
- The API file endpoint serves only allow-listed files under the geolocator cache and enforces the configured size ceiling.
- Search area, imagery count, tile count, top-K, bytes, runtime, and workers are bounded by configuration.
- Model caches, credentials, imagery, generated rasters, and weights are ignored and checked in CI.

## Extension boundary

A future remote control plane may call the local API/MCP worker, but heavy vision should remain on a local or containerized compute worker. The next technical phase is a rights-cleared real-world benchmark with preregistered negatives, followed by optional learned retrieval/matching adapters only after their exact code and weight licenses are locked.
