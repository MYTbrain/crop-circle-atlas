from __future__ import annotations

import csv
import calendar
import hashlib
import json
import math
import re
import unicodedata
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from .orientation_validation import validate_orientation
except ImportError:
    from orientation_validation import validate_orientation


ROOT = Path(__file__).resolve().parents[1]
NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"
ET.register_namespace("", NS)
ET.register_namespace("gx", GX_NS)

AUTHORIZED_IMAGE_RIGHTS = {
    "public_domain",
    "cc0",
    "cc_by",
    "cc_by_sa",
    "licensed",
    "permission_granted",
    "owner_supplied_publication_authorized",
}
LICENSE_IMAGE_RIGHTS = {"cc0", "cc_by", "cc_by_sa", "licensed"}
HOLDER_REQUIRED_IMAGE_RIGHTS = {
    "cc_by", "cc_by_sa", "licensed", "permission_granted",
    "owner_supplied_publication_authorized",
}
MAX_PUBLIC_OVERLAY_RMSE_M = 25.0


def q(tag):
    return f"{{{NS}}}{tag}"


def gx(tag):
    return f"{{{GX_NS}}}{tag}"


def text(parent, tag, value):
    node = ET.SubElement(parent, q(tag))
    node.text = str(value)
    return node


def destination(lat, lon, bearing, distance_km):
    radius = 6371.0088
    phi1, lam1, theta = map(math.radians, (lat, lon, bearing))
    delta = distance_km / radius
    phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta))
    lam2 = lam1 + math.atan2(math.sin(theta) * math.sin(delta) * math.cos(phi1),
                            math.cos(delta) - math.sin(phi1) * math.sin(phi2))
    return math.degrees(phi2), ((math.degrees(lam2) + 540) % 360) - 180


def haversine_bearing(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    distance = 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))
    bearing = math.atan2(math.sin(dlon) * math.cos(lat2),
                         math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    return distance, (math.degrees(bearing) + 360) % 360


def cross_along_track(origin, target, ray_bearing):
    """Signed cross-track and along-track distances on a spherical Earth."""
    distance, target_bearing = haversine_bearing(origin, target)
    delta = distance / 6371.0088
    angle = math.radians(angular_difference_signed(target_bearing, ray_bearing))
    cross = math.asin(max(-1.0, min(1.0, math.sin(delta) * math.sin(angle)))) * 6371.0088
    along = math.atan2(math.sin(delta) * math.cos(angle), math.cos(delta)) * 6371.0088
    return cross, along, target_bearing


def bearing_lateral_uncertainty(distance_km, uncertainty_deg):
    """Maximum spherical cross-track displacement from a bearing error."""
    delta = float(distance_km) / 6371.0088
    theta = math.radians(float(uncertainty_deg))
    return abs(math.asin(max(-1.0, min(1.0, math.sin(delta) * math.sin(theta)))) * 6371.0088)


def angular_difference(a, b):
    return abs((a - b + 180) % 360 - 180)


def angular_difference_signed(a, b):
    return (a - b + 180) % 360 - 180


def as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalized_place(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char)).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def likely_same_event_alias(source, target):
    if source.get("date_iso") != target.get("date_iso") or source.get("country_code") != target.get("country_code"):
        return False
    left, right = normalized_place(source.get("place")), normalized_place(target.get("place"))
    return bool(left and right and (left == right or left.startswith(f"{right} ") or right.startswith(f"{left} ")))


def date_interval(date_iso):
    try:
        parts = [int(value) for value in str(date_iso).split("-")]
        year = parts[0]
        if len(parts) == 1:
            return date(year, 1, 1), date(year, 12, 31)
        month = parts[1]
        if len(parts) == 2:
            return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        day = parts[2]
        exact = date(year, month, day)
        return exact, exact
    except (TypeError, ValueError):
        return None


def temporal_relation(source_date_iso, target_date_iso):
    source_interval = date_interval(source_date_iso)
    target_interval = date_interval(target_date_iso)
    if not source_interval or not target_interval:
        return "overlap_or_indeterminate"
    if target_interval[0] > source_interval[1]:
        return "later"
    if target_interval[1] < source_interval[0]:
        return "earlier"
    return "overlap_or_indeterminate"


def orientation_qualification(observation, formation):
    return validate_orientation(observation, formation)


def orientation_evidence_qualification(observation, root=None):
    root = (root or ROOT).resolve()
    expected_hash = str(observation.get("evidence_sha256", "")).strip().lower()
    relative = str(observation.get("evidence_cache_path", "")).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        return False, "missing_or_invalid_evidence_sha256"
    if not relative:
        return False, "missing_evidence_cache_path"
    evidence_path = (root / relative).resolve()
    if not evidence_path.is_relative_to(root):
        return False, "evidence_path_outside_repository"
    if not evidence_path.is_file():
        return False, "evidence_cache_file_missing"
    if sha256_file(evidence_path) != expected_hash:
        return False, "evidence_sha256_mismatch"
    return True, ""


