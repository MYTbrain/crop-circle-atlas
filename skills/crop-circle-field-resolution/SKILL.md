---
name: crop-circle-field-resolution
description: Resolve one crop-formation report, or a small explicitly bounded batch, from locality clues to reviewable exact-field candidates using the Crop Circle Atlas geolocator MCP tools. Use for bounded imagery discovery, candidate ranking, registration triage, and preserving unresolved outcomes; do not use for bulk centroid promotion or open-ended visual browsing.
---

# Crop Circle Field Resolution

## Operating contract

Treat report locality coordinates as search anchors, never formation sites. Keep machine results at `review_required` or lower. Only a separate human review may classify a field, and only `promote_reviewed_resolution` with explicit confirmation may create a registry patch proposal.

## Workflow

1. Work on one formation. A batch must be explicitly bounded and small enough to keep every evidence trail separate.
2. Call `get_formation_context`. Inspect all source assertions, dates, aliases, locality role, image references, and existing reviewed resolution.
3. Reconcile aliases before spatial work. Stop and preserve the ambiguity if two reports may describe the same event but cannot be reconciled.
4. Call `create_field_resolution_job` and `set_location_clues`. Every material clue needs confidence, source URL, and assertion ID where available.
5. Define exclusions and a defensible bounded polygon with `resolve_search_area`. Record it only as `locality_search_area`.
6. Call `search_imagery` for the relevant acquisition interval and record provider, collection, rights metadata, and limitations.
7. Call `generate_candidate_tiles`, then `rank_candidate_tiles`. Stop at a small top-K list, normally 20 or fewer and never over the configured 50-candidate ceiling.
8. Run `match_candidate` only against the selected top candidates. Retain negative results so identical fields are not searched again without changed evidence, imagery, or algorithms.
9. Send viable registrations to the reviewer. Use `validate_registration` only with controls and separately held-out checkpoints.
10. Preserve `unresolved` or `deferred` when evidence is inadequate. An unresolved result is a valid research output.

## Prohibitions

- Never promote a town, postcode, county, map-label, or locality centroid to a field or site.
- Never browse satellite imagery without a bounded job polygon and stop condition.
- Never ask a language model to visually guess among thousands of fields.
- Never treat retrieval score, SIFT fit, a four-point transform, or control residual as independent accuracy.
- Never expose credentials, return large rasters through MCP, or commit provider pixels, caches, or model weights.
- Never mutate the canonical site registry during machine processing.

## Handoff

Return job ID, artifact paths and hashes, candidate count, top-K scores, searched provider/date coverage, rejected evidence, limitations, current state, and next valid states. State explicitly that every surviving registration is still a machine proposal.
