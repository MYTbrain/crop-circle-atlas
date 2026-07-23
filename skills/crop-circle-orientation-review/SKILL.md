---
name: crop-circle-orientation-review
description: Measure a straight component from a reviewed crop-circle registration as a true-north bearing with origin and angular uncertainty. Use only after image registration when endpoints can be marked defensibly and the measurement must remain provisional until explicitly promoted.
---

# Crop Circle Orientation Review

## Preconditions

Run only for a reviewed registration in `candidate_field`, `corroborated_field`, `registered_site`, or `publication_eligible`. Do not convert an image-space detector angle or diagram angle directly to a geographic bearing.

## Workflow

1. Load the reviewed registration, candidate tile, homography, coordinate uncertainty, and source provenance.
2. Mark endpoint A and endpoint B on the registered source image. The endpoints must describe the visible straight component, not a guessed continuation.
3. Select directionality explicitly: `forward`, `reverse`, or `bidirectional`. Do not infer which direction a feature points.
4. Call `measure_registered_component`. Transform both endpoints through the reviewed homography into geographic coordinates.
5. Record forward and reverse true-north azimuth, selected azimuth, segment length, midpoint origin, origin uncertainty, and angular uncertainty.
6. Review whether endpoint selection, registration uncertainty, source resolution, and perspective support the reported precision. Increase uncertainty rather than reporting spurious decimals.
7. Persist the measurement with status `provisional_pending_explicit_promotion` and `formal_alignment_eligible=false`.
8. Require a separate explicit review and promotion before adding it to accepted alignment observations.

## Prohibitions

- Never run before registration or from a locality reference.
- Never substitute map north, image-up, crop rows, or a PDF page axis for true north.
- Never erase bidirectionality or uncertainty when extending a line.
- Never include provisional measurements in formal alignment-frequency or prediction analysis.
- Never describe an extended ray as predictive evidence without preregistered methods and independent evaluation.

## Completion report

Return formation/job/registration IDs, both endpoint coordinates, forward and reverse azimuths, selected directionality, angular and origin uncertainty, length, provisional status, evidence hashes, and the explicit reason it remains excluded from formal alignment analysis.
