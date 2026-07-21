#!/usr/bin/env python3
"""Ingest a resolved registration and north-up PNG into image_assets.csv.

Publication-authorized derivatives are copied into ``assets/registered-overlays``.
Private and permission-pending derivatives are registered by hash but are not
copied into the repository, so the combined KMZ generator excludes them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from PIL import Image

try:
    from .georeference_image import (
        PUBLIC_RIGHTS, RegistrationError, plan_raster, rights_qualification,
        solve_registration,
    )
except ImportError:  # Direct ``python scripts/ingest_georeference.py`` execution.
    from georeference_image import (
        PUBLIC_RIGHTS, RegistrationError, plan_raster, rights_qualification,
        solve_registration,
    )


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "crop-circle-atlas/georeference-registration/v1"
IMAGE_ASSET_FIELDS = [
    "asset_id", "formation_id", "source_url", "local_path", "sha256",
    "rights_status", "rights_holder", "license", "rights_proof",
    "control_points_json", "transform_rmse_m", "reviewer", "reviewed_at", "notes",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stem(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "._-" else "-" for character in value)
    cleaned = "-".join(part for part in cleaned.split("-") if part).strip("-.")
    if not cleaned:
        raise RegistrationError("asset_id does not contain a filesystem-safe character")
    return cleaned


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        unknown = set(reader.fieldnames) - set(IMAGE_ASSET_FIELDS)
        if unknown:
            raise RegistrationError(f"image-assets file has unsupported columns: {', '.join(sorted(unknown))}")
        return [{field: row.get(field, "") for field in IMAGE_ASSET_FIELDS} for row in reader]


def write_rows_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", dir=path.parent, delete=False,
        prefix=f".{path.name}.", suffix=".tmp",
    ) as handle:
        temporary = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=IMAGE_ASSET_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def registered_corners(output: dict) -> dict:
    bounds = output.get("bounds_wgs84", {})
    try:
        west = float(bounds["west"])
        south = float(bounds["south"])
        east = float(bounds["east"])
        north = float(bounds["north"])
    except (KeyError, TypeError, ValueError) as error:
        raise RegistrationError("registration output lacks finite WGS84 bounds") from error
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise RegistrationError("registration output WGS84 bounds are invalid")
    return {
        "corners": {
            "nw": {"latitude": north, "longitude": west},
            "ne": {"latitude": north, "longitude": east},
            "se": {"latitude": south, "longitude": east},
            "sw": {"latitude": south, "longitude": west},
        },
        "source": "north_up_epsg3857_output_bounds",
    }


def validate_registration_geometry(metadata: dict) -> None:
    source = metadata.get("source_image", {})
    try:
        source_size = (int(source["width_px"]), int(source["height_px"]))
    except (KeyError, TypeError, ValueError) as error:
        raise RegistrationError("registration lacks source-image dimensions") from error
    if source_size[0] <= 0 or source_size[1] <= 0:
        raise RegistrationError("registration source-image dimensions are invalid")
    solved = solve_registration(metadata, source_size)
    recorded_transform = metadata.get("transform", {})
    if recorded_transform.get("distance_measurement") != "spherical_geodesic_ground_metres":
        raise RegistrationError("registration residual units are not verified physical ground metres")
    recorded_matrix = recorded_transform.get("image_pixel_to_web_mercator")
    if not isinstance(recorded_matrix, list) or len(recorded_matrix) != 3:
        raise RegistrationError("registration lacks a projective transform matrix")
    for recorded_row, solved_row in zip(recorded_matrix, solved["image_pixel_to_web_mercator"], strict=True):
        if not isinstance(recorded_row, list) or len(recorded_row) != 3:
            raise RegistrationError("registration transform matrix is malformed")
        for recorded, expected in zip(recorded_row, solved_row, strict=True):
            tolerance = max(1e-7, abs(expected) * 1e-11)
            try:
                recorded_value = float(recorded)
            except (TypeError, ValueError) as error:
                raise RegistrationError("registration transform matrix is malformed") from error
            if abs(recorded_value - expected) > tolerance:
                raise RegistrationError("recorded transform does not match control points")
    try:
        recorded_rmse = float(recorded_transform.get("control_point_rmse_m", -1))
    except (TypeError, ValueError) as error:
        raise RegistrationError("registration ground-distance RMSE is malformed") from error
    if abs(recorded_rmse - solved["control_point_rmse_m"]) > max(1e-7, solved["control_point_rmse_m"] * 1e-8):
        raise RegistrationError("recorded ground-distance RMSE does not match control points")

    output = metadata.get("output", {})
    try:
        output_size = (int(output["width_px"]), int(output["height_px"]))
    except (KeyError, TypeError, ValueError) as error:
        raise RegistrationError("registration output dimensions are missing") from error
    recomputed_plan = plan_raster(
        solved["image_pixel_to_web_mercator"], source_size[0], source_size[1], max(output_size)
    )
    if output_size != (recomputed_plan["width_px"], recomputed_plan["height_px"]):
        raise RegistrationError("registration output dimensions do not match the control-point transform")
    recorded_bounds = output.get("bounds_wgs84", {})
    for key, expected in recomputed_plan["bounds_wgs84"].items():
        try:
            recorded = float(recorded_bounds[key])
        except (KeyError, TypeError, ValueError) as error:
            raise RegistrationError("registration output WGS84 bounds are missing") from error
        if abs(recorded - expected) > 1e-8:
            raise RegistrationError("registration output bounds do not match the control-point transform")


def build_asset_row(metadata: dict, warped_png: Path, repo_root: Path) -> tuple[dict[str, str], Path | None]:
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise RegistrationError(f"unsupported registration schema; expected {SCHEMA_VERSION}")
    validate_registration_geometry(metadata)
    asset = metadata.get("asset", {})
    asset_id = str(asset.get("asset_id", "")).strip()
    formation_id = str(metadata.get("formation_id", "")).strip()
    if not asset_id or not formation_id:
        raise RegistrationError("registration requires asset_id and formation_id")
    if not warped_png.is_file():
        raise RegistrationError(f"warped PNG does not exist: {warped_png}")
    if warped_png.suffix.lower() != ".png":
        raise RegistrationError("warped raster must be a PNG")
    output = metadata.get("output", {})
    if output.get("crs") != "EPSG:3857" or output.get("north_up") is not True:
        raise RegistrationError("registration output must be a north-up EPSG:3857 raster")
    transform = metadata.get("transform", {})
    with Image.open(warped_png) as image:
        image.load()
        if image.format != "PNG":
            raise RegistrationError("warped raster content is not PNG")
        expected_size = (int(output.get("width_px", 0)), int(output.get("height_px", 0)))
        if image.size != expected_size:
            raise RegistrationError(f"warped PNG dimensions {image.size} do not match metadata {expected_size}")

    rights = asset.get("rights", {})
    status = str(rights.get("status", "local_analysis_only")).strip().lower()
    publishable, rights_reasons = rights_qualification(rights)
    if status in PUBLIC_RIGHTS and not publishable:
        raise RegistrationError("publication-authorized status is incomplete: " + ", ".join(rights_reasons))
    reviewer = str(metadata.get("review", {}).get("reviewer", "")).strip()
    reviewed_at = str(metadata.get("review", {}).get("reviewed_at", "")).strip()
    if not reviewer or not reviewed_at:
        raise RegistrationError("registration requires reviewer and reviewed_at before image-assets ingest")

    png_hash = sha256_file(warped_png)
    destination = None
    local_path = ""
    if publishable:
        destination = repo_root / "assets" / "registered-overlays" / f"{safe_stem(asset_id)}-{png_hash[:16]}.png"
        local_path = destination.relative_to(repo_root).as_posix()
    corners = registered_corners(output)
    source_hash = str(metadata.get("source_image", {}).get("sha256", ""))
    notes = {
        "distance_measurement": transform["distance_measurement"],
        "registration_id": metadata.get("registration_id", ""),
        "source_image_sha256": source_hash,
        "warped_raster": "copied_for_combined_kmz" if publishable else "private_not_copied",
    }
    row = {
        "asset_id": asset_id,
        "formation_id": formation_id,
        "source_url": str(asset.get("source_url", "")).strip(),
        "local_path": local_path,
        "sha256": png_hash,
        "rights_status": status,
        "rights_holder": str(rights.get("holder", "")).strip(),
        "license": str(rights.get("license", "")).strip(),
        "rights_proof": str(rights.get("proof", "")).strip(),
        "control_points_json": json.dumps(corners, sort_keys=True, separators=(",", ":")),
        "transform_rmse_m": format(float(transform.get("control_point_rmse_m", 0)), ".12g"),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "notes": json.dumps(notes, sort_keys=True, separators=(",", ":")),
    }
    return row, destination


def ingest_registration(registration_path: Path, warped_png: Path, repo_root: Path = ROOT,
                        image_assets_path: Path | None = None, replace: bool = False) -> dict[str, str]:
    registration_path = registration_path.resolve()
    warped_png = warped_png.resolve()
    repo_root = repo_root.resolve()
    image_assets_path = (image_assets_path or repo_root / "data" / "image_assets.csv").resolve()
    metadata = json.loads(registration_path.read_text(encoding="utf-8"))
    row, destination = build_asset_row(metadata, warped_png, repo_root)
    formations_path = repo_root / "data" / "formations.csv"
    if not formations_path.is_file():
        raise RegistrationError("repo root does not contain data/formations.csv")
    with formations_path.open(encoding="utf-8-sig", newline="") as handle:
        formation_ids = {item.get("formation_id", "") for item in csv.DictReader(handle)}
    if row["formation_id"] not in formation_ids:
        raise RegistrationError(f"formation_id does not exist in data/formations.csv: {row['formation_id']}")
    rows = load_rows(image_assets_path)
    existing = next((item for item in rows if item["asset_id"] == row["asset_id"]), None)
    if existing and existing != row and not replace:
        raise RegistrationError(f"asset_id already exists with different metadata: {row['asset_id']}")

    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha256_file(destination) != row["sha256"]:
            raise RegistrationError(f"destination exists with different content: {destination}")
        if not destination.exists():
            shutil.copyfile(warped_png, destination)

    updated = [item for item in rows if item["asset_id"] != row["asset_id"]]
    updated.append(row)
    updated.sort(key=lambda item: item["asset_id"])
    write_rows_atomic(image_assets_path, updated)
    return row


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", required=True, type=Path, help="resolved v1 registration JSON")
    parser.add_argument("--warped-png", required=True, type=Path, help="north-up PNG produced from that registration")
    parser.add_argument("--repo-root", type=Path, default=ROOT, help="atlas repository root")
    parser.add_argument("--image-assets", type=Path, help="override image_assets.csv path")
    parser.add_argument("--replace", action="store_true", help="replace one existing row with the same asset_id")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        row = ingest_registration(
            args.registration, args.warped_png, args.repo_root,
            image_assets_path=args.image_assets, replace=args.replace,
        )
    except (OSError, json.JSONDecodeError, RegistrationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(row, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
