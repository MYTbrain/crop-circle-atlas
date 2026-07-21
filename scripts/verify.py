import csv
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def rows(name):
    with (ROOT / "data" / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


formations = rows("formations.csv")
assertions = rows("source_assertions.csv")
snapshots = rows("source_snapshots.csv")
source_catalog = rows("source_catalog.csv")
assert len(formations) >= 5000, len(formations)
assert len(assertions) >= len(formations)
assert len(snapshots) >= 180, len(snapshots)
assert len(source_catalog) >= 10, len(source_catalog)
ids = [row["formation_id"] for row in formations]
assert len(ids) == len(set(ids))
geocoded = [row for row in formations if row["latitude"]]
assert len(geocoded) >= 2000, len(geocoded)
for row in geocoded:
    assert -90 <= float(row["latitude"]) <= 90
    assert -180 <= float(row["longitude"]) <= 180
    assert row["geocode_method"] == "geonames_locality_centroid"
geojson = json.loads((ROOT / "web" / "data" / "formations.geojson").read_text(encoding="utf-8"))
assert len(geojson["features"]) == len(geocoded)
ET.parse(ROOT / "exports" / "crop_circle_atlas.kml")
with zipfile.ZipFile(ROOT / "exports" / "crop_circle_atlas.kmz") as archive:
    assert archive.testzip() is None
    assert "doc.kml" in archive.namelist()
for needed in ("index.html", "app.js", "styles.css"):
    assert (ROOT / "web" / needed).exists()
assert (ROOT / "docs" / "SOURCE_REGISTER.md").exists()
assert (ROOT / "outputs" / "initial-build" / "crop_circle_atlas.xlsx").exists()
print(f"PASS formations={len(formations)} assertions={len(assertions)} geocoded={len(geocoded)} snapshots={len(snapshots)}")
