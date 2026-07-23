# Geolocator dependency and model license audit

Checked against official package metadata or upstream repositories on 2026-07-22. "Imported" means runtime code imports the package. "Adapter only" means this repository contains an interface but no third-party code or weights. Source-photo rights are governed separately by `DATA_RIGHTS.md` and per-item records.

## Selected runtime

| Component | Version | Upstream | License / obligations | Use and decision |
|---|---:|---|---|---|
| Rasterio | 1.5.0 | [PyPI](https://pypi.org/project/rasterio/) | BSD-3-Clause; preserve notice | Imported for raster discovery/windows/tiles. |
| GDAL | wheel transitive | [GDAL license](https://gdal.org/en/stable/license.html) | MIT/X-style; preserve notice | Native Rasterio dependency; not called as a separate service. |
| pyproj / PROJ | 3.7.2 / wheel transitive | [pyproj](https://pypi.org/project/pyproj/) | MIT; PROJ MIT | Imported for CRS/geodesy. Preserve notices on redistribution. |
| Shapely / GEOS | 2.1.2 / wheel transitive | [Shapely](https://github.com/shapely/shapely) | Shapely BSD-3; GEOS LGPL-2.1 | Imported for geometry. Unmodified dynamic wheel dependency. |
| Affine | 2.4.0 | [PyPI](https://pypi.org/project/affine/) | BSD-3-Clause | Imported/transitive raster transforms. |
| NumPy | 2.3.5 | [PyPI](https://pypi.org/project/numpy/) | BSD-3-Clause; wheel also carries compatible notices for OpenBLAS/LAPACK and GCC runtime exception | Imported for numerical work. |
| OpenCV / opencv-python-headless | 4.13.0.92 | [OpenCV license](https://opencv.org/license/) | Apache-2.0; wheel build scripts MIT; bundled codec notices apply | Imported for SIFT, RANSAC, image transforms. |
| Pillow | 12.2.0 | [PyPI](https://pypi.org/project/pillow/) | MIT-CMU/HPND-style | Imported for deterministic PNG output. |
| jsonschema | 4.26.0 | [PyPI](https://pypi.org/project/jsonschema/) | MIT | Imported for contract validation. |
| FastAPI | 0.133.1 | [PyPI](https://pypi.org/project/fastapi/) | MIT | Optional `server` extra. Local API only. |
| Uvicorn | 0.41.0 | [PyPI](https://pypi.org/project/uvicorn/) | BSD-3-Clause | Optional local server. |
| MCP Python SDK | 1.28.1 (<2) | [official repository](https://github.com/modelcontextprotocol/python-sdk) | MIT | Optional server extra; current stable v1 API. |
| PySTAC Client | 0.9.0 | [official repository](https://github.com/stac-utils/pystac-client) | Apache-2.0 | Optional STAC search adapter. |
| PySTAC | 1.15.1 | [official repository](https://github.com/stac-utils/pystac) | Apache-2.0 | Transitive STAC object model. |
| Planetary Computer SDK | 1.0.0 | [official docs](https://planetarycomputer.microsoft.com/docs/quickstarts/reading-stac/) | MIT | Optional asset signing/search. Provider terms still govern imagery. |
| pytest / pytest-cov / coverage | 9.0.2 / 7.0.0 / installed transitive | official PyPI packages | MIT / MIT / Apache-2.0 | Development and CI only. |
| Leaflet | 1.9.4 CDN | [license](https://github.com/Leaflet/Leaflet/blob/main/LICENSE) | BSD-2-Clause; attribution | Existing browser map, not vendored. Tile-provider attribution remains visible. |

## Direct transitives

These are installed by the selected extras and no code is copied into the repository:

| Group | Packages and license |
|---|---|
| Raster/validation | `attrs` MIT; `click` BSD-3; `cligj` BSD; `pyparsing` MIT; `certifi` MPL-2.0; `jsonschema-specifications`, `referencing`, `rpds-py` MIT. |
| FastAPI/Pydantic | `starlette` BSD-3; `pydantic`, `pydantic-core`, `typing-inspection`, `annotated-types`, `annotated-doc`, `anyio` MIT; `typing-extensions` PSF-2.0; `idna` BSD-3. |
| Uvicorn | `h11` MIT. |
| MCP | `httpx`, `httpcore` BSD-3; `httpx-sse` MIT; `sse-starlette` BSD-3; `pydantic-settings` MIT; `python-multipart` Apache-2.0; `python-dotenv` BSD-3; `PyJWT` MIT; `cryptography` Apache-2.0 OR BSD-3; `cffi` MIT-0. |
| STAC/Planetary | `requests` Apache-2.0; `urllib3`, `charset-normalizer`, `pytz`, `six` MIT; `python-dateutil` dual BSD/Apache; PySTAC extension packages Apache-2.0. |

Binary wheels may contain additional compatible notices. Release packaging must retain the license files supplied by wheels and re-run metadata/license review after upgrades. Provider imagery terms and attribution are not inferred from library licenses.

## Evaluated retrieval, matching, and browser projects

| Project | Upstream | Code license / weight status | Integration status and rationale |
|---|---|---|---|
| AnyLoc | [repository](https://github.com/AnyLoc/AnyLoc) | BSD-3-Clause code; selected backbone/weight terms must be reviewed separately | Adapter only, disabled. No code or weights copied. |
| MegaLoc | [repository](https://github.com/gmberton/megaloc) | MIT code; checkpoint/dataset terms require per-model review | Adapter only, disabled. |
| EarthLoc | [repository](https://github.com/gmberton/EarthLoc) | MIT code verified | Studied only; no code or weights copied. |
| EarthMatch | [repository](https://github.com/gmberton/EarthMatch) | No compatible top-level license was confirmed during this audit | Architectural reference only, as required. No import. |
| LightGlue | [repository](https://github.com/cvg/LightGlue) | Apache-2.0 implementation and LightGlue weights; feature extractor weights vary and SuperPoint terms are restrictive | Adapter only, disabled pending an explicitly selected compatible detector/weight pair. |
| VisMatch | upstream wrapper/model not locked | Wrapper and selected model/weight licenses unresolved | Adapter only and fail-closed. |
| GIM matchers | upstream/model not locked | Per-matcher code and weight terms vary | Not integrated. Requires separate audit. |
| Leaflet.DistortableImage | [npm](https://www.npmjs.com/package/leaflet-distortableimage) / [repository](https://github.com/publiclab/Leaflet.DistortableImage) | MIT, current package line 0.21.x | Compatible but not integrated; the repository's tested projective-registration code is reused instead. |
| Allmaps | [project](https://allmaps.org/) | Individual packages may be MIT; application code includes GPL components | No application code imported. Package-by-package approval required. |
| TiTiler | [repository](https://github.com/developmentseed/titiler) | MIT | Evaluated, not imported. Direct local cutouts are sufficient for MVP. |
| rio-cogeo | [repository](https://github.com/cogeotiff/rio-cogeo) | BSD-3-Clause | Evaluated, not imported. No COG creation requirement in MVP. |

## Redistribution and data decisions

- No third-party repository, model weight, provider raster, historical satellite image, or source photograph is vendored.
- Model caches are external and ignored. Any future model activation must record code commit, weight identifier/hash, license, training-data caveat, and redistribution terms.
- Library license compatibility does not authorize source-image redistribution. Public KMZ generation validates the per-image rights record and fails closed.
- CDN Leaflet and all basemaps retain visible attribution. Offline redistribution would require bundling the applicable license texts and respecting tile-provider terms.