def load_csv(name):
    path = ROOT / "data" / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(name, default=None):
    path = ROOT / name
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


ACTUAL_SITE_STATUSES = {
    "corroborated_field", "registered_site", "exact_source_gps",
    "verified_historical_imagery", "georeferenced_aerial_photo",
}


def location_status(row):
    status = (row.get("location_status") or row.get("site_status") or
              row.get("location_role") or "").strip()
    if status:
        return status
    if row.get("geocode_method") == "geonames_locality_centroid":
        return "locality_reference"
    if row.get("latitude") and row.get("longitude"):
        return "exact_source_gps"
    return "unresolved"


def location_role(row):
    role = (row.get("location_role") or "").strip()
    status = location_status(row)
    if role == "formation_site":
        if status in {"candidate_field", "probable_field"}:
            return "candidate_field"
        return "registered_site" if status == "registered_site" else "corroborated_field"
    if role:
        return role
    if status in ACTUAL_SITE_STATUSES:
        return "registered_site" if status == "registered_site" else "corroborated_field"
    if status in {"candidate_field", "probable_field"}:
        return "candidate_field"
    if status in {"locality_reference", "locality_reference_only"}:
        return "locality_reference"
    return "unresolved"


def is_actual_site(row):
    return location_role(row) in {"corroborated_field", "registered_site"} or location_status(row) in ACTUAL_SITE_STATUSES


def is_alignment_eligible_site(row):
    return str(row.get("site_alignment_eligible", "")).strip().lower() in {"true", "1", "yes"}


def is_convex_geodetic_quad(corners):
    """Reject folded/degenerate linked-overlay footprints before publication."""
    direction = 0
    for index in range(4):
        a = corners[index]
        b = corners[(index + 1) % 4]
        c = corners[(index + 2) % 4]
        cross = ((b[1] - a[1]) * (c[0] - b[0]) -
                 (b[0] - a[0]) * (c[1] - b[1]))
        if abs(cross) <= 1e-12:
            return False
        sign = 1 if cross > 0 else -1
        if direction and sign != direction:
            return False
        direction = sign
    return True


def make_style(doc, style_id, color, scale):
    style = ET.SubElement(doc, q("Style"), id=style_id)
    icon = ET.SubElement(style, q("IconStyle"))
    text(icon, "color", color)
    text(icon, "scale", scale)
    label = ET.SubElement(style, q("LabelStyle"))
    text(label, "scale", "0")


def extended_data(parent, values):
    ext = ET.SubElement(parent, q("ExtendedData"))
    for name, value in values.items():
        node = ET.SubElement(ext, q("Data"), name=name)
        text(node, "value", value)


def parse_control_points(raw):
    """Return image-corner coordinates in NW, NE, SE, SW order when available."""
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    points = payload.get("corners", payload) if isinstance(payload, dict) else payload
    if isinstance(points, dict):
        lookup = {str(k).lower(): v for k, v in points.items()}
        ordered = [lookup.get(key) for key in ("nw", "ne", "se", "sw")]
    elif isinstance(points, list) and len(points) == 4:
        ordered = points
    else:
        return None
    result = []
    for item in ordered:
        if not isinstance(item, dict):
            return None
        lat = as_float(item.get("latitude", item.get("lat")))
        lon = as_float(item.get("longitude", item.get("lng", item.get("lon"))))
        if lat is None or lon is None:
            ground = item.get("ground")
            if isinstance(ground, dict):
                lat = as_float(ground.get("latitude", ground.get("lat")))
                lon = as_float(ground.get("longitude", ground.get("lng", ground.get("lon"))))
        if lat is None or lon is None:
            return None
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            return None
        result.append((lat, lon))
    return result


def image_rights_qualification(asset):
    rights = asset.get("rights_status", "").strip().lower()
    if rights not in AUTHORIZED_IMAGE_RIGHTS:
        return False, ["rights_not_publication_authorized"]
    reasons = []
    if str(asset.get("public_derivative_export_allowed", "")).strip().lower() not in {"true", "1", "yes"}:
        reasons.append("public_derivative_export_not_allowed")
    if not asset.get("rights_proof", "").strip():
        reasons.append("missing_license_or_permission_proof")
    if rights in LICENSE_IMAGE_RIGHTS and not asset.get("license", "").strip():
        reasons.append("missing_license_identifier")
    if rights in HOLDER_REQUIRED_IMAGE_RIGHTS and not asset.get("rights_holder", "").strip():
        reasons.append("missing_rights_holder")
    if not asset.get("reviewer", "").strip():
        reasons.append("missing_reviewer")
    if not asset.get("reviewed_at", "").strip():
        reasons.append("missing_review_date")
    return not reasons, reasons


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_deterministic_member(archive, archive_name, payload):
    info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, payload)


def safe_overlay_stem(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value or "").strip("-.")
    return cleaned or "registered-overlay"


