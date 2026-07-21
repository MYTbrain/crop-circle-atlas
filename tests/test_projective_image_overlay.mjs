import assert from "node:assert/strict";
import test from "node:test";

import {
  applyHomography,
  homographyFromUnitSquare,
  normalizeGeodeticCorners,
  solveHomography,
} from "../web/projective-image-overlay.mjs";

const closePoint = (actual, expected, tolerance = 1e-8) => {
  assert.equal(actual.length, 2);
  actual.forEach((value, index) => {
    assert.ok(Math.abs(value - expected[index]) <= tolerance,
      `${actual} did not map to ${expected}`);
  });
};

test("homography maps all four source-image corners to a skewed target footprint", () => {
  const corners = [[40, 30], [440, 5], [390, 330], [15, 270]];
  const matrix = homographyFromUnitSquare(corners);
  const sourceCorners = [[0, 0], [1, 0], [1, 1], [0, 1]];
  sourceCorners.forEach((point, index) => closePoint(applyHomography(matrix, point), corners[index]));
});

test("perspective mapping is invertible for interior points", () => {
  const source = [[0, 0], [1, 0], [1, 1], [0, 1]];
  const target = [[100, 80], [550, 20], [470, 420], [35, 300]];
  const forward = solveHomography(source, target);
  const inverse = solveHomography(target, source);
  const point = [0.37, 0.64];
  closePoint(applyHomography(inverse, applyHomography(forward, point)), point, 1e-9);
});

test("geodetic corners retain image-corner order across supported input forms", () => {
  const normalized = normalizeGeodeticCorners({
    topLeft: { lat: 45.1, lng: -122.8 },
    topRight: [45.11, -122.7],
    bottomRight: { latitude: 45.0, longitude: -122.69 },
    bottomLeft: [44.99, -122.81],
  });
  assert.deepEqual(normalized, [
    [45.1, -122.8],
    [45.11, -122.7],
    [45.0, -122.69],
    [44.99, -122.81],
  ]);
});

test("folded or degenerate corner mappings fail closed", () => {
  assert.throws(
    () => homographyFromUnitSquare([[0, 0], [1, 1], [1, 0], [0, 1]]),
    /convex quadrilaterals/,
  );
  assert.throws(
    () => homographyFromUnitSquare([[0, 0], [1, 0], [2, 0], [3, 0]]),
    /convex quadrilaterals/,
  );
});

