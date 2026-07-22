---
name: crop-circle-image-registration
description: Register one specific crop-circle source image to one selected candidate tile, inspect correspondences, correct controls, validate with independent checkpoints, and create rights-gated local overlays. Use after bounded candidate retrieval when a reviewer needs a defensible projective registration rather than a visual guess.
---

# Crop Circle Image Registration

## Preconditions

Require a persisted field-resolution job, one source image, one selected candidate tile, source provenance, imagery provider/date metadata, and a rights record. Do not begin from a town centroid or an unbounded map view.

## Workflow

1. Load the source image and candidate metadata. Verify hashes, CRS, physical footprint, dimensions, acquisition date, orthorectification status, and rights.
2. Run `match_candidate`. Inspect ratio-filtered matches, RANSAC inliers, rejected matches, reprojection residual, homography conditioning, fold-over, and spatial distribution.
3. Reject degenerate, clustered, repetitive-row, shadow-only, or transient-feature matches. The crop design itself is not a stable ground-control landmark.
4. Correct image corners or controls in the reviewer. Use at least four spatially distributed stable controls; use more when available.
5. Reserve at least three additional stable landmarks as held-out checkpoints. A landmark must never be both a control and a checkpoint.
6. Call `validate_registration`. Report control fit in pixels separately from checkpoint median, RMSE, maximum, and p95 errors in physical ground metres.
7. Record conservative uncertainty from checkpoint error, reference accuracy, landmark selection, source resolution/distortion, center interpretation, and control-selection instability.
8. Save an explicit human decision. Accept, downgrade, reject, defer, or preserve unresolved; never silently promote the machine result.
9. Use `generate_local_overlay` for local-analysis KML/KMZ. Public export must fail closed unless the rights record proves derivative permission, license, holder where required, and explicit authorization.

## Evidence rules

- Control residual measures transform fit; it is not independent accuracy.
- Historical imagery and source-photo geometry can disagree because of landscape change, orthorectification, lens distortion, and oblique perspective.
- Prefer stable road intersections, field boundaries, buildings, bridges, mature tree-line corners, drainage features, and utility corridors.
- Preserve the original candidate, edited registration, checkpoints, reviewer, timestamps, software versions, hashes, and limitations as separate append-only evidence.
- Never publish or commit source pixels whose rights permit only local analysis.

## Completion report

Return registration candidate ID, review ID, transform type, inlier metrics, control and checkpoint counts, checkpoint errors, uncertainty, spatial classification, rights decision, overlay paths/hashes, and unresolved limitations.
