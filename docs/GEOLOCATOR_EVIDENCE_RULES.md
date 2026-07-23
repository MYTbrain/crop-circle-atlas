# Geolocator evidence rules

## Spatial roles are not interchangeable

- `locality_reference` is a town, label, or other search anchor. It is not a field.
- `locality_search_area` is a bounded polygon used to find imagery. It is not a field.
- `candidate_field` is a human-reviewed plausible field with explicit uncertainty and limitations.
- `corroborated_field` requires two compatible evidence types and passing independent validation.
- `registered_site` is a source-reported coordinate with its method and uncertainty; it is not automatically independently corroborated.

Never promote a town centroid, map label, postcode, county center, or automated geocoder result to a formation site.

## Alias reconciliation comes first

Resolve duplicate reports, date aliases, spelling variants, and same-field/different-year relationships before spatial work. Keep ambiguous entities separate. A spatially convincing candidate does not prove two reports are aliases.

## Machine evidence

Retrieval similarity reduces a bounded search set. It is not location evidence. SIFT/RANSAC yields a `review_required` proposal at best. Reject matches with insufficient inliers, poor spatial distribution, repeated agricultural texture, unstable homography, folded footprint, excessive residual, or incompatible scene geometry.

## Controls and checkpoints

Controls estimate the transform. Checkpoints independently test it and cannot be reused controls. Use stable ground objects distributed around the scene. Do not use the crop formation, vehicles, shadows, temporary tracks, or crop-row texture. At least four controls and three held-out checkpoints are required for independent validation.

Control reprojection residual is reported in pixels and must never be called accuracy. Checkpoint errors are measured on the ground in metres and reported as median, RMSE, maximum, and p95.

## Uncertainty

Use a conservative bound composed of checkpoint floor, reference-image accuracy, landmark selection, source resolution, source distortion, formation-center interpretation, and control-selection instability. The result is not a probabilistic confidence interval. Do not report precision unsupported by the source image or controls.

## Human classification gate

A reviewer must identify themselves, choose accept/downgrade/reject/defer/unresolved, select the candidate, preserve edited controls and checkpoints, set the spatial class and uncertainty, record compatible evidence and contradictions, decide rights, and cite evidence hashes. The state machine rejects invalid transitions. Unresolved and deferred are valid outcomes.

## Rights are separate from spatial confidence

Rights status never increases location confidence, and spatial confidence never grants publication rights. Local-analysis artifacts may be generated after an accepted or downgraded review. Public export additionally requires an authorized status, explicit derivative permission, proof, license identifier where applicable, and rights holder where applicable. Otherwise it fails closed.

The repository must not contain provider rasters, historical screenshots, rights-restricted source photographs, credentials, model weights, or caches.

## Promotion and orientation

Machine processing never edits canonical coordinates. A separately confirmed `promote_reviewed_resolution` operation writes a reviewable patch proposal with `canonical_catalog_mutated=false`.

Straight-component measurement runs only after review. It transforms two explicit endpoints through the registration, reports forward/reverse true-north bearings plus angular/origin uncertainty, preserves directionality, and stays `formal_alignment_eligible=false` until separately promoted. Provisional rays must not be used to claim prediction or alignment prevalence.

## Negative evidence

Persist fields searched, imagery vintages absent or incompatible, rejected matches, checkpoint failures, rights failures, algorithm versions, and stop reasons. Do not repeat an identical negative search unless the report evidence, imagery coverage/vintage, or algorithm changes materially.
