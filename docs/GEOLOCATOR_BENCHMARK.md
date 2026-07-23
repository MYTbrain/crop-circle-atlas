# Crop Circle Geolocator benchmark

## Separation and leakage control

`services/geolocator/benchmarks/reviewed-cases-input.json` contains only report clues, locality-level search information, dates, source references, and rights decisions. `evaluator-only-ground-truth.json` contains reviewed final coordinates/footprints and can be loaded only through the explicit evaluator path. The input loader rejects exact-coordinate keys. Search, retrieval, and matching modules never receive evaluator coordinates.

Source pixels are included only when the manifest records permission for local benchmarking. A link or an open-license label alone is not silently converted into a downloaded fixture.

## Real-world manifest

Nine cases are preregistered: Whiskey Hill/Hubbard 1998, Wavra Farm 1997, Rockville 1 and 2 (2003), Wausau 1997, Miamisburg 2004, Hopewell/Chillicothe 2012, Albion/Starr 2002, and Diessenhofen 2008. Eight are metadata-only because source-image rights are not cleared. Diessenhofen references a CC BY-SA 3.0 Wikimedia Commons source and is the only pixel-permitted candidate, but its required historical reference raster is not packaged.

Current real-world result: **0 of 9 cases have been run end to end in this benchmark**. Therefore top-K recall, field-center error, footprint error, checkpoint error, false-acceptance rate, unresolved rate, and effectiveness are **not measured** for real data. Existing reviewed atlas placements are benchmark candidates/ground truth, not outputs from this new pipeline.

## Synthetic result

The deterministic positive case generates a 1 m/pixel projected GeoTIFF, extracts a source view with projective crop, blur, contrast and brightness changes, searches one imagery item, generates four tiles, performs CPU retrieval, and runs SIFT/RANSAC. The snapshot in `mvp-results.json`, run on 2026-07-22, records:

| Metric | Synthetic result |
|---|---:|
| Correct tile rank | 1 |
| Top-1 / top-5 / top-10 / top-50 recall | 1.0 / 1.0 / 1.0 / 1.0 |
| Formation-center error at 1 m GSD | 0.042369 m |
| Mean / maximum footprint-corner error | 0.327789 / 0.492662 m |
| Checkpoint median / RMSE / maximum | 0.121591 / 0.131853 / 0.190322 m |
| SIFT inliers / inlier ratio | 117 / 0.59390863 |
| Imagery items / tiles searched | 1 / 4 |
| Cache hits / misses / hit rate on repeated work | 9 / 9 / 0.5 |
| Device | CPU |

Stage times are recorded in the JSON snapshot but are environment-specific. False-acceptance rate is `not_measured_no_negative_synthetic_cases`; one positive case cannot estimate it. The synthetic unresolved/defer rate was 0 for this case only.

This result validates coordinate, tiling, retrieval, projective recovery, and error-measurement mathematics. It is explicitly not evidence that the system can geolocate real crop-circle photographs.

## Run

Describe the real-world manifest without accessing evaluator truth:

```powershell
python -m crop_circle_geo.cli benchmark --manifest services/geolocator/benchmarks/reviewed-cases-input.json
```

Run the separate synthetic benchmark:

```powershell
python -m crop_circle_geo.cli benchmark --manifest services/geolocator/benchmarks/reviewed-cases-input.json --synthetic
```

CI runs `test_complete_synthetic_benchmark_recovers_known_transform` with center <4 m, maximum corner <10 m, and maximum synthetic checkpoint <5 m at 1 m GSD.

## Required next benchmark phase

Obtain publication or private-benchmark permission for a balanced real set, acquire contemporaneous orthorectified reference imagery, preregister search polygons and negative fields, lock evaluator truth, and measure all specified metrics. Include hard agricultural negatives so false acceptance is estimable. Compare CPU retrieval/SIFT before enabling learned adapters.