def image_registration_qualification(asset):
    try:
        notes = json.loads(asset.get("notes", ""))
    except (json.JSONDecodeError, TypeError):
        return False, "missing_verified_registration_metadata"
    if not isinstance(notes, dict):
        return False, "missing_verified_registration_metadata"
    if notes.get("distance_measurement") != "spherical_geodesic_ground_metres":
        return False, "unverified_transform_distance_units"
    if not str(notes.get("registration_id", "")).strip():
        return False, "missing_registration_id"
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(notes.get("source_image_sha256", ""))):
        return False, "missing_or_invalid_source_image_sha256"
    try:
        corners_payload = json.loads(asset.get("control_points_json", ""))
    except (json.JSONDecodeError, TypeError):
        return False, "missing_four_registered_corners"
    if not isinstance(corners_payload, dict) or corners_payload.get("source") != "north_up_epsg3857_output_bounds":
        return False, "unverified_registered_output_bounds"
    corners = parse_control_points(asset.get("control_points_json", ""))
    if not corners:
        return False, "unverified_registered_output_bounds"
    nw, ne, se, sw = corners
    if not (nw[0] == ne[0] > sw[0] == se[0] and nw[1] == sw[1] < ne[1] == se[1]):
        return False, "unverified_registered_output_bounds"
    return True, ""


def add_rights_cleared_overlays(doc, image_assets, formation_ids=None):
    folder = ET.SubElement(doc, q("Folder"))
    text(folder, "name", "Rights-cleared registered image overlays")
    included = []
    rejected = []
    for asset in image_assets:
        asset_id = asset.get("asset_id", "")
        formation_id = asset.get("formation_id", "").strip()
        if formation_ids is not None and formation_id not in formation_ids:
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": "formation_not_found"})
            continue
        rights = asset.get("rights_status", "").strip().lower()
        rights_ok, rights_reasons = image_rights_qualification(asset)
        if not rights_ok:
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": ";".join(rights_reasons)})
            continue
        registration_ok, registration_reason = image_registration_qualification(asset)
        if not registration_ok:
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": registration_reason})
            continue
        local = asset.get("local_path", "").strip()
        source_path = (ROOT / local).resolve() if local else None
        if source_path and not source_path.is_relative_to(ROOT.resolve()):
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": "local_image_outside_repository"})
            continue
        if not source_path or not source_path.is_file():
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": "missing_local_image"})
            continue
        expected_hash = asset.get("sha256", "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": "missing_or_invalid_image_sha256"})
            continue
        if sha256_file(source_path) != expected_hash:
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": "image_sha256_mismatch"})
            continue
        rmse = as_float(asset.get("transform_rmse_m"))
        if rmse is None or not math.isfinite(rmse) or rmse < 0:
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": "missing_or_invalid_transform_rmse_m"})
            continue
        if rmse > MAX_PUBLIC_OVERLAY_RMSE_M:
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": "transform_rmse_exceeds_public_limit"})
            continue
        corners = parse_control_points(asset.get("control_points_json", ""))
        if not corners:
            rejected.append({"asset_id": asset_id, "status": "excluded", "reason": "missing_four_registered_corners"})
            continue
        overlay = ET.SubElement(folder, q("GroundOverlay"))
        text(overlay, "name", asset_id or source_path.name)
        overlay_description = (
            f'Formation: {asset.get("formation_id", "")} | rights status: {rights} | '
            f'rights holder/creator: {asset.get("rights_holder", "")} | '
            f'license: {asset.get("license", "")} | rights proof: {asset.get("rights_proof", "")} | '
            f'source: {asset.get("source_url", "")} | '
            f'ground-distance RMSE: {asset.get("transform_rmse_m", "?")} m'
        )
        text(overlay, "description", overlay_description)
        extended_data(overlay, {
            "formation_id": asset.get("formation_id", ""),
            "rights_status": rights,
            "rights_holder": asset.get("rights_holder", ""),
            "license": asset.get("license", ""),
            "rights_proof": asset.get("rights_proof", ""),
            "source_url": asset.get("source_url", ""),
            "transform_rmse_m_ground_distance": asset.get("transform_rmse_m", ""),
        })
        icon = ET.SubElement(overlay, q("Icon"))
        archive_name = f"assets/{safe_overlay_stem(asset_id or source_path.stem)}{source_path.suffix.lower()}"
        text(icon, "href", archive_name)
        quad = ET.SubElement(overlay, gx("LatLonQuad"))
        # gx:LatLonQuad requires counter-clockwise order starting at the lower-left.
        sw, se, ne, nw = corners[3], corners[2], corners[1], corners[0]
        text(quad, "coordinates", " ".join(f"{lon},{lat}" for lat, lon in (sw, se, ne, nw)))
        included.append((source_path, archive_name, asset_id))
    return included, rejected


