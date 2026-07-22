# Crop Circle Geolocator setup

## Requirements

- Python 3.12 or newer
- Node.js for the existing browser tests
- Optional Docker Desktop
- Local GeoTIFF/COG imagery or access to a STAC/Planetary Computer/USGS provider for real searches

From the repository root:

```powershell
python -m pip install -e "services/geolocator[dev,server,stac]"
python -m pytest services/geolocator/tests -q
python -m crop_circle_geo.cli benchmark --manifest services/geolocator/benchmarks/reviewed-cases-input.json
python scripts/verify.py
```

## Configuration

Copy `.env.example` to an ignored `.env` or set variables in the shell. The example contains names only. The worker does not automatically load `.env`; use the shell, Docker Compose, or your process manager.

Safe defaults are 2,500 km2 maximum search area, 100 imagery items, 10,000 tile variants, top 50 candidates, 0.25 tile overlap, 1 GiB per file, one-hour processing timeout, and two workers. Lower these limits for laptops.

Important variables include `CROP_CIRCLE_ATLAS_ROOT`, `CROP_CIRCLE_GEO_CACHE`, `CROP_CIRCLE_GEO_MODEL_CACHE`, `CROP_CIRCLE_GEO_MAX_*`, `USGS_M2M_USERNAME`, `USGS_M2M_APP_TOKEN`, and `USGS_M2M_TOKEN`. Never place values in Git.

## Run the local service

```powershell
python -m crop_circle_geo.cli serve-api
```

Serve `web/` from a local static server, open `geolocation-review.html`, and connect to `http://127.0.0.1:8765`. The public GitHub Pages reviewer clearly reports an offline state when this worker is absent.

Run MCP over standard input/output:

```powershell
python -m crop_circle_geo.mcp_server
```

The MCP client must set `CROP_CIRCLE_ATLAS_ROOT` to this repository and should set `CROP_CIRCLE_GEO_CACHE` to an external working directory.

## Local raster metadata

Place `.tif` or `.tiff` files in a directory outside Git. Each raster must have a CRS. An optional adjacent file such as `historic.tif.metadata.json` can specify:

```json
{
  "collection": "local-historical",
  "item_id": "flight-1998-07-01",
  "acquisition_start": "1998-07-01",
  "acquisition_end": "1998-07-01",
  "orthorectified": true,
  "ground_sample_distance_m": 1.0,
  "rights": {
    "status": "local_analysis_only",
    "holder": null,
    "license": null,
    "proof": null,
    "public_derivative_export_allowed": false
  }
}
```

The tile generator requires a projected, metre-based raster CRS. Reproject geographic rasters before tiling.

## Command workflow

Use `python -m crop_circle_geo.cli --help`. The sequence is `context`, `create-job`, `set-clues`, `set-search-area`, `search-imagery`, `generate-tiles`, `rank`, `match`, `validate`, `review`, and optionally `measure-component` or `generate-overlay`. `promote-reviewed-resolution --confirm` creates a patch proposal only; it does not mutate `data/site_resolutions.csv`.

## Docker

Create a local `local-imagery/` directory and optionally an ignored `.env`, then run:

```powershell
docker compose -f docker-compose.geolocator.yml up --build
```

The container filesystem is read-only except for `/cache` and `/tmp`; the port is published only at `127.0.0.1:8765`.

## External-service boundaries

- Generic STAC and Planetary Computer searches need network access. Planetary Computer asset URLs are signed with its SDK.
- USGS M2M needs account/app credentials in environment variables and is not exercised live in tests.
- No large learned model is downloaded by base, CI, server, or STAC installation. Optional adapter activation requires a separate license and benchmark review.
