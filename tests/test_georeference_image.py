import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("georeference_image", ROOT / "scripts" / "georeference_image.py")
GEOREF = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GEOREF)
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_registration.json"


def make_synthetic_grid(path: Path) -> None:
    image = Image.new("RGB", (320, 240), "#10231f")
    draw = ImageDraw.Draw(image)
    for x in range(0, 321, 20):
        draw.line((x, 0, x, 239), fill=(40 + x % 180, 180, 150), width=1)
    for y in range(0, 241, 20):
        draw.line((0, y, 319, y), fill=(220, 80 + y % 150, 70), width=1)
    draw.line((80, 120, 250, 120), fill="white", width=5)
    draw.ellipse((152, 112, 168, 128), outline="#f5ac58", width=3)
    image.save(path, format="PNG", compress_level=9)


class GeoreferenceImageTests(unittest.TestCase):
    def test_high_latitude_distances_are_physical_ground_metres(self):
        origin = GEOREF.lonlat_to_mercator(0, 75)
        projected_endpoint = (origin[0] + 1000, origin[1])
        ground = GEOREF.projected_ground_distance_metres(origin, projected_endpoint)
        expected = 1000 * GEOREF.math.cos(GEOREF.math.radians(75)) * 6_371_008.8 / 6_378_137
        self.assertAlmostEqual(ground, expected, delta=0.01)
        self.assertGreater(ground, 257)
        self.assertLess(ground, 260)
        matrix = [[1, 0, origin[0]], [0, -1, origin[1]], [0, 0, 1]]
        component = GEOREF.resolve_straight_component(
            {
                "straight_component": {
                    "endpoint_a": {"image": {"x": 0, "y": 0}},
                    "endpoint_b": {"image": {"x": 1000, "y": 0}},
                    "directionality": "forward",
                }
            },
            matrix,
        )
        self.assertAlmostEqual(component["length_m"], ground, delta=1e-6)
        self.assertEqual(component["distance_measurement"], "spherical_geodesic_ground_metres")
        image_points = [(0, 0), (1000, 0), (1000, 1000), (0, 1000), (500, 500)]
        targets = [GEOREF.apply_homography(matrix, point) for point in image_points]
        targets[-1] = (targets[-1][0] + 10, targets[-1][1])
        controls = []
        for index, (image_point, target) in enumerate(zip(image_points, targets, strict=True)):
            longitude, latitude = GEOREF.mercator_to_lonlat(*target)
            controls.append({
                "id": f"high{index}",
                "image": {"x": image_point[0], "y": image_point[1]},
                "geographic": {"longitude": longitude, "latitude": latitude},
            })
        registration = GEOREF.solve_registration({"control_points": controls}, (1000, 1000))
        projected_rmse = GEOREF.math.sqrt(sum(
            GEOREF.math.dist(
                GEOREF.apply_homography(registration["image_pixel_to_web_mercator"], image_point),
                target,
            ) ** 2
            for image_point, target in zip(image_points, targets, strict=True)
        ) / len(image_points))
        self.assertLess(registration["control_point_rmse_m"], projected_rmse * 0.27)
        self.assertEqual(registration["distance_measurement"], "spherical_geodesic_ground_metres")

    def test_projective_transform_and_deterministic_exports(self):
        metadata = json.loads(FIXTURE.read_text(encoding="utf-8"))
        solved = GEOREF.solve_registration(metadata, (320, 240))
        self.assertLess(solved["control_point_rmse_m"], 1e-5)
        for point in metadata["control_points"]:
            expected = GEOREF.lonlat_to_mercator(
                point["geographic"]["longitude"], point["geographic"]["latitude"]
            )
            actual = GEOREF.apply_homography(
                solved["image_pixel_to_web_mercator"],
                (point["image"]["x"], point["image"]["y"]),
            )
            self.assertLess(GEOREF.math.dist(expected, actual), 1e-5)

        overdetermined = json.loads(json.dumps(metadata))
        for index, image_point in enumerate(((75.0, 80.0), (245.0, 165.0)), start=5):
            projected = GEOREF.apply_homography(solved["image_pixel_to_web_mercator"], image_point)
            longitude, latitude = GEOREF.mercator_to_lonlat(*projected)
            overdetermined["control_points"].append({
                "id": f"cp{index}",
                "image": {"x": image_point[0], "y": image_point[1]},
                "geographic": {"longitude": longitude, "latitude": latitude, "crs": "EPSG:4326"},
            })
        least_squares = GEOREF.solve_registration(overdetermined, (320, 240))
        self.assertLess(least_squares["control_point_rmse_m"], 1e-5)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            image_path = base / "synthetic-grid.png"
            make_synthetic_grid(image_path)
            first = GEOREF.export_registration(FIXTURE, image_path, base / "first", max_dimension=256)
            second = GEOREF.export_registration(FIXTURE, image_path, base / "second", max_dimension=256)

            first_paths = {key: Path(value) for key, value in first["paths"].items()}
            second_paths = {key: Path(value) for key, value in second["paths"].items()}
            for path in first_paths.values():
                self.assertTrue(path.is_file(), path)

            with Image.open(first_paths["png"]) as warped:
                self.assertEqual(max(warped.size), 256)
                self.assertEqual(warped.mode, "RGBA")
                alpha = warped.getchannel("A")
                self.assertGreater(alpha.getbbox()[2] * alpha.getbbox()[3], 0)

            kml_root = ET.parse(first_paths["kml"]).getroot()
            kml_ns = "{http://www.opengis.net/kml/2.2}"
            kml_text = first_paths["kml"].read_text(encoding="utf-8")
            self.assertIn("no demonstrated predictive validity", kml_text)
            overlay = kml_root.find(f".//{kml_ns}GroundOverlay")
            self.assertIsNotNone(overlay)
            overlay_values = {
                node.get("name"): (node.find(f"{kml_ns}value").text or "")
                for node in overlay.findall(f".//{kml_ns}Data")
            }
            self.assertEqual(overlay_values["rights_status"], "local_analysis_only")
            self.assertEqual(overlay_values["rights_holder"], "Crop Circle Atlas test fixture")
            self.assertEqual(overlay_values["license"], "Synthetic test data")
            self.assertEqual(overlay_values["source_url"], "https://example.invalid/synthetic-test-only")
            with zipfile.ZipFile(first_paths["kmz"]) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
                self.assertIn("doc.kml", names)
                self.assertTrue(any(name.startswith("images/") and name.endswith(".png") for name in names))
                self.assertTrue(any(name.startswith("metadata/") and name.endswith(".json") for name in names))
                self.assertIn(b"unreviewed_local_registration", archive.read("doc.kml"))

            world_file = first_paths["world_file"].read_text(encoding="ascii").splitlines()
            self.assertEqual(len(world_file), 6)
            self.assertGreater(float(world_file[0]), 0)
            self.assertLess(float(world_file[3]), 0)

            resolved = json.loads(first_paths["registration"].read_text(encoding="utf-8"))
            self.assertEqual(resolved["straight_component"]["directionality"], "bidirectional")
            self.assertGreater(resolved["straight_component"]["length_m"], 10)
            self.assertIn("forward_azimuth_true_deg", resolved["straight_component"])
            self.assertEqual(resolved["straight_component"]["ray_origin"]["representative_point"], "straight_component_midpoint")
            self.assertEqual(resolved["straight_component"]["ray_origin"]["uncertainty_m"], 5)
            self.assertEqual(resolved["export"]["mode"], "local_analysis")

            for key in ("png", "world_file", "projection", "kml", "kmz", "registration"):
                self.assertEqual(
                    GEOREF.file_sha256(first_paths[key]),
                    GEOREF.file_sha256(second_paths[key]),
                    f"{key} was not deterministic",
                )

    def test_public_export_fails_closed_without_rights(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            image_path = base / "synthetic-grid.png"
            make_synthetic_grid(image_path)
            with self.assertRaisesRegex(GEOREF.RegistrationError, "rights_status_not_publication_authorized"):
                GEOREF.export_registration(
                    FIXTURE, image_path, base / "public", max_dimension=128, public_export=True
                )


if __name__ == "__main__":
    unittest.main()