def add_source_linked_provisional_overlays(doc, payload, formation_ids=None):
    """Add opt-in remote overlays without copying source-image pixels into the KMZ."""
    folder = ET.SubElement(doc, q("Folder"))
    text(folder, "name", "Linked provisional source-photo placements (pixels not packaged)")
    text(folder, "visibility", "0")
    text(folder, "description", (
        "Remote source photographs load only when this folder is enabled. The KMZ does not contain "
        "the source pixels. Placements in this folder are provisional and excluded from formal "
        "alignment-hit calculations until independent checkpoints are accepted."
    ))
    count = 0
    rejected = []
    included_ids = set()
    for item in payload.get("overlays", []):
        overlay_id = item.get("overlay_id", "")
        formation_id = item.get("formation_id", "")
        if formation_ids is not None and formation_id not in formation_ids:
            rejected.append({"asset_id": overlay_id, "status": "excluded", "reason": "formation_not_found"})
            continue
        source_url = str(item.get("source_image_url", "")).strip()
        corners = item.get("corners")
        if not source_url.startswith("https://") or not isinstance(corners, list) or len(corners) != 4:
            rejected.append({"asset_id": overlay_id, "status": "excluded", "reason": "invalid_remote_overlay_metadata"})
            continue
        normalized = []
        for corner in corners:
            if not isinstance(corner, list) or len(corner) != 2:
                normalized = []
                break
            lat, lon = as_float(corner[0]), as_float(corner[1])
            if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                normalized = []
                break
            normalized.append((lat, lon))
        if len(normalized) != 4 or not is_convex_geodetic_quad(normalized):
            rejected.append({"asset_id": overlay_id, "status": "excluded", "reason": "invalid_remote_overlay_corners"})
            continue
        overlay = ET.SubElement(folder, q("GroundOverlay"))
        text(overlay, "name", item.get("title") or overlay_id)
        text(overlay, "visibility", "1")
        opacity = min(1.0, max(0.0, as_float(item.get("default_opacity"), 0.68)))
        text(overlay, "color", f"{round(opacity * 255):02x}ffffff")
        uncertainty_value = item.get("coordinate_uncertainty_m")
        uncertainty_status = item.get("coordinate_uncertainty_status", "")
        sensitivity_value = item.get("display_corner_sensitivity_envelope_m")
        sensitivity_kind = item.get("display_corner_sensitivity_kind", "")
        uncertainty_text = f"{uncertainty_value} m" if uncertainty_value is not None else (
            uncertainty_status.replace("_", " ") or "not independently quantified"
        )
        if sensitivity_value is not None:
            uncertainty_text += (
                f"; display-corner sensitivity envelope: {sensitivity_value} m "
                "(conditional detector sensitivity, not a confidence interval)"
            )
        text(overlay, "description", (
            f'Registration status: {item.get("registration_status", "provisional")} | '
            f'rights: {item.get("rights_status", "unknown")} | source page: '
            f'{item.get("source_page_url", "")} | coordinate uncertainty: '
            f'{uncertainty_text} | {item.get("notes", "")}'
        ))
        extended_data(overlay, {
            "overlay_id": overlay_id,
            "formation_id": formation_id,
            "registration_status": item.get("registration_status", ""),
            "rights_status": item.get("rights_status", ""),
            "pixel_distribution": "remote_source_link_only_not_packaged",
            "source_page_url": item.get("source_page_url", ""),
            "source_image_sha256": item.get("source_image_sha256", ""),
            "coordinate_uncertainty_m": item.get("coordinate_uncertainty_m", ""),
            "coordinate_uncertainty_status": uncertainty_status,
            "display_corner_sensitivity_envelope_m": sensitivity_value if sensitivity_value is not None else "",
            "display_corner_sensitivity_kind": sensitivity_kind,
            "display_geometry_status": item.get("display_geometry_status", ""),
            "registration_observation_id": item.get("registration_observation_id", ""),
        })
        icon = ET.SubElement(overlay, q("Icon"))
        text(icon, "href", source_url)
        quad = ET.SubElement(overlay, gx("LatLonQuad"))
        top_left, top_right, bottom_right, bottom_left = normalized
        text(quad, "coordinates", " ".join(
            f"{lon},{lat}" for lat, lon in (bottom_left, bottom_right, top_right, top_left)
        ))
        count += 1
        included_ids.add(overlay_id)
    return count, rejected, included_ids


