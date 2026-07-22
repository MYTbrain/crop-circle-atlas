# Crop Circle Geolocator

Local, deterministic field-candidate search and reviewed aerial-image registration for Crop Circle Atlas. The worker writes versioned evidence to an external cache and never edits the canonical catalog during machine processing.

Install the lightweight development and local-service groups from the repository root:

```powershell
python -m pip install -e "services/geolocator[dev,server,stac]"
```

See `docs/GEOLOCATOR_SETUP.md` for configuration and `docs/GEOLOCATOR_EVIDENCE_RULES.md` for the mandatory review boundary.

The worker includes local GeoTIFF/COG, generic STAC, Planetary Computer, and USGS M2M provider adapters; physical tile generation; deterministic CPU retrieval; OpenCV SIFT/RANSAC registration; independent checkpoint validation; conservative uncertainty; a 14-tool MCP server; a localhost API; and rights-gated KML/KMZ export.

```powershell
python -m crop_circle_geo.cli serve-api
python -m crop_circle_geo.mcp_server
python -m crop_circle_geo.cli benchmark --manifest services/geolocator/benchmarks/reviewed-cases-input.json --synthetic
```

Open `web/geolocation-review.html` through a local static server for the reviewer workbench. The public page remains useful as documentation when the local worker is offline.
