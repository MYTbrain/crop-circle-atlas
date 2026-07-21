#!/usr/bin/env python3
"""Detect straight primitives in Crop Circle Center catalogue diagrams.

The detector deliberately reports axes in *image space*.  It never converts a
diagram axis into a geographic bearing.  Geographic azimuths belong only in
``data/orientation_observations.csv`` after review of independent north
evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as exc:  # pragma: no cover - environment-dependent message
    raise SystemExit(
        "OpenCV is required: python -m pip install opencv-python-headless==4.13.0.92"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = Path(r"C:\Users\jarod\Downloads\COMBINED.pdf")
ASSERTIONS_PATH = ROOT / "data" / "source_assertions.csv"
LABELS_PATH = ROOT / "data" / "straight_component_validation_labels.csv"
OUTPUT_CSV = ROOT / "data" / "straight_component_candidates.csv"
OUTPUT_DIR = ROOT / "outputs" / "straight-components"
TMP_DIR = ROOT / "tmp" / "pdfs" / "straight-components"
DETECTOR_VERSION = "straight-components-v1.0.0"
PDF_SOURCE_NAME = "Crop Circle Center PDF catalog"

# These ratios describe the stable 4 x 5 card grid in the 309-page catalogue.
# They are scale-independent and were checked at pages 1, 50, 100, 150, 200,
# 250, and 309.  The crop stops above each card's caption and separator rules.
BODY_BOTTOM_RATIO = 1650.0 / 1754.0
COL_OVERLAP_RATIO = 10.0 / (1240.0 / 4.0)
DIAGRAM_TOP_IN_ROW = 10.0 / 330.0
# Lower rows sit closer to their caption baselines.  Row-specific limits keep
# place/date text out of the diagram crop while retaining the full glyph.
DIAGRAM_HEIGHT_IN_ROW = (220.0, 220.0, 220.0, 205.0, 200.0)

INK_THRESHOLD = 140
MID_GRAY_THRESHOLD = 180
MIN_SEGMENT_PX = 16.0
ANGLE_CLUSTER_TOLERANCE_DEG = 4.0
CAVEAT = "diagram-space axis only; not a true-north azimuth"


@dataclass(frozen=True)
class Segment:
    length: float
    angle: float


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def angle_distance(a: float, b: float) -> float:
    """Smallest distance between two unoriented axes, in degrees."""
    return abs((a - b + 90.0) % 180.0 - 90.0)


def axis_mean(weighted_angles: list[tuple[float, float]]) -> float:
    x = sum(weight * math.cos(math.radians(2.0 * angle)) for weight, angle in weighted_angles)
    y = sum(weight * math.sin(math.radians(2.0 * angle)) for weight, angle in weighted_angles)
    return (math.degrees(math.atan2(y, x)) / 2.0) % 180.0


def axis_uncertainty(weighted_angles: list[tuple[float, float]], mean: float) -> float:
    total = sum(weight for weight, _ in weighted_angles)
    if not total:
        return 90.0
    variance = sum(weight * angle_distance(angle, mean) ** 2 for weight, angle in weighted_angles) / total
    return math.sqrt(variance)


def locate_pdftoppm(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("pdftoppm")
    if found:
        candidates.append(Path(found))
    # Standard WinGet Poppler location used by this workspace.
    winget_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_root.exists():
        candidates.extend(sorted(winget_root.glob("oschwartz10612.Poppler_*/*/Library/bin/pdftoppm.exe")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit("pdftoppm was not found; install Poppler or pass --pdftoppm")


def read_pdf_assertions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["source_name"] == PDF_SOURCE_NAME]
    if not rows:
        raise SystemExit(f"No {PDF_SOURCE_NAME!r} rows in {path}")
    keys = [(int(row["source_page"]), int(row["source_slot"])) for row in rows]
    if len(keys) != len(set(keys)):
        raise SystemExit("Duplicate PDF page/slot keys in source assertions")
    return sorted(rows, key=lambda row: (int(row["source_page"]), int(row["source_slot"])))


def read_labels(path: Path) -> dict[tuple[int, int], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    labels: dict[tuple[int, int], dict[str, str]] = {}
    for row in rows:
        key = (int(row["source_page"]), int(row["source_slot"]))
        if row["manual_label"] not in {"straight", "no_straight", "no_diagram"}:
            raise SystemExit(f"Unsupported manual label at {key}: {row['manual_label']}")
        labels[key] = row
    return labels


def crop_box(width: int, height: int, slot: int) -> tuple[int, int, int, int]:
    if not 1 <= slot <= 20:
        raise ValueError(f"Card slot must be 1..20, got {slot}")
    row, col = divmod(slot - 1, 4)
    col_width = width / 4.0
    body_bottom = height * BODY_BOTTOM_RATIO
    row_height = body_bottom / 5.0
    x0 = max(0, round(col * col_width - col_width * COL_OVERLAP_RATIO))
    x1 = min(width, round((col + 1) * col_width + col_width * COL_OVERLAP_RATIO))
    y0 = round(row * row_height + row_height * DIAGRAM_TOP_IN_ROW)
    y1 = round(y0 + height * DIAGRAM_HEIGHT_IN_ROW[row] / 1754.0)
    return x0, y0, x1, y1


def cluster_segments(segments: list[Segment]) -> list[dict[str, float | int]]:
    candidates: list[dict[str, float | int]] = []
    for seed in segments:
        members = [segment for segment in segments if angle_distance(segment.angle, seed.angle) <= ANGLE_CLUSTER_TOLERANCE_DEG]
        weighted = [(segment.length, segment.angle) for segment in members]
        mean = axis_mean(weighted)
        support = sum(segment.length for segment in members)
        candidates.append(
            {
                "axis": mean,
                "support": support,
                "count": len(members),
                "uncertainty": axis_uncertainty(weighted, mean),
                "max_length": max(segment.length for segment in members),
            }
        )
    candidates.sort(key=lambda item: (-float(item["support"]), float(item["axis"])))
    clusters: list[dict[str, float | int]] = []
    for candidate in candidates:
        if all(angle_distance(float(candidate["axis"]), float(kept["axis"])) > 10.0 for kept in clusters):
            clusters.append(candidate)
    return clusters


def classify(max_norm: float, dominant_norm: float, dominant_fraction: float) -> str:
    """Return a review tier, tuned for precision before recall.

    ``high`` and ``medium`` identify stronger candidates. ``low`` intentionally
    preserves weak/short/complex cases for human review. None of the tiers is a
    geographic-orientation claim.
    """
    if (
        max_norm >= 0.38
        or (max_norm >= 0.26 and dominant_fraction >= 0.20)
        or (dominant_norm >= 0.90 and dominant_fraction >= 0.15)
        or (dominant_fraction >= 0.35 and dominant_norm >= 0.35 and max_norm >= 0.12)
    ):
        return "high"
    if (
        (max_norm >= 0.16 and dominant_fraction >= 0.20)
        or (dominant_norm >= 0.75 and dominant_fraction >= 0.18)
        or (dominant_fraction >= 0.32 and dominant_norm >= 0.28)
    ):
        return "medium"
    if max_norm >= 0.15 or dominant_norm >= 0.40 or (dominant_fraction >= 0.28 and dominant_norm >= 0.22):
        return "low"
    return "none"


def analyze_crop(gray: "np.ndarray") -> dict[str, object]:
    dark_pixels = int(np.count_nonzero(gray < INK_THRESHOLD))
    mid_pixels = int(np.count_nonzero(gray < MID_GRAY_THRESHOLD))
    dark_to_mid = dark_pixels / mid_pixels if mid_pixels else 0.0
    dark_mask = (gray < INK_THRESHOLD).astype(np.uint8)
    component_count, _, component_stats, _ = cv2.connectedComponentsWithStats(dark_mask, 8)
    dark_component_areas = component_stats[1:, cv2.CC_STAT_AREA] if component_count > 1 else []
    largest_dark_component = int(max(dark_component_areas, default=0))
    # The catalogue's placeholder is gray text: many small dark components over
    # a larger mid-gray glyph area.  Requiring that topology avoids mistaking
    # low-contrast line drawings (for example page 50, slot 4) for placeholders.
    no_diagram = (
        mid_pixels >= 1200
        and dark_to_mid < 0.55
        and component_count - 1 >= 30
        and largest_dark_component < 200
    )
    blank = mid_pixels < 80

    binary = np.where(gray < INK_THRESHOLD, 0, 255).astype(np.uint8)
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    detected = detector.detect(binary)[0]
    segments: list[Segment] = []
    if detected is not None:
        for raw in detected[:, 0]:
            x1, y1, x2, y2 = (float(value) for value in raw)
            length = math.hypot(x2 - x1, y2 - y1)
            if length >= MIN_SEGMENT_PX:
                # Image coordinates: 0 degrees points right and angles increase
                # clockwise because image y increases downward. Axis is modulo 180.
                angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
                segments.append(Segment(length=length, angle=angle))

    clusters = cluster_segments(segments)
    total_support = sum(segment.length for segment in segments)
    dominant = clusters[0] if clusters else None
    max_length = max((segment.length for segment in segments), default=0.0)
    dominant_support = float(dominant["support"]) if dominant else 0.0
    dominant_fraction = dominant_support / total_support if total_support else 0.0
    scale = float(min(gray.shape))
    max_norm = max_length / scale if scale else 0.0
    dominant_norm = dominant_support / scale if scale else 0.0
    tier = "none" if no_diagram or blank else classify(max_norm, dominant_norm, dominant_fraction)
    status = "no_diagram" if no_diagram else "blank" if blank else "diagram"

    raw_score = (
        0.45 * min(max_norm / 0.38, 1.0)
        + 0.35 * min(dominant_norm / 0.90, 1.0)
        + 0.20 * min(dominant_fraction / 0.35, 1.0)
    )
    score = 0.0 if status != "diagram" else min(raw_score, 1.0)
    useful_clusters = [cluster for cluster in clusters if float(cluster["support"]) >= 24.0][:4]
    axes = ";".join(f"{float(cluster['axis']):.1f}" for cluster in useful_clusters)

    return {
        "diagram_status": status,
        "straight_component_tier": tier,
        "straight_component_candidate": "yes" if tier in {"high", "medium", "low"} else "no",
        "detector_score": f"{score:.3f}",
        "dominant_axis_image_deg": f"{float(dominant['axis']):.1f}" if dominant and status == "diagram" else "",
        "axis_uncertainty_deg": f"{float(dominant['uncertainty']):.1f}" if dominant and status == "diagram" else "",
        "axis_candidates_image_deg": axes if status == "diagram" else "",
        "line_segment_count": str(len(segments)),
        "max_segment_length_px": f"{max_length:.1f}",
        "dominant_support_length_px": f"{dominant_support:.1f}",
        "dominant_support_fraction": f"{dominant_fraction:.3f}",
        "ink_pixels": str(dark_pixels),
        "mid_gray_pixels": str(mid_pixels),
        "dark_to_mid_ratio": f"{dark_to_mid:.3f}",
        "dark_component_count": str(component_count - 1),
        "largest_dark_component_px": str(largest_dark_component),
    }


def render_page(pdftoppm: Path, pdf: Path, page: int, dpi: int, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(pdftoppm),
        "-f",
        str(page),
        "-l",
        str(page),
        "-r",
        str(dpi),
        "-gray",
        "-png",
        "-singlefile",
        str(pdf),
        str(target.with_suffix("")),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    if not target.exists():
        raise RuntimeError(f"Expected rendered page was not created: {target}")
    return target


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # BOM makes non-ASCII locality names survive direct Excel/PowerShell opens
    # without changing the underlying Unicode strings or double-decoding bytes.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def confusion(rows: list[dict[str, object]], positive_tiers: set[str]) -> dict[str, float | int | None]:
    counts = Counter(tp=0, fp=0, tn=0, fn=0)
    for row in rows:
        actual = row["manual_label"] == "straight"
        predicted = row["straight_component_tier"] in positive_tiers
        if actual and predicted:
            counts["tp"] += 1
        elif not actual and predicted:
            counts["fp"] += 1
        elif not actual and not predicted:
            counts["tn"] += 1
        else:
            counts["fn"] += 1
    tp, fp, tn, fn = (counts[name] for name in ("tp", "fp", "tn", "fn"))
    total = tp + fp + tn + fn

    def ratio(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    return {
        **counts,
        "n": total,
        "accuracy": ratio(tp + tn, total),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


def make_contact_sheets(
    records: list[dict[str, object]],
    crops: dict[tuple[int, int], "np.ndarray"],
    prefix: str,
    output_dir: Path,
    per_sheet: int = 30,
) -> list[str]:
    output_paths: list[str] = []
    tile_w, tile_h = 280, 230
    columns = 5
    rows_per_sheet = math.ceil(per_sheet / columns)
    for sheet_number, start in enumerate(range(0, len(records), per_sheet), start=1):
        batch = records[start : start + per_sheet]
        canvas = np.full((rows_per_sheet * tile_h, columns * tile_w, 3), 255, dtype=np.uint8)
        for index, record in enumerate(batch):
            page = int(record["source_page"])
            slot = int(record["source_slot"])
            crop = crops[(page, slot)]
            display = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
            display = cv2.resize(display, (tile_w - 8, tile_h - 42), interpolation=cv2.INTER_AREA)
            manual = str(record.get("manual_label", ""))
            predicted = str(record["straight_component_tier"])
            if manual:
                actual = manual == "straight"
                predicted_positive = predicted in {"high", "medium", "low"}
                color = (0, 145, 0) if actual == predicted_positive else (0, 0, 220)
            else:
                color = {"high": (0, 0, 200), "medium": (0, 140, 255), "low": (0, 180, 180)}.get(predicted, (120, 120, 120))
            cv2.rectangle(display, (0, 0), (display.shape[1] - 1, display.shape[0] - 1), color, 3)
            row, col = divmod(index, columns)
            x, y = col * tile_w + 4, row * tile_h + 4
            canvas[y : y + display.shape[0], x : x + display.shape[1]] = display
            text_y = y + tile_h - 31
            cv2.putText(canvas, f"p{page} s{slot}  pred={predicted}", (x + 2, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            if manual:
                cv2.putText(canvas, f"manual={manual}", (x + 2, text_y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            else:
                cv2.putText(canvas, f"score={record['detector_score']} axis={record['dominant_axis_image_deg']}", (x + 2, text_y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
        target = output_dir / f"{prefix}_{sheet_number:02d}.jpg"
        cv2.imwrite(str(target), canvas, [cv2.IMWRITE_JPEG_QUALITY, 90])
        output_paths.append(str(target.relative_to(ROOT)).replace("\\", "/"))
    return output_paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--pdftoppm", help="Explicit path to Poppler pdftoppm")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--keep-rendered-pages", action="store_true")
    args = parser.parse_args()

    if args.dpi != 150:
        raise SystemExit("The validated detector currently requires --dpi 150")
    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")

    pdftoppm = locate_pdftoppm(args.pdftoppm)
    assertions = read_pdf_assertions(ASSERTIONS_PATH)
    labels = read_labels(LABELS_PATH)
    pdf_sha256 = sha256_file(args.pdf)
    assertions_by_page: dict[int, list[dict[str, str]]] = {}
    for assertion in assertions:
        assertions_by_page.setdefault(int(assertion["source_page"]), []).append(assertion)

    output_rows: list[dict[str, object]] = []
    contact_crops: dict[tuple[int, int], np.ndarray] = {}
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for page in sorted(assertions_by_page):
        rendered = render_page(pdftoppm, args.pdf, page, args.dpi, TMP_DIR / f"page-{page:04d}.png")
        image = cv2.imread(str(rendered), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise RuntimeError(f"OpenCV could not read {rendered}")
        height, width = image.shape
        for assertion in assertions_by_page[page]:
            slot = int(assertion["source_slot"])
            x0, y0, x1, y1 = crop_box(width, height, slot)
            crop = image[y0:y1, x0:x1]
            analysis = analyze_crop(crop)
            candidate_key = f"{assertion['assertion_id']}|{pdf_sha256}|{DETECTOR_VERSION}"
            record: dict[str, object] = {
                "candidate_id": "sc_" + hashlib.sha1(candidate_key.encode("utf-8")).hexdigest()[:16],
                "assertion_id": assertion["assertion_id"],
                "source_name": assertion["source_name"],
                "source_page": assertion["source_page"],
                "source_slot": assertion["source_slot"],
                "year": assertion["year"],
                "month": assertion["month"],
                "day": assertion["day"],
                "date_iso": assertion["date_iso"],
                "place": assertion["place"],
                "region": assertion["region"],
                "country": assertion["country"],
                "country_code": assertion["country_code"],
                "crop_box_px": f"{x0},{y0},{x1},{y1}",
                "page_width_px": width,
                "page_height_px": height,
                **analysis,
                "axis_reference": "image x-axis; 0=right; clockwise; modulo 180",
                "geographic_azimuth_qualified": "no",
                "caveat": CAVEAT,
                "detector_version": DETECTOR_VERSION,
                "source_pdf_sha256": pdf_sha256,
            }
            label = labels.get((page, slot))
            if label:
                record["manual_label"] = label["manual_label"]
                record["manual_review_note"] = label.get("review_note", "")
            output_rows.append(record)
            if label:
                contact_crops[(page, slot)] = crop.copy()
        if not args.keep_rendered_pages:
            rendered.unlink(missing_ok=True)

    fieldnames = [
        "candidate_id", "assertion_id", "source_name", "source_page", "source_slot",
        "year", "month", "day", "date_iso", "place", "region", "country", "country_code",
        "crop_box_px", "page_width_px", "page_height_px", "diagram_status",
        "straight_component_tier", "straight_component_candidate", "detector_score",
        "dominant_axis_image_deg", "axis_uncertainty_deg", "axis_candidates_image_deg",
        "line_segment_count", "max_segment_length_px", "dominant_support_length_px",
        "dominant_support_fraction", "ink_pixels", "mid_gray_pixels", "dark_to_mid_ratio",
        "dark_component_count", "largest_dark_component_px",
        "axis_reference", "geographic_azimuth_qualified", "caveat", "detector_version",
        "source_pdf_sha256",
    ]
    write_csv(OUTPUT_CSV, output_rows, fieldnames)

    labeled = [row for row in output_rows if row.get("manual_label")]
    classification_labeled = [row for row in labeled if row["manual_label"] != "no_diagram"]
    label_status_accuracy = None
    if labeled:
        correct_status = sum(
            (row["manual_label"] == "no_diagram") == (row["diagram_status"] == "no_diagram")
            for row in labeled
        )
        label_status_accuracy = round(correct_status / len(labeled), 4)

    sheet_paths = make_contact_sheets(labeled, contact_crops, "qa_labeled_sample", OUTPUT_DIR) if labeled else []
    errors = [
        row for row in classification_labeled
        if (row["manual_label"] == "straight") != (row["straight_component_tier"] in {"high", "medium", "low"})
    ]
    if errors:
        sheet_paths.extend(make_contact_sheets(errors, contact_crops, "qa_all_tier_errors", OUTPUT_DIR))

    metrics = {
        "generated_at": utc_now(),
        "detector_version": DETECTOR_VERSION,
        "opencv_version": cv2.__version__,
        "pdf_path": str(args.pdf.resolve()),
        "pdf_sha256": pdf_sha256,
        "pdf_assertions_processed": len(output_rows),
        "tier_counts": dict(sorted(Counter(str(row["straight_component_tier"]) for row in output_rows).items())),
        "diagram_status_counts": dict(sorted(Counter(str(row["diagram_status"]) for row in output_rows).items())),
        "validated_thresholds": {
            "high_only": confusion(classification_labeled, {"high"}),
            "high_or_medium": confusion(classification_labeled, {"high", "medium"}),
            "all_candidate_tiers": confusion(classification_labeled, {"high", "medium", "low"}),
        },
        "labeled_sample": {
            "total": len(labeled),
            "classification_rows": len(classification_labeled),
            "manual_label_counts": dict(sorted(Counter(str(row["manual_label"]) for row in labeled).items())),
            "no_diagram_status_accuracy": label_status_accuracy,
            "pages": sorted({int(row["source_page"]) for row in labeled}),
        },
        "angle_semantics": {
            "reference": "image x-axis",
            "zero": "right",
            "direction": "clockwise in image coordinates",
            "period_degrees": 180,
            "geographic_interpretation": "none",
        },
        "threshold_notes": {
            "high": "strong long or concentrated straight-segment evidence",
            "medium": "moderate straight-segment evidence",
            "low": "weak, short, or complex evidence retained for review",
            "none": "no detector threshold met",
        },
        "contact_sheets": sheet_paths,
    }
    (OUTPUT_DIR / "qa_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
