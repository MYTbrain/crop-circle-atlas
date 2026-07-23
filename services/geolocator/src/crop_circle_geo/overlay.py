"""Deterministic local-analysis and rights-gated publication KMZ export."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import cv2
import numpy as np
from PIL import Image

from .provenance import canonical_json, sha256_file
from .rights import require_publication_rights


def _deterministic_zip(path: Path, members: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, payload)


def _kml(review: dict[str, Any], tile: dict[str, Any], image_name: str, local_analysis: bool) -> str:
    coordinates = tile["physical_footprint"]["coordinates"][0]
    lons = [float(point[0]) for point in coordinates]
    lats = [float(point[1]) for point in coordinates]
    caveat = (
        "LOCAL ANALYSIS ONLY. This package is not authorized for publication or redistribution."
        if local_analysis else "Publication package authorized by the recorded review and asset-rights proof."
    )
    rights = review.get("rights_decision", {})
    extended = {
        "job_id": review.get("job_id", ""), "formation_id": review.get("formation_id", ""),
        "review_id": review.get("review_id", ""), "reviewer": review.get("reviewer", ""),
        "reviewed_at": review.get("reviewed_at", ""), "spatial_classification": review.get("spatial_classification", ""),
        "coordinate_uncertainty_m": review.get("coordinate_uncertainty_m", ""),
        "rights_status": rights.get("status", "local_analysis_only"), "rights_holder": rights.get("holder", ""),
        "license": rights.get("license", ""), "rights_proof": rights.get("proof", ""),
        "publication_eligible": str(not local_analysis).lower(), "caveat": caveat,
    }
    data = "".join(f'<Data name="{escape(str(key))}"><value>{escape(str(value))}</value></Data>' for key, value in extended.items())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f'<name>{escape(str(review.get("formation_id", "formation")))} registered overlay</name>'
        f'<description>{escape(caveat)}</description><GroundOverlay><name>Reviewed registration</name>'
        f'<description>{escape(caveat)}</description><ExtendedData>{data}</ExtendedData>'
        f'<Icon><href>{escape(image_name)}</href></Icon><LatLonBox><north>{max(lats):.12f}</north>'
        f'<south>{min(lats):.12f}</south><east>{max(lons):.12f}</east><west>{min(lons):.12f}</west>'
        '</LatLonBox></GroundOverlay></Document></kml>'
    )


def generate_overlay(
    review: dict[str, Any],
    registration_candidate: dict[str, Any],
    tile: dict[str, Any],
    source_image: Path,
    output_dir: Path,
    public_export: bool = False,
) -> dict[str, Any]:
    if not review.get("reviewer") or review.get("decision") not in {"accepted", "downgraded"}:
        raise ValueError("overlay generation requires an explicit accepted or downgraded human review")
    if registration_candidate.get("machine_status") != "review_required":
        raise ValueError("rejected or insufficient machine registrations cannot be exported")
    if public_export:
        if review.get("publication_eligible") is not True:
            raise PermissionError("review did not explicitly authorize publication")
        require_publication_rights(review.get("rights_decision"))
    source = cv2.imread(str(source_image), cv2.IMREAD_COLOR)
    if source is None:
        raise ValueError(f"unable to read source image: {source_image}")
    width, height = map(int, tile["dimensions_px"])
    matrix = np.asarray(registration_candidate["homography"], dtype=np.float64)
    color = cv2.warpPerspective(source, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
    source_mask = np.full(source.shape[:2], 255, dtype=np.uint8)
    alpha = cv2.warpPerspective(source_mask, matrix, (width, height), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
    rgba = cv2.cvtColor(color, cv2.COLOR_BGR2RGBA)
    rgba[..., 3] = alpha
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{review['formation_id']}-{review['review_id']}"
    image_path = output_dir / f"{stem}.png"
    Image.fromarray(rgba).save(image_path, format="PNG", optimize=False, compress_level=9)
    kml_payload = _kml(review, tile, image_path.name, local_analysis=not public_export).encode("utf-8")
    kml_path = output_dir / f"{stem}.kml"
    kml_path.write_bytes(kml_payload)
    resolved = {
        "review_sha256": __import__("hashlib").sha256(canonical_json(review)).hexdigest(),
        "registration_candidate_id": registration_candidate["registration_candidate_id"],
        "source_image_sha256": sha256_file(source_image), "overlay_sha256": sha256_file(image_path),
        "public_export": public_export,
    }
    metadata_payload = canonical_json(resolved) + b"\n"
    kmz_path = output_dir / f"{stem}.kmz"
    _deterministic_zip(kmz_path, [("doc.kml", kml_payload), (image_path.name, image_path.read_bytes()), ("metadata.json", metadata_payload)])
    return {
        **resolved, "image_path": str(image_path), "kml_path": str(kml_path), "kmz_path": str(kmz_path),
        "kmz_sha256": sha256_file(kmz_path),
    }
