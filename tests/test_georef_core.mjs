import assert from "node:assert/strict";
import {
  applyHomography,
  computeHomography,
  initialBearing,
  invert3x3,
  lonLatToMercator,
  mercatorToLonLat,
  orientationFromImageSegment,
  planNorthUpRaster,
  projectedGroundDistanceMetres,
  solveRegistration,
} from "../web/georef-core.mjs";

const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

// A synthetic projective camera view: rotation, skew, scale, and perspective.
const expected = [
  [0.43, 0.08, -11131949.079327356],
  [-0.04, -0.51, 4865942.279503176],
  [0.00003, -0.00002, 1],
];
const source = [[0, 0], [800, 0], [800, 600], [0, 600]];
const target = source.map((point) => applyHomography(expected, point));
const solved = computeHomography(source, target);

for (const point of [[0, 0], [800, 0], [800, 600], [0, 600], [137.25, 444.75], [602.5, 211.125]]) {
  assert.ok(distance(applyHomography(solved, point), applyHomography(expected, point)) < 1e-6,
    `projective transform error exceeded one micrometre at ${point}`);
}

const inverse = invert3x3(solved);
for (const point of [[15, 27], [400, 300], [799, 599]]) {
  assert.ok(distance(applyHomography(inverse, applyHomography(solved, point)), point) < 1e-7,
    `inverse round-trip failed at ${point}`);
}

const sourceWithChecks = [...source, [175, 215], [620, 410]];
const targetWithChecks = sourceWithChecks.map((point) => applyHomography(expected, point));
const leastSquaresSolved = computeHomography(sourceWithChecks, targetWithChecks);
for (const point of [[31, 52], [333, 222], [742, 515]]) {
  assert.ok(distance(applyHomography(leastSquaresSolved, point), applyHomography(expected, point)) < 1e-6,
    `least-squares projective error exceeded one micrometre at ${point}`);
}

const controls = sourceWithChecks.map((point, index) => {
  const [longitude, latitude] = mercatorToLonLat(...targetWithChecks[index]);
  return {
    id: `cp${index + 1}`,
    image: { x: point[0], y: point[1] },
    geographic: { longitude, latitude, crs: "EPSG:4326" },
  };
});
const registration = solveRegistration(controls, 800, 600);
assert.ok(registration.rmseMetres < 1e-6, `unexpected fit RMSE ${registration.rmseMetres}`);

const plan = planNorthUpRaster(registration.matrix, 800, 600, 1024);
assert.equal(Math.max(plan.width, plan.height), 1024);
assert.ok(plan.boundsWgs84.west < plan.boundsWgs84.east);
assert.ok(plan.boundsWgs84.south < plan.boundsWgs84.north);

const orientation = orientationFromImageSegment({
  matrix: registration.matrix,
  endpointA: [180, 300],
  endpointB: [650, 300],
  transformRmseMetres: registration.rmseMetres,
  groundControlUncertaintyMetres: 3,
  endpointClickUncertaintyPixels: 1.5,
  directionality: "reverse",
});
assert.equal(orientation.directionality, "reverse");
assert.ok(Math.abs(orientation.azimuthTrueDegrees - orientation.reverseBearingTrueDegrees) < 1e-12);
assert.ok(orientation.lengthMetres > 100);
assert.ok(orientation.azimuthUncertaintyDegrees > 0 && orientation.azimuthUncertaintyDegrees < 10);
assert.ok(orientation.originUncertaintyMetres >= 3);
assert.ok(Math.abs(initialBearing(
  [orientation.endpointA.longitude, orientation.endpointA.latitude],
  [orientation.endpointB.longitude, orientation.endpointB.latitude],
) - orientation.forwardBearingTrueDegrees) < 1e-10);

// EPSG:3857 exaggerates local scale by sec(latitude); reported measurements must not.
const highLatitudeOrigin = lonLatToMercator(0, 75);
const highLatitudeGroundDistance = projectedGroundDistanceMetres(
  highLatitudeOrigin, [highLatitudeOrigin[0] + 1000, highLatitudeOrigin[1]],
);
const expectedHighLatitudeDistance = 1000 * Math.cos(75 * Math.PI / 180) * 6371008.8 / 6378137;
assert.ok(Math.abs(highLatitudeGroundDistance - expectedHighLatitudeDistance) < 0.01,
  `high-latitude ground conversion failed: ${highLatitudeGroundDistance}`);
assert.ok(highLatitudeGroundDistance < 260 && highLatitudeGroundDistance > 257);
const highLatitudeOrientation = orientationFromImageSegment({
  matrix: [[1, 0, highLatitudeOrigin[0]], [0, -1, highLatitudeOrigin[1]], [0, 0, 1]],
  endpointA: [0, 0],
  endpointB: [1000, 0],
  groundControlUncertaintyMetres: 2,
  endpointClickUncertaintyPixels: 1,
  directionality: "forward",
});
assert.ok(Math.abs(highLatitudeOrientation.lengthMetres - highLatitudeGroundDistance) < 1e-6);
assert.equal(highLatitudeOrientation.distanceMeasurement, "spherical_geodesic_ground_metres");
assert.ok(highLatitudeOrientation.originUncertaintyMetres > 2 && highLatitudeOrientation.originUncertaintyMetres < 2.02,
  `click uncertainty used projected metres: ${highLatitudeOrientation.originUncertaintyMetres}`);
const highLatitudeImagePoints = [[0, 0], [1000, 0], [1000, 1000], [0, 1000], [500, 500]];
const highLatitudeMatrix = [[1, 0, highLatitudeOrigin[0]], [0, -1, highLatitudeOrigin[1]], [0, 0, 1]];
const highLatitudeTargets = highLatitudeImagePoints.map((point) => applyHomography(highLatitudeMatrix, point));
highLatitudeTargets[4][0] += 10; // An intentionally mismatched fifth landmark.
const highLatitudeControls = highLatitudeImagePoints.map((point, index) => {
  const [longitude, latitude] = mercatorToLonLat(...highLatitudeTargets[index]);
  return { id: `high${index}`, image: { x: point[0], y: point[1] }, geographic: { longitude, latitude } };
});
const highLatitudeRegistration = solveRegistration(highLatitudeControls, 1000, 1000);
const projectedResidualRmse = Math.sqrt(highLatitudeImagePoints.reduce((sum, point, index) => {
  const estimated = applyHomography(highLatitudeRegistration.matrix, point);
  return sum + distance(estimated, highLatitudeTargets[index]) ** 2;
}, 0) / highLatitudeImagePoints.length);
assert.ok(highLatitudeRegistration.rmseMetres < projectedResidualRmse * 0.27,
  `fit RMSE used projected metres: ground=${highLatitudeRegistration.rmseMetres} projected=${projectedResidualRmse}`);
assert.equal(highLatitudeRegistration.distanceMeasurement, "spherical_geodesic_ground_metres");

assert.throws(
  () => computeHomography([[0, 0], [1, 0], [2, 0], [3, 0]], target),
  /collinear|clustered/i,
);

console.log(`PASS georef-core max_transform_error_m<1e-6 rmse_m=${registration.rmseMetres.toExponential(3)} azimuth_deg=${orientation.azimuthTrueDegrees.toFixed(6)}`);