def main():
    formations = load_csv("formations.csv")
    by_id = {row["formation_id"]: row for row in formations}
    observations = load_csv("orientation_observations.csv")
    provisional_observations = load_csv("provisional_orientation_observations.csv")
    image_assets = load_csv("image_assets.csv")
    linked_overlay_payload = load_json("web/data/registered_overlays.json", {"overlays": []})
    root = ET.Element(q("kml"))
    doc = ET.SubElement(root, q("Document"))
    text(doc, "name", "Crop Circle Atlas")
    text(doc, "description", "Formation sites, candidate fields, and rough locality references are separated. Locality references are hidden by default and are not crop-circle locations, ray origins, or alignment targets. Projection lines remain exploratory and have no demonstrated predictive validity. Locality references use GeoNames under CC BY 4.0: https://www.geonames.org/")
    make_style(doc, "site", "ffc5d14f", "0.9")
    make_style(doc, "candidate", "ff55adf6", "0.8")
    make_style(doc, "locality", "ff999999", "0.48")
    line_style = ET.SubElement(doc, q("Style"), id="ray")
    ls = ET.SubElement(line_style, q("LineStyle"))
    text(ls, "color", "ff4fd1c5")
    text(ls, "width", "2")

    provisional_style = ET.SubElement(doc, q("Style"), id="provisional-ray")
    provisional_ls = ET.SubElement(provisional_style, q("LineStyle"))
    text(provisional_ls, "color", "ff55adf6")
    text(provisional_ls, "width", "2")

    folders = {
        "actual": ET.SubElement(doc, q("Folder")),
        "candidate": ET.SubElement(doc, q("Folder")),
        "locality": ET.SubElement(doc, q("Folder")),
    }
    text(folders["actual"], "name", "Corroborated and registered formation sites")
    text(folders["candidate"], "name", "Candidate fields (not exact formation sites)")
    text(folders["locality"], "name", "Reference localities (not formation sites)")
    text(folders["locality"], "visibility", "0")
    point_count = 0
    point_role_counts = {"actual": 0, "candidate": 0, "locality": 0}
    for row in formations:
        if not row.get("latitude") or not row.get("longitude"):
            continue
        role = location_role(row)
        if role in {"registered_site", "corroborated_field"}:
            key, style = "actual", "#site"
        elif role == "candidate_field":
            key, style = "candidate", "#candidate"
        elif role == "locality_reference":
            key, style = "locality", "#locality"
        else:
            continue
        pm = ET.SubElement(folders[key], q("Placemark"))
        text(pm, "name", f'{row.get("date_iso", "")} - {row.get("place", "")}')
        text(pm, "styleUrl", style)
        if key == "locality":
            text(pm, "visibility", "0")
        method = (row.get("site_coordinate_method") if key != "locality" else
                  row.get("locality_coordinate_method")) or row.get("geocode_method", "unknown")
        desc = (f'<b>{row.get("place", "")}</b><br>{row.get("region", "")}, {row.get("country", "")}<br>'
                f'Date: {row.get("date_iso", "")} ({row.get("date_precision", "")})<br>'
                f'<b>Location role: {role}</b><br>'
                f'Coordinate method: {method}; uncertainty {row.get("coordinate_uncertainty_km", "?")} km<br>'
                f'{row.get("site_notes", "")}<br>'
                f'Sources: {row.get("source_names", "")}<br>{row.get("source_urls", "")}')
        text(pm, "description", desc)
        extended_data(pm, {
            "formation_id": row.get("formation_id", ""),
            "location_status": location_status(row),
            "location_role": role,
            "coordinate_method": method,
            "coordinate_uncertainty_km": row.get("coordinate_uncertainty_km", ""),
            "straight_component_status": row.get("straight_component_status", row.get("has_straight_component", "unknown")),
            "orientation_status": row.get("orientation_status", "not_reviewed"),
        })
        point = ET.SubElement(pm, q("Point"))
        text(point, "coordinates", f'{row["longitude"]},{row["latitude"]},0')
        point_count += 1
        point_role_counts[key] += 1

    ray_folder = ET.SubElement(doc, q("Folder"))
    text(ray_folder, "name", "Experimental projections from documented orientations")
    hits = []
    ray_audit = []
    ray_features = []
    ray_count = 0
    for obs in observations:
        source = by_id.get(obs.get("formation_id", ""))
        if not source:
            ray_audit.append({"observation_id": obs.get("observation_id", ""), "formation_id": obs.get("formation_id", ""), "assertion_id": obs.get("assertion_id", ""), "status": "rejected", "reasons": "formation_not_found"})
            continue
        qualification = orientation_qualification(obs, source)
        if not qualification["qualified"]:
            ray_audit.append({"observation_id": obs.get("observation_id", ""), "formation_id": source["formation_id"], "assertion_id": obs.get("assertion_id", ""), "status": "rejected", "reasons": ";".join(qualification["reasons"])})
            continue
        evidence_ok, evidence_reason = orientation_evidence_qualification(obs)
        if not evidence_ok:
            ray_audit.append({"observation_id": obs.get("observation_id", ""), "formation_id": source["formation_id"], "assertion_id": obs.get("assertion_id", ""), "status": "rejected", "reasons": evidence_reason})
            continue
        lat, lon = qualification["origin_latitude"], qualification["origin_longitude"]
        if not is_actual_site(source) or not source.get("site_latitude") or not source.get("site_longitude"):
            ray_audit.append({"observation_id": obs.get("observation_id", ""), "formation_id": source["formation_id"], "assertion_id": obs.get("assertion_id", ""), "status": "rejected", "reasons": "ray_origin_has_no_field_site_record"})
            continue
        site_uncertainty_m = as_float(source.get("site_coordinate_uncertainty_m"), float("inf"))
        if not math.isfinite(site_uncertainty_m) or site_uncertainty_m <= 0:
            ray_audit.append({"observation_id": obs.get("observation_id", ""), "formation_id": source["formation_id"], "assertion_id": obs.get("assertion_id", ""), "status": "rejected", "reasons": "ray_origin_site_uncertainty_missing"})
            continue
        effective_origin_uncertainty_m = max(qualification["origin_uncertainty_m"], site_uncertainty_m)
        origin_to_site_km, _ = haversine_bearing(
            (lat, lon), (float(source["site_latitude"]), float(source["site_longitude"]))
        )
        if origin_to_site_km > effective_origin_uncertainty_m / 1000:
            ray_audit.append({"observation_id": obs.get("observation_id", ""), "formation_id": source["formation_id"], "assertion_id": obs.get("assertion_id", ""), "status": "rejected", "reasons": "ray_origin_outside_site_uncertainty"})
            continue
        bearing = qualification["azimuth"] % 360
        length = qualification["max_range_km"]
        corridor = qualification["corridor_km"]
        directionality = qualification["directionality"]
        ends = [destination(lat, lon, bearing, length)]
        if directionality == "bidirectional":
            ends.insert(0, destination(lat, lon, (bearing + 180) % 360, length))
        else:
            ends.insert(0, (lat, lon))
        pm = ET.SubElement(ray_folder, q("Placemark"))
        text(pm, "name", f'Experimental projection - {source["formation_id"]} - {bearing:.1f} degrees true')
        text(pm, "styleUrl", "#ray")
        text(pm, "description", f'Experimental projection from an evidence-reviewed local orientation; the long-distance extension has no demonstrated predictive validity. Method: {obs.get("orientation_method", "")} | uncertainty: {obs.get("azimuth_uncertainty_deg", "?")} degrees | evidence: {obs.get("evidence_url", "")} | caveat: {obs.get("notes", "")}')
        extended_data(pm, {
            "formation_id": source["formation_id"],
            "projection_status": "experimental_extension_of_documented_local_orientation",
            "predictive_validity": "none_demonstrated",
            "azimuth_true_deg": bearing,
            "azimuth_uncertainty_deg": qualification["uncertainty"],
            "origin_method": qualification["origin_method"],
            "origin_uncertainty_m": effective_origin_uncertainty_m,
            "reviewer": obs.get("reviewer", ""),
            "reviewed_at": obs.get("reviewed_at", ""),
        })
        line = ET.SubElement(pm, q("LineString"))
        text(line, "tessellate", "1")
        text(line, "coordinates", " ".join(f"{p[1]},{p[0]},0" for p in ends))
        ray_features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in ends]},
            "properties": {
                "observation_id": obs.get("observation_id", ""),
                "formation_id": source["formation_id"],
                "assertion_id": obs.get("assertion_id", ""),
                "place": source.get("place", ""),
                "date_iso": source.get("date_iso", ""),
                "azimuth_true_deg": bearing,
                "azimuth_uncertainty_deg": qualification["uncertainty"],
                "directionality": directionality,
                "max_range_km": length,
                "corridor_km": corridor,
                "orientation_method": obs.get("orientation_method", ""),
                "evidence_url": obs.get("evidence_url", ""),
                "evidence_sha256": obs.get("evidence_sha256", ""),
                "origin_method": qualification["origin_method"],
                "origin_uncertainty_m": effective_origin_uncertainty_m,
                "reviewer": obs.get("reviewer", ""),
                "reviewed_at": obs.get("reviewed_at", ""),
                "projection_status": "experimental_extension_of_documented_local_orientation",
                "predictive_validity": "none_demonstrated",
                "notes": obs.get("notes", ""),
            },
        })
        ray_count += 1
        ray_audit.append({"observation_id": obs.get("observation_id", ""), "formation_id": source["formation_id"], "assertion_id": obs.get("assertion_id", ""), "status": "qualified", "reasons": ""})
        for target in formations:
            if (target["formation_id"] == source["formation_id"] or not target.get("latitude") or
                    not is_alignment_eligible_site(target) or
                    (source.get("site_cluster_id") and source.get("site_cluster_id") == target.get("site_cluster_id")) or
                    likely_same_event_alias(source, target)):
                continue
            target_point = (float(target["latitude"]), float(target["longitude"]))
            source_target_distance, _ = haversine_bearing((lat, lon), target_point)
            if source_target_distance < 1:
                continue
            options = [cross_along_track((lat, lon), target_point, bearing)]
            if directionality == "bidirectional":
                options.append(cross_along_track((lat, lon), target_point, (bearing + 180) % 360))
            cross_track, along_track, _ = min(options, key=lambda value: abs(value[0]) if value[1] >= 0 else float("inf"))
            cross_track = abs(cross_track)
            if 0 <= along_track <= length and cross_track <= corridor:
                relation = temporal_relation(source.get("date_iso", ""), target.get("date_iso", ""))
                target_uncertainty = as_float(target.get("coordinate_uncertainty_km"), float("inf"))
                source_uncertainty = effective_origin_uncertainty_m / 1000
                bearing_uncertainty = bearing_lateral_uncertainty(along_track, qualification["uncertainty"])
                combined_uncertainty = target_uncertainty + source_uncertainty + bearing_uncertainty
                if combined_uncertainty <= corridor:
                    quality = "eligible_centerline_and_uncertainty"
                elif bearing_uncertainty > corridor:
                    quality = "exploratory_bearing_uncertainty_exceeds_corridor"
                else:
                    quality = "exploratory_coordinate_uncertainty_exceeds_corridor"
                hits.append({"source_formation_id":source["formation_id"], "target_formation_id":target["formation_id"],
                             "azimuth_true_deg":bearing, "along_track_km":round(along_track, 3),
                             "cross_track_km":round(cross_track, 3), "max_range_km":length,
                             "corridor_km":corridor, "temporal_relation":relation,
                             "source_origin_method": qualification["origin_method"],
                             "source_origin_uncertainty_m": effective_origin_uncertainty_m,
                             "target_coordinate_uncertainty_km": target.get("coordinate_uncertainty_km", ""),
                             "azimuth_uncertainty_deg": qualification["uncertainty"],
                             "orientation_lateral_uncertainty_km": round(bearing_uncertainty, 3),
                             "combined_spatial_uncertainty_km": round(combined_uncertainty, 3),
                             "hit_geometry": "centerline_corridor",
                             "spatial_quality_status": quality,
                             "eligible_for_statistical_test": "yes" if quality == "eligible_centerline_and_uncertainty" else "no"})

    provisional_folder = ET.SubElement(doc, q("Folder"))
    text(provisional_folder, "name", "Provisional user-demonstrated axes (excluded from alignment calculations)")
    provisional_features = []
    provisional_count = 0
    for obs in provisional_observations:
        source = by_id.get(obs.get("formation_id", ""))
        lat = as_float(obs.get("origin_latitude"))
        lon = as_float(obs.get("origin_longitude"))
        bearing = as_float(obs.get("azimuth_true_deg"))
        uncertainty = as_float(obs.get("azimuth_uncertainty_deg"))
        length = as_float(obs.get("max_range_km"), 500)
        directionality = obs.get("directionality", "bidirectional")
        if (not source or lat is None or lon is None or bearing is None or uncertainty is None or
                not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 0 <= bearing < 360 or
                length is None or length <= 0 or directionality not in {"forward", "bidirectional"}):
            continue
        if not is_actual_site(source) or not source.get("site_latitude") or not source.get("site_longitude"):
            continue
        site_uncertainty_m = as_float(source.get("site_coordinate_uncertainty_m"), float("inf"))
        observation_uncertainty_m = as_float(obs.get("origin_uncertainty_m"), float("inf"))
        if not all(math.isfinite(value) and value > 0 for value in (site_uncertainty_m, observation_uncertainty_m)):
            continue
        effective_origin_uncertainty_m = max(site_uncertainty_m, observation_uncertainty_m)
        origin_to_site_km, _ = haversine_bearing(
            (lat, lon), (float(source["site_latitude"]), float(source["site_longitude"]))
        )
        if origin_to_site_km > effective_origin_uncertainty_m / 1000:
            continue
        ends = [destination(lat, lon, bearing, length)]
        if directionality == "bidirectional":
            ends.insert(0, destination(lat, lon, (bearing + 180) % 360, length))
        else:
            ends.insert(0, (lat, lon))
        pm = ET.SubElement(provisional_folder, q("Placemark"))
        text(pm, "name", f'PROVISIONAL - {source.get("date_iso", "")} {source.get("place", "")} - {bearing:.1f} degrees true')
        text(pm, "styleUrl", "#provisional-ray")
        text(pm, "description", (
            "Provisional user-demonstrated registered axis. Independent ground-control checkpoints are "
            f"pending; excluded from formal alignment-hit calculations. {obs.get('notes', '')}"
        ))
        extended_data(pm, {
            "formation_id": source["formation_id"],
            "review_status": obs.get("review_status", "provisional"),
            "predictive_validity": "none_demonstrated",
            "excluded_from_alignment_calculations": "yes",
            "azimuth_true_deg": bearing,
            "azimuth_uncertainty_deg": uncertainty,
            "origin_uncertainty_m": effective_origin_uncertainty_m,
            "evidence_url": obs.get("evidence_url", ""),
            "evidence_kind": obs.get("evidence_kind", ""),
            "evidence_sha256_subject": obs.get("evidence_sha256_subject", ""),
            "evidence_sha256": obs.get("evidence_sha256", ""),
        })
        line = ET.SubElement(pm, q("LineString"))
        text(line, "tessellate", "1")
        text(line, "coordinates", " ".join(f"{point[1]},{point[0]},0" for point in ends))
        provisional_features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[point[1], point[0]] for point in ends]},
            "properties": {
                "observation_id": obs.get("observation_id", ""),
                "formation_id": source["formation_id"],
                "assertion_id": obs.get("assertion_id", ""),
                "place": source.get("place", ""),
                "date_iso": source.get("date_iso", ""),
                "azimuth_true_deg": bearing,
                "azimuth_uncertainty_deg": uncertainty,
                "directionality": directionality,
                "max_range_km": length,
                "corridor_km": as_float(obs.get("corridor_km"), 2),
                "orientation_method": obs.get("orientation_method", ""),
                "evidence_url": obs.get("evidence_url", ""),
                "evidence_kind": obs.get("evidence_kind", ""),
                "evidence_sha256_subject": obs.get("evidence_sha256_subject", ""),
                "evidence_sha256": obs.get("evidence_sha256", ""),
                "origin_method": obs.get("origin_coordinate_method", ""),
                "origin_uncertainty_m": effective_origin_uncertainty_m,
                "reviewer": obs.get("reviewer", ""),
                "reviewed_at": obs.get("reviewed_at", ""),
                "review_status": obs.get("review_status", "provisional"),
                "projection_status": "provisional_user_demonstrated_axis",
                "predictive_validity": "none_demonstrated",
                "excluded_from_alignment_calculations": "yes",
                "notes": obs.get("notes", ""),
            },
        })
        provisional_count += 1

    overlay_files, overlay_audit = add_rights_cleared_overlays(doc, image_assets, set(by_id))
    linked_overlay_count, linked_overlay_audit, linked_overlay_ids = add_source_linked_provisional_overlays(
        doc, linked_overlay_payload, set(by_id)
    )
    overlay_audit.extend(linked_overlay_audit)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    exports = ROOT / "exports"
    exports.mkdir(exist_ok=True)
    kml_path = exports / "crop_circle_atlas.kml"
    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    kmz_path = exports / "crop_circle_atlas.kmz"
    with zipfile.ZipFile(kmz_path, "w", zipfile.ZIP_DEFLATED) as archive:
        write_deterministic_member(archive, "doc.kml", kml_path.read_bytes())
        for source_path, archive_name, _ in overlay_files:
            write_deterministic_member(archive, archive_name, source_path.read_bytes())
    web_downloads = ROOT / "web" / "downloads"
    web_downloads.mkdir(parents=True, exist_ok=True)
    (web_downloads / kmz_path.name).write_bytes(kmz_path.read_bytes())
    ray_geojson = {
        "type": "FeatureCollection",
        "features": ray_features,
        "metadata": {
            "notice": "Each line starts from an evidence-reviewed local true-north orientation. Its long-distance extension is experimental, has no demonstrated predictive validity, and any alignment hit remains exploratory.",
        },
    }
    (ROOT / "web" / "data" / "orientation_rays.geojson").write_text(
        json.dumps(ray_geojson, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    provisional_geojson = {
        "type": "FeatureCollection",
        "features": provisional_features,
        "metadata": {
            "notice": "These axes were recovered from user-supplied georegistrations but lack independent checkpoints. They are displayed as provisional and are excluded from formal alignment-hit calculations.",
        },
    }
    (ROOT / "web" / "data" / "provisional_orientation_rays.geojson").write_text(
        json.dumps(provisional_geojson, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    hit_fields = ["source_formation_id","target_formation_id","azimuth_true_deg","along_track_km","cross_track_km","max_range_km","corridor_km","temporal_relation","source_origin_method","source_origin_uncertainty_m","target_coordinate_uncertainty_km","azimuth_uncertainty_deg","orientation_lateral_uncertainty_km","combined_spatial_uncertainty_km","hit_geometry","spatial_quality_status","eligible_for_statistical_test"]
    with (ROOT / "data" / "alignment_hits.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=hit_fields)
        writer.writeheader()
        writer.writerows(hits)
    audit_fields = ["observation_id", "formation_id", "assertion_id", "status", "reasons"]
    with (ROOT / "data" / "orientation_ray_audit.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_fields)
        writer.writeheader()
        writer.writerows(ray_audit)
    with (ROOT / "data" / "image_overlay_audit.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["asset_id", "status", "reason"])
        writer.writeheader()
        writer.writerows(overlay_audit)
        for _, _, asset_id in overlay_files:
            writer.writerow({"asset_id": asset_id, "status": "included", "reason": ""})
        for item in linked_overlay_payload.get("overlays", []):
            if item.get("overlay_id") in linked_overlay_ids:
                writer.writerow({"asset_id": item.get("overlay_id", ""), "status": "included_remote_link", "reason": "pixels_not_packaged_provisional"})
    print(
        f"points={point_count} point_roles={point_role_counts} rays={ray_count} "
        f"provisional_rays={provisional_count} hits={len(hits)} packaged_overlays={len(overlay_files)} "
        f"linked_overlays={linked_overlay_count} rejected_rays="
        f"{sum(1 for row in ray_audit if row['status'] == 'rejected')}"
    )


if __name__ == "__main__":
    main()
