#!/usr/bin/env python3
"""Create deterministic local georeferencing artifacts from a browser registration.

The source image is read from disk and is never transmitted. By default the
outputs are local-analysis artifacts. ``--public-export`` fails closed unless
the registration records a publication-compatible rights status.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
import zipfile
from html import escape
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image


SCHEMA_VERSION = "crop-circle-atlas/georeference-registration/v1"
TOOL_VERSION = "1.0.0"
WEB_MERCATOR_RADIUS_M = 6_378_137.0
MAX_MERCATOR_LAT = 85.0511287798066
EPSILON = 1e-12
PUBLIC_RIGHTS = {
    "public_domain", "cc0", "cc_by", "cc_by_sa", "licensed",
    "permission_granted", "owner_supplied_publication_authorized",
}
LICENSE_RIGHTS = {"cc0", "cc_by", "cc_by_sa", "licensed"}
HOLDER_REQUIRED_RIGHTS = {
    "cc_by", "cc_by_sa", "licensed", "permission_granted",
    "owner_supplied_publication_authorized",
}
WKT_EPSG_3857 = (
    'PROJCS["WGS 84 / Pseudo-Mercator",GEOGCS["WGS 84",'
    'DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
    'PROJECTION["Mercator_1SP"],PARAMETER["central_meridian",0],'
    'PARAMETER["scale_factor",1],PARAMETER["false_easting",0],'
    'PARAMETER["false_northing",0],UNIT["metre",1],AXIS["X",EAST],AXIS["Y",NORTH]]'
)


class RegistrationError(ValueError):
    """Raised when registration evidence is incomplete or geometrically invalid."""


def lonlat_to_mercator(longitude: float, latitude: float) -> tuple[float, float]:
    if not (math.isfinite(longitude) and math.isfinite(latitude)):
        raise RegistrationError("Longitude and latitude must be finite numbers")
    latitude = max(-MAX_MERCATOR_LAT, min(MAX_MERCATOR_LAT, latitude))
    x = WEB_MERCATOR_RADIUS_M * math.radians(longitude)
    y = WEB_MERCATOR_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
    return x, y


def mercator_to_lonlat(x: float, y: float) -> tuple[float, float]:
    return (
        math.degrees(x / WEB_MERCATOR_RADIUS_M),
        math.degrees(2 * math.atan(math.exp(y / WEB_MERCATOR_RADIUS_M)) - math.pi / 2),
    )


def great_circle_distance_metres(start: Sequence[float], end: Sequence[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*start, *end))
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (math.sin(delta_lat / 2) ** 2
                 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2)
    return 6_371_008.8 * 2 * math.asin(min(1.0, math.sqrt(haversine)))


def projected_ground_distance_metres(start: Sequence[float], end: Sequence[float]) -> float:
    return great_circle_distance_metres(mercator_to_lonlat(*start), mercator_to_lonlat(*end))


def geographic_midpoint(start: Sequence[float], end: Sequence[float]) -> tuple[float, float]:
    lon1, lat1 = map(math.radians, start)
    lon2, lat2 = map(math.radians, end)
    delta_lon = lon2 - lon1
    bx = math.cos(lat2) * math.cos(delta_lon)
    by = math.cos(lat2) * math.sin(delta_lon)
    latitude = math.atan2(math.sin(lat1) + math.sin(lat2), math.hypot(math.cos(lat1) + bx, by))
    longitude = lon1 + math.atan2(by, math.cos(lat1) + bx)
    return ((math.degrees(longitude) + 540) % 360 - 180, math.degrees(latitude))


def multiply(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> list[list[float]]:
    if not a or not b or len(a[0]) != len(b):
        raise RegistrationError("Matrix dimensions do not agree")
    return [[sum(value * b[index][column] for index, value in enumerate(row))
             for column in range(len(b[0]))] for row in a]


def inverse_3x3(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    (a, b, c), (d, e, f), (g, h, i) = matrix
    A, B, C = e * i - f * h, c * h - b * i, b * f - c * e
    D, E, F = f * g - d * i, a * i - c * g, c * d - a * f
    G, H, I = d * h - e * g, b * g - a * h, a * e - b * d
    determinant = a * A + b * D + c * G
    if not math.isfinite(determinant) or abs(determinant) < EPSILON:
        raise RegistrationError("Transform matrix is singular")
    return [[value / determinant for value in row] for row in ((A, B, C), (D, E, F), (G, H, I))]


def apply_homography(matrix: Sequence[Sequence[float]], point: Sequence[float]) -> tuple[float, float]:
    x, y = point
    denominator = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    if not math.isfinite(denominator) or abs(denominator) < EPSILON:
        raise RegistrationError("Point maps to the projective horizon")
    return (
        (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / denominator,
        (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / denominator,
    )


def solve_linear(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    size = len(vector)
    augmented = [list(row) + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < EPSILON:
            raise RegistrationError("Control points are degenerate or nearly collinear")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    return [row[size] for row in augmented]


def solve_least_squares(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    """Solve an overdetermined system with a Householder QR decomposition."""
    rows, columns = len(matrix), len(matrix[0])
    if rows < columns:
        raise RegistrationError("Not enough equations for the projective transform")
    qr = [list(row) for row in matrix]
    transformed = list(vector)
    for column in range(columns):
        norm = math.hypot(*(qr[row][column] for row in range(column, rows)))
        if norm < EPSILON:
            raise RegistrationError("Control points are degenerate or nearly collinear")
        alpha = -norm if qr[column][column] >= 0 else norm
        reflector = [qr[column][column] - alpha]
        reflector.extend(qr[row][column] for row in range(column + 1, rows))
        reflector_norm = sum(value * value for value in reflector)
        if reflector_norm < EPSILON:
            continue
        for target_column in range(column, columns):
            projection = 2 * sum(
                reflector[row - column] * qr[row][target_column]
                for row in range(column, rows)
            ) / reflector_norm
            for row in range(column, rows):
                qr[row][target_column] -= projection * reflector[row - column]
        projection = 2 * sum(
            reflector[row - column] * transformed[row] for row in range(column, rows)
        ) / reflector_norm
        for row in range(column, rows):
            transformed[row] -= projection * reflector[row - column]
    solution = [0.0] * columns
    for row in range(columns - 1, -1, -1):
        known = sum(qr[row][column] * solution[column] for column in range(row + 1, columns))
        if abs(qr[row][row]) < EPSILON:
            raise RegistrationError("Control points do not uniquely determine a projective transform")
        solution[row] = (transformed[row] - known) / qr[row][row]
    return solution


def normalize_points(points: Sequence[Sequence[float]]) -> tuple[list[list[float]], list[tuple[float, float]]]:
    center_x = sum(point[0] for point in points) / len(points)
    center_y = sum(point[1] for point in points) / len(points)
    mean_distance = sum(math.hypot(point[0] - center_x, point[1] - center_y) for point in points) / len(points)
    if not math.isfinite(mean_distance) or mean_distance < EPSILON:
        raise RegistrationError("Control points do not span a usable area")
    scale = math.sqrt(2) / mean_distance
    matrix = [[scale, 0.0, -scale * center_x], [0.0, scale, -scale * center_y], [0.0, 0.0, 1.0]]
    return matrix, [apply_homography(matrix, point) for point in points]


def _max_triangle_area(points: Sequence[Sequence[float]]) -> float:
    maximum = 0.0
    for first in range(len(points) - 2):
        for second in range(first + 1, len(points) - 1):
            for third in range(second + 1, len(points)):
                a, b, c = points[first], points[second], points[third]
                maximum = max(maximum, abs((b[0] - a[0]) * (c[1] - a[1])
                                           - (b[1] - a[1]) * (c[0] - a[0])) / 2)
    return maximum


def validate_point_set(points: Sequence[Sequence[float]], label: str) -> None:
    if len(points) < 4 or any(len(point) != 2 for point in points):
        raise RegistrationError(f"{label} must contain at least four 2D points")
    if any(not math.isfinite(value) for point in points for value in point):
        raise RegistrationError(f"{label} must contain finite values")
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    diagonal_squared = (max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2
    if diagonal_squared < EPSILON or _max_triangle_area(points) / diagonal_squared < 1e-5:
        raise RegistrationError(f"{label} are collinear or too tightly clustered")


def compute_homography(source: Sequence[Sequence[float]], target: Sequence[Sequence[float]]) -> list[list[float]]:
    validate_point_set(source, "Image control points")
    validate_point_set(target, "Map control points")
    if len(source) != len(target):
        raise RegistrationError("Image and map control-point counts differ")
    source_normalization, normalized_source = normalize_points(source)
    target_normalization, normalized_target = normalize_points(target)
    equations: list[list[float]] = []
    values: list[float] = []
    for (x, y), (X, Y) in zip(normalized_source, normalized_target, strict=True):
        equations.append([x, y, 1, 0, 0, 0, -x * X, -y * X])
        values.append(X)
        equations.append([0, 0, 0, x, y, 1, -x * Y, -y * Y])
        values.append(Y)
    h = solve_linear(equations, values) if len(equations) == 8 else solve_least_squares(equations, values)
    normalized = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]]
    result = multiply(multiply(inverse_3x3(target_normalization), normalized), source_normalization)
    divisor = result[2][2] if abs(result[2][2]) > EPSILON else math.sqrt(sum(value * value for row in result for value in row))
    return [[value / divisor for value in row] for row in result]


def solve_registration(metadata: dict, image_size: tuple[int, int]) -> dict:
    control_points = metadata.get("control_points")
    if not isinstance(control_points, list) or len(control_points) < 4:
        raise RegistrationError("At least four complete control-point pairs are required")
    image_points = [(float(point["image"]["x"]), float(point["image"]["y"])) for point in control_points]
    map_points = [lonlat_to_mercator(float(point["geographic"]["longitude"]),
                                     float(point["geographic"]["latitude"])) for point in control_points]
    matrix = compute_homography(image_points, map_points)
    residuals = [projected_ground_distance_metres(apply_homography(matrix, point), target)
                 for point, target in zip(image_points, map_points, strict=True)]
    rmse = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    plan = plan_raster(matrix, image_size[0], image_size[1], 2048)
    return {
        "type": "projective_homography",
        "source_crs": "image_pixel",
        "target_crs": "EPSG:3857",
        "image_pixel_to_web_mercator": matrix,
        "web_mercator_to_image_pixel": inverse_3x3(matrix),
        "control_point_residuals_m": residuals,
        "control_point_rmse_m": rmse,
        "max_control_point_residual_m": max(residuals),
        "distance_measurement": "spherical_geodesic_ground_metres",
        "accuracy_note": "A four-point fit is exact by construction. With additional points, residual measures internal fit but is not independent positional accuracy.",
        "footprint": plan["footprint"],
    }


def _is_convex(points: Sequence[Sequence[float]]) -> bool:
    sign = 0
    for index in range(len(points)):
        a, b, c = points[index], points[(index + 1) % len(points)], points[(index + 2) % len(points)]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) < EPSILON:
            continue
        current = 1 if cross > 0 else -1
        if sign and current != sign:
            return False
        sign = current
    return bool(sign)


def image_footprint(matrix: Sequence[Sequence[float]], width: int, height: int) -> dict:
    corners_image = [(0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height))]
    denominators = [matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] for x, y in corners_image]
    if any(not math.isfinite(value) or abs(value) < EPSILON for value in denominators) \
            or any(math.copysign(1, value) != math.copysign(1, denominators[0]) for value in denominators):
        raise RegistrationError("Transform crosses the projective horizon inside the image")
    corners = [apply_homography(matrix, point) for point in corners_image]
    if not _is_convex(corners):
        raise RegistrationError("Transformed image footprint is folded; check control-point pairing")
    xs, ys = [point[0] for point in corners], [point[1] for point in corners]
    return {
        "corners_image_pixel": [list(point) for point in corners_image],
        "corners_web_mercator": [list(point) for point in corners],
        "corners_wgs84": [list(mercator_to_lonlat(*point)) for point in corners],
        "bounds_web_mercator": {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)},
    }


def plan_raster(matrix: Sequence[Sequence[float]], source_width: int, source_height: int,
                max_dimension: int) -> dict:
    if not 64 <= max_dimension <= 8192:
        raise RegistrationError("Maximum output dimension must be between 64 and 8192")
    footprint = image_footprint(matrix, source_width, source_height)
    bounds = footprint["bounds_web_mercator"]
    width_metres = bounds["maxX"] - bounds["minX"]
    height_metres = bounds["maxY"] - bounds["minY"]
    if width_metres >= height_metres:
        width = max_dimension
        height = max(1, round(max_dimension * height_metres / width_metres))
    else:
        height = max_dimension
        width = max(1, round(max_dimension * width_metres / height_metres))
    west, south = mercator_to_lonlat(bounds["minX"], bounds["minY"])
    east, north = mercator_to_lonlat(bounds["maxX"], bounds["maxY"])
    return {
        "crs": "EPSG:3857",
        "width_px": width,
        "height_px": height,
        "bounds_web_mercator": bounds,
        "bounds_wgs84": {"west": west, "south": south, "east": east, "north": north},
        "pixel_size_m": {"x": width_metres / width, "y": height_metres / height},
        "pixel_size_unit": "EPSG:3857_projected_metre",
        "north_up": True,
        "transparent_outside_footprint": True,
        "footprint": footprint,
    }


def warp_image(image: Image.Image, inverse_matrix: Sequence[Sequence[float]], plan: dict) -> Image.Image:
    bounds = plan["bounds_web_mercator"]
    width, height = plan["width_px"], plan["height_px"]
    pixel_x = (bounds["maxX"] - bounds["minX"]) / width
    pixel_y = (bounds["maxY"] - bounds["minY"]) / height
    output_to_mercator = [
        [pixel_x, 0.0, bounds["minX"] + pixel_x / 2],
        [0.0, -pixel_y, bounds["maxY"] - pixel_y / 2],
        [0.0, 0.0, 1.0],
    ]
    output_to_source = multiply(inverse_matrix, output_to_mercator)
    divisor = output_to_source[2][2]
    if abs(divisor) < EPSILON:
        raise RegistrationError("Output transform cannot be normalized")
    output_to_source = [[value / divisor for value in row] for row in output_to_source]
    coefficients = (
        output_to_source[0][0], output_to_source[0][1], output_to_source[0][2],
        output_to_source[1][0], output_to_source[1][1], output_to_source[1][2],
        output_to_source[2][0], output_to_source[2][1],
    )
    return image.convert("RGBA").transform(
        (width, height),
        Image.Transform.PERSPECTIVE,
        coefficients,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )


def initial_bearing(start: Sequence[float], end: Sequence[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*start, *end))
    delta_lon = lon2 - lon1
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def destination(origin: Sequence[float], bearing: float, distance_metres: float) -> tuple[float, float]:
    radius = 6_371_008.8
    longitude, latitude = origin
    phi1, lambda1, theta = math.radians(latitude), math.radians(longitude), math.radians(bearing)
    delta = distance_metres / radius
    phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta))
    lambda2 = lambda1 + math.atan2(math.sin(theta) * math.sin(delta) * math.cos(phi1),
                                   math.cos(delta) - math.sin(phi1) * math.sin(phi2))
    return ((math.degrees(lambda2) + 540) % 360 - 180, math.degrees(phi2))


def resolve_straight_component(metadata: dict, matrix: Sequence[Sequence[float]]) -> dict | None:
    component = metadata.get("straight_component")
    if not component:
        return None
    try:
        a_image = component["endpoint_a"]["image"]
        b_image = component["endpoint_b"]["image"]
        a_projected = apply_homography(matrix, (float(a_image["x"]), float(a_image["y"])))
        b_projected = apply_homography(matrix, (float(b_image["x"]), float(b_image["y"])))
    except (KeyError, TypeError, ValueError) as error:
        raise RegistrationError("Straight-component endpoints are incomplete") from error
    a = mercator_to_lonlat(*a_projected)
    b = mercator_to_lonlat(*b_projected)
    forward, reverse = initial_bearing(a, b), initial_bearing(b, a)
    directionality = component.get("directionality", "bidirectional")
    if directionality not in {"forward", "reverse", "bidirectional"}:
        raise RegistrationError("Straight-component directionality must be forward, reverse, or bidirectional")
    midpoint = dict(zip(("longitude", "latitude"), geographic_midpoint(a, b), strict=True))
    recorded_origin_uncertainty = component.get("ray_origin", {}).get(
        "uncertainty_m", component.get("origin_uncertainty_m", 0)
    )
    resolved = copy.deepcopy(component)
    resolved.update({
        "endpoint_a": {"image": {"x": float(a_image["x"]), "y": float(a_image["y"])}, "longitude": a[0], "latitude": a[1]},
        "endpoint_b": {"image": {"x": float(b_image["x"]), "y": float(b_image["y"])}, "longitude": b[0], "latitude": b[1]},
        "midpoint": midpoint,
        "ray_origin": {
            "representative_point": "straight_component_midpoint",
            "latitude": midpoint["latitude"],
            "longitude": midpoint["longitude"],
            "uncertainty_m": float(recorded_origin_uncertainty),
        },
        "length_m": great_circle_distance_metres(a, b),
        "forward_azimuth_true_deg": forward,
        "reverse_azimuth_true_deg": reverse,
        "selected_azimuth_true_deg": reverse if directionality == "reverse" else forward,
        "directionality": directionality,
        "distance_measurement": "spherical_geodesic_ground_metres",
    })
    return resolved


def build_kml(metadata: dict, plan: dict, image_href: str, component: dict | None = None) -> str:
    asset = metadata.get("asset", {})
    asset_id = asset.get("asset_id") or metadata.get("formation_id") or "crop-circle-overlay"
    rights = asset.get("rights", {})
    rights_status = str(rights.get("status", "local_analysis_only"))
    rights_holder = str(rights.get("holder", ""))
    license_text = str(rights.get("license", ""))
    rights_proof = str(rights.get("proof", ""))
    source_url = str(asset.get("source_url", ""))
    bounds = plan["bounds_wgs84"]
    attribution = (
        f"Rights status: {rights_status}; rights holder/creator: {rights_holder or 'not supplied'}; "
        f"license: {license_text or 'not supplied'}; rights proof: {rights_proof or 'not supplied'}; "
        f"source: {source_url or 'not supplied'}. A local-analysis export is not publication authorization."
    )
    overlay = (
        f"<GroundOverlay><name>{escape(asset_id)} north-up overlay</name>"
        f"<description>{escape(attribution)}</description><ExtendedData>"
        f'<Data name="rights_status"><value>{escape(rights_status)}</value></Data>'
        f'<Data name="rights_holder"><value>{escape(rights_holder)}</value></Data>'
        f'<Data name="license"><value>{escape(license_text)}</value></Data>'
        f'<Data name="rights_proof"><value>{escape(rights_proof)}</value></Data>'
        f'<Data name="source_url"><value>{escape(source_url)}</value></Data></ExtendedData>'
        f"<Icon><href>{escape(image_href)}</href></Icon><LatLonBox>"
        f"<north>{bounds['north']:.10f}</north><south>{bounds['south']:.10f}</south>"
        f"<east>{bounds['east']:.10f}</east><west>{bounds['west']:.10f}</west><rotation>0</rotation>"
        "</LatLonBox></GroundOverlay>"
    )
    orientation = ""
    if component:
        a, b, midpoint = component["endpoint_a"], component["endpoint_b"], component["midpoint"]
        origin = (midpoint["longitude"], midpoint["latitude"])
        distance_metres = float(component.get("ray_range_km", 500)) * 1000
        if component["directionality"] == "bidirectional":
            ray_points = [destination(origin, component["reverse_azimuth_true_deg"], distance_metres),
                          destination(origin, component["forward_azimuth_true_deg"], distance_metres)]
        else:
            ray_points = [origin, destination(origin, component["selected_azimuth_true_deg"], distance_metres)]
        ray_coordinates = " ".join(f"{lon:.10f},{lat:.10f},0" for lon, lat in ray_points)
        orientation = (
            "<Folder><name>Measured component and unreviewed experimental projection</name>"
            "<Placemark><name>Measured straight component</name><LineString><tessellate>1</tessellate>"
            f"<coordinates>{a['longitude']:.10f},{a['latitude']:.10f},0 "
            f"{b['longitude']:.10f},{b['latitude']:.10f},0</coordinates></LineString></Placemark>"
            f"<Placemark><name>UNREVIEWED EXPERIMENTAL {escape(component['directionality'])} projection "
            f"{component['selected_azimuth_true_deg']:.3f} degrees true</name>"
            "<description>This local registration has not passed the atlas evidence-review gate. Extending the measured component is an exploratory hypothesis with no demonstrated predictive validity.</description><ExtendedData>"
            '<Data name="qualification_status"><value>unreviewed_local_registration</value></Data>'
            '<Data name="predictive_validity"><value>none_demonstrated</value></Data>'
            f"<Data name=\"azimuth_uncertainty_deg\"><value>{float(component.get('azimuth_uncertainty_deg', 0)):.6f}</value></Data>"
            f"<Data name=\"origin_uncertainty_m\"><value>{float(component.get('ray_origin', {}).get('uncertainty_m', 0)):.6f}</value></Data>"
            f"<Data name=\"corridor_km\"><value>{float(component.get('corridor_km', 0)):.3f}</value></Data>"
            "</ExtendedData><Style><LineStyle><color>ff55adf6</color><width>3</width></LineStyle></Style>"
            f"<LineString><tessellate>1</tessellate><coordinates>{ray_coordinates}</coordinates></LineString>"
            "</Placemark></Folder>"
        )
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>{escape(asset_id)} georeference</name>'
            '<description>Local image-registration output. Image publication depends on the embedded rights record. Any projection is unreviewed and has no demonstrated predictive validity.</description>'
            f"{overlay}{orientation}</Document></kml>\n")


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return stem or "crop-circle-overlay"


def deterministic_zip(path: Path, members: Iterable[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in members:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, payload)


def rights_qualification(rights: dict) -> tuple[bool, list[str]]:
    status = rights.get("status", "local_analysis_only")
    if status not in PUBLIC_RIGHTS:
        return False, ["rights_status_not_publication_authorized"]
    reasons = []
    if not str(rights.get("proof", "")).strip():
        reasons.append("missing_license_or_permission_proof")
    if status in LICENSE_RIGHTS and not str(rights.get("license", "")).strip():
        reasons.append("missing_license_identifier")
    if status in HOLDER_REQUIRED_RIGHTS and not str(rights.get("holder", "")).strip():
        reasons.append("missing_rights_holder")
    return not reasons, reasons


def validate_rights(metadata: dict, public_export: bool) -> tuple[str, bool]:
    rights = metadata.get("asset", {}).get("rights", {})
    status = rights.get("status", "local_analysis_only")
    publishable, reasons = rights_qualification(rights)
    if public_export and not publishable:
        raise RegistrationError(f"Public export refused: {', '.join(reasons)} (status '{status}')")
    return status, publishable


def export_registration(registration_path: Path, image_path: Path, output_dir: Path,
                        max_dimension: int = 2048, public_export: bool = False,
                        overwrite: bool = False) -> dict:
    metadata = json.loads(registration_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise RegistrationError(f"Unsupported schema_version; expected {SCHEMA_VERSION}")
    rights_status, publishable = validate_rights(metadata, public_export)
    if not image_path.is_file():
        raise RegistrationError(f"Source image does not exist: {image_path}")
    source_hash = file_sha256(image_path)
    recorded_hash = metadata.get("source_image", {}).get("sha256")
    if recorded_hash and source_hash.lower() != recorded_hash.lower():
        raise RegistrationError("Source image SHA-256 does not match registration metadata")

    with Image.open(image_path) as opened:
        opened.load()
        image = opened.copy()
    recorded_width = metadata.get("source_image", {}).get("width_px")
    recorded_height = metadata.get("source_image", {}).get("height_px")
    if recorded_width and int(recorded_width) != image.width or recorded_height and int(recorded_height) != image.height:
        raise RegistrationError("Source image dimensions do not match registration metadata")

    transform = solve_registration(metadata, image.size)
    plan = plan_raster(transform["image_pixel_to_web_mercator"], image.width, image.height, max_dimension)
    component = resolve_straight_component(metadata, transform["image_pixel_to_web_mercator"])
    resolved = copy.deepcopy(metadata)
    resolved["transform"] = {key: value for key, value in transform.items() if key != "footprint"}
    resolved["output"] = {key: value for key, value in plan.items() if key != "footprint"}
    resolved["straight_component"] = component
    resolved.setdefault("source_image", {}).update({
        "sha256": source_hash, "width_px": image.width, "height_px": image.height,
        "local_path": None, "pixels_embedded": False,
    })
    resolved["export"] = {
        "tool": "scripts/georeference_image.py",
        "tool_version": TOOL_VERSION,
        "mode": "public" if public_export else "local_analysis",
        "rights_status": rights_status,
        "public_derivative_export_allowed": publishable,
        "deterministic": True,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    asset_id = metadata.get("asset", {}).get("asset_id") or metadata.get("formation_id") or image_path.stem
    stem = safe_stem(asset_id)
    paths = {
        "png": output_dir / f"{stem}_north_up.png",
        "world_file": output_dir / f"{stem}_north_up.pgw",
        "projection": output_dir / f"{stem}_north_up.prj",
        "kml": output_dir / f"{stem}.kml",
        "kmz": output_dir / f"{stem}.kmz",
        "registration": output_dir / f"{stem}.registration.json",
        "manifest": output_dir / f"{stem}.manifest.json",
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise RegistrationError("Refusing to overwrite existing outputs: " + ", ".join(path.name for path in existing))

    warped = warp_image(image, transform["web_mercator_to_image_pixel"], plan)
    warped.save(paths["png"], format="PNG", optimize=False, compress_level=9)
    pixel = plan["pixel_size_m"]
    bounds = plan["bounds_web_mercator"]
    world_file = (
        f"{pixel['x']:.12f}\n0.000000000000\n0.000000000000\n{-pixel['y']:.12f}\n"
        f"{bounds['minX'] + pixel['x'] / 2:.12f}\n{bounds['maxY'] - pixel['y'] / 2:.12f}\n"
    )
    paths["world_file"].write_text(world_file, encoding="ascii", newline="\n")
    paths["projection"].write_text(WKT_EPSG_3857 + "\n", encoding="ascii", newline="\n")
    standalone_kml = build_kml(resolved, plan, paths["png"].name, component)
    paths["kml"].write_text(standalone_kml, encoding="utf-8", newline="\n")
    registration_bytes = canonical_json(resolved)
    paths["registration"].write_bytes(registration_bytes)
    kmz_kml = build_kml(resolved, plan, f"images/{paths['png'].name}", component).encode("utf-8")
    deterministic_zip(paths["kmz"], [
        ("doc.kml", kmz_kml),
        (f"images/{paths['png'].name}", paths["png"].read_bytes()),
        (f"metadata/{paths['registration'].name}", registration_bytes),
    ])
    manifest = {
        "schema_version": "crop-circle-atlas/georeference-export-manifest/v1",
        "asset_id": asset_id,
        "source_image": {"sha256": source_hash, "bytes": image_path.stat().st_size},
        "rights": {"status": rights_status, "public_export": public_export, "publishable": publishable},
        "outputs": {
            key: {"filename": path.name, "bytes": path.stat().st_size, "sha256": file_sha256(path)}
            for key, path in paths.items() if key != "manifest"
        },
        "tool_version": TOOL_VERSION,
    }
    paths["manifest"].write_bytes(canonical_json(manifest))
    return {"paths": {key: str(path) for key, path in paths.items()}, "manifest": manifest}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", required=True, type=Path, help="v1 registration JSON exported by georef.html")
    parser.add_argument("--image", required=True, type=Path, help="original local source image")
    parser.add_argument("--output-dir", required=True, type=Path, help="directory for PNG, PGW, PRJ, KML, KMZ, and metadata")
    parser.add_argument("--max-dimension", type=int, default=2048, help="longest output raster edge, 64-8192 (default: 2048)")
    parser.add_argument("--public-export", action="store_true", help="fail closed unless the rights record permits publication")
    parser.add_argument("--overwrite", action="store_true", help="overwrite only this tool's named output files if they already exist")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = export_registration(
            args.registration.resolve(), args.image.resolve(), args.output_dir.resolve(),
            max_dimension=args.max_dimension, public_export=args.public_export,
            overwrite=args.overwrite,
        )
    except (OSError, json.JSONDecodeError, RegistrationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result["manifest"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
