from __future__ import annotations

import csv
import math
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", NS)


def q(tag):
    return f"{{{NS}}}{tag}"


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


def angular_difference(a, b):
    return abs((a - b + 180) % 360 - 180)


def load_csv(name):
    path = ROOT / "data" / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def make_style(doc, style_id, color, scale):
    style = ET.SubElement(doc, q("Style"), id=style_id)
    icon = ET.SubElement(style, q("IconStyle"))
    text(icon, "color", color)
    text(icon, "scale", scale)
    label = ET.SubElement(style, q("LabelStyle"))
    text(label, "scale", "0")


def main():
    formations = load_csv("formations.csv")
    by_id = {row["formation_id"]: row for row in formations}
    observations = load_csv("orientation_observations.csv")
    root = ET.Element(q("kml"))
    doc = ET.SubElement(root, q("Document"))
    text(doc, "name", "Crop Circle Atlas")
    text(doc, "description", "Reported formation localities. Automated coordinates are approximate locality centroids, not field locations.")
    make_style(doc, "us", "ff00a5ff", "0.8")
    make_style(doc, "global", "ffffa33b", "0.55")
    line_style = ET.SubElement(doc, q("Style"), id="ray")
    ls = ET.SubElement(line_style, q("LineStyle"))
    text(ls, "color", "ff4fd1c5")
    text(ls, "width", "2")

    folders = {}
    for key, label in (("US", "United States - priority"), ("GLOBAL", "Worldwide")):
        folders[key] = ET.SubElement(doc, q("Folder"))
        text(folders[key], "name", label)
    point_count = 0
    for row in formations:
        if not row.get("latitude") or not row.get("longitude"):
            continue
        key = "US" if row.get("country_code") == "US" else "GLOBAL"
        pm = ET.SubElement(folders[key], q("Placemark"))
        text(pm, "name", f'{row.get("date_iso", "")} - {row.get("place", "")}')
        text(pm, "styleUrl", "#us" if key == "US" else "#global")
        desc = (f'<b>{row.get("place", "")}</b><br>{row.get("region", "")}, {row.get("country", "")}<br>'
                f'Date: {row.get("date_iso", "")} ({row.get("date_precision", "")})<br>'
                f'Coordinate: GeoNames locality centroid; uncertainty {row.get("coordinate_uncertainty_km", "?")} km<br>'
                f'Sources: {row.get("source_names", "")}<br>{row.get("source_urls", "")}')
        text(pm, "description", desc)
        point = ET.SubElement(pm, q("Point"))
        text(point, "coordinates", f'{row["longitude"]},{row["latitude"]},0')
        point_count += 1

    ray_folder = ET.SubElement(doc, q("Folder"))
    text(ray_folder, "name", "Orientation-qualified projection rays")
    hits = []
    ray_count = 0
    for obs in observations:
        source = by_id.get(obs.get("formation_id", ""))
        if not source or not source.get("latitude") or not obs.get("azimuth_true_deg"):
            continue
        lat, lon = float(source["latitude"]), float(source["longitude"])
        bearing = float(obs["azimuth_true_deg"]) % 360
        length = float(obs.get("max_range_km") or 500)
        corridor = float(obs.get("corridor_km") or 2)
        directionality = obs.get("directionality", "forward")
        ends = [destination(lat, lon, bearing, length)]
        if directionality == "bidirectional":
            ends.insert(0, destination(lat, lon, (bearing + 180) % 360, length))
        else:
            ends.insert(0, (lat, lon))
        pm = ET.SubElement(ray_folder, q("Placemark"))
        text(pm, "name", f'{source["formation_id"]} - {bearing:.1f} degrees true')
        text(pm, "styleUrl", "#ray")
        text(pm, "description", f'Method: {obs.get("orientation_method", "")} | uncertainty: {obs.get("azimuth_uncertainty_deg", "?")} degrees | evidence: {obs.get("evidence_url", "")}')
        line = ET.SubElement(pm, q("LineString"))
        text(line, "tessellate", "1")
        text(line, "coordinates", " ".join(f"{p[1]},{p[0]},0" for p in ends))
        ray_count += 1
        for target in formations:
            if target["formation_id"] == source["formation_id"] or not target.get("latitude"):
                continue
            distance, target_bearing = haversine_bearing((lat, lon), (float(target["latitude"]), float(target["longitude"])))
            diffs = [angular_difference(target_bearing, bearing)]
            if directionality == "bidirectional":
                diffs.append(angular_difference(target_bearing, (bearing + 180) % 360))
            angle = min(diffs)
            cross_track = abs(distance * math.sin(math.radians(angle)))
            along_track = distance * math.cos(math.radians(angle))
            if 0 <= along_track <= length and cross_track <= corridor:
                relation = "later" if int(target["year"]) > int(source["year"]) else "earlier" if int(target["year"]) < int(source["year"]) else "same_year"
                hits.append({"source_formation_id":source["formation_id"], "target_formation_id":target["formation_id"],
                             "azimuth_true_deg":bearing, "along_track_km":round(along_track, 3),
                             "cross_track_km":round(cross_track, 3), "max_range_km":length,
                             "corridor_km":corridor, "temporal_relation":relation})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    exports = ROOT / "exports"
    exports.mkdir(exist_ok=True)
    kml_path = exports / "crop_circle_atlas.kml"
    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(exports / "crop_circle_atlas.kmz", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(kml_path, "doc.kml")
    hit_fields = ["source_formation_id","target_formation_id","azimuth_true_deg","along_track_km","cross_track_km","max_range_km","corridor_km","temporal_relation"]
    with (ROOT / "data" / "alignment_hits.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=hit_fields)
        writer.writeheader()
        writer.writerows(hits)
    print(f"points={point_count} rays={ray_count} hits={len(hits)}")


if __name__ == "__main__":
    main()

