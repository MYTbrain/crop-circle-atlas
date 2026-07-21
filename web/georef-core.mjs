/**
 * Pure georeferencing math shared by the browser lab and deterministic tests.
 * Coordinates are image pixels, WGS84 longitude/latitude, and EPSG:3857 metres.
 */

export const REGISTRATION_SCHEMA = "crop-circle-atlas/georeference-registration/v1";
export const WEB_MERCATOR_RADIUS_M = 6378137;
export const MAX_MERCATOR_LAT = 85.0511287798066;

const EPSILON = 1e-12;

export function lonLatToMercator(longitude, latitude) {
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
    throw new TypeError("Longitude and latitude must be finite numbers.");
  }
  const lat = Math.max(-MAX_MERCATOR_LAT, Math.min(MAX_MERCATOR_LAT, latitude));
  const x = WEB_MERCATOR_RADIUS_M * longitude * Math.PI / 180;
  const y = WEB_MERCATOR_RADIUS_M * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
  return [x, y];
}

export function mercatorToLonLat(x, y) {
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    throw new TypeError("Projected coordinates must be finite numbers.");
  }
  return [
    x / WEB_MERCATOR_RADIUS_M * 180 / Math.PI,
    (2 * Math.atan(Math.exp(y / WEB_MERCATOR_RADIUS_M)) - Math.PI / 2) * 180 / Math.PI,
  ];
}

export function greatCircleDistanceMetres(fromLonLat, toLonLat) {
  const radians = (value) => value * Math.PI / 180;
  const [lon1, lat1] = fromLonLat.map(radians);
  const [lon2, lat2] = toLonLat.map(radians);
  const deltaLat = lat2 - lat1;
  const deltaLon = lon2 - lon1;
  const haversine = Math.sin(deltaLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLon / 2) ** 2;
  return 6371008.8 * 2 * Math.asin(Math.min(1, Math.sqrt(haversine)));
}

export function projectedGroundDistanceMetres(fromMercator, toMercator) {
  return greatCircleDistanceMetres(
    mercatorToLonLat(...fromMercator),
    mercatorToLonLat(...toMercator),
  );
}

export function geographicMidpoint(fromLonLat, toLonLat) {
  const radians = (value) => value * Math.PI / 180;
  const degrees = (value) => value * 180 / Math.PI;
  const [lon1, lat1] = fromLonLat.map(radians);
  const [lon2, lat2] = toLonLat.map(radians);
  const deltaLon = lon2 - lon1;
  const bx = Math.cos(lat2) * Math.cos(deltaLon);
  const by = Math.cos(lat2) * Math.sin(deltaLon);
  const latitude = Math.atan2(
    Math.sin(lat1) + Math.sin(lat2),
    Math.hypot(Math.cos(lat1) + bx, by),
  );
  const longitude = lon1 + Math.atan2(by, Math.cos(lat1) + bx);
  return [((degrees(longitude) + 540) % 360) - 180, degrees(latitude)];
}

export function multiplyMatrices(a, b) {
  if (!a.length || !b.length || a[0].length !== b.length) {
    throw new Error("Matrix dimensions do not agree.");
  }
  return a.map((row) => b[0].map((_, column) =>
    row.reduce((sum, value, index) => sum + value * b[index][column], 0)));
}

export function invert3x3(matrix) {
  const [[a, b, c], [d, e, f], [g, h, i]] = matrix;
  const A = e * i - f * h;
  const B = c * h - b * i;
  const C = b * f - c * e;
  const D = f * g - d * i;
  const E = a * i - c * g;
  const F = c * d - a * f;
  const G = d * h - e * g;
  const H = b * g - a * h;
  const I = a * e - b * d;
  const determinant = a * A + b * D + c * G;
  if (!Number.isFinite(determinant) || Math.abs(determinant) < EPSILON) {
    throw new Error("Transform matrix is singular.");
  }
  return [[A, B, C], [D, E, F], [G, H, I]].map((row) => row.map((value) => value / determinant));
}

export function applyHomography(matrix, point) {
  const [x, y] = point;
  const denominator = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2];
  if (!Number.isFinite(denominator) || Math.abs(denominator) < EPSILON) {
    throw new Error("Point maps to the projective horizon.");
  }
  return [
    (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / denominator,
    (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / denominator,
  ];
}

function solveLinearSystem(matrix, vector) {
  const n = vector.length;
  const augmented = matrix.map((row, index) => [...row, vector[index]]);
  for (let column = 0; column < n; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < n; row += 1) {
      if (Math.abs(augmented[row][column]) > Math.abs(augmented[pivot][column])) pivot = row;
    }
    if (Math.abs(augmented[pivot][column]) < EPSILON) {
      throw new Error("Control points are degenerate or nearly collinear.");
    }
    [augmented[column], augmented[pivot]] = [augmented[pivot], augmented[column]];
    const divisor = augmented[column][column];
    for (let j = column; j <= n; j += 1) augmented[column][j] /= divisor;
    for (let row = 0; row < n; row += 1) {
      if (row === column) continue;
      const factor = augmented[row][column];
      for (let j = column; j <= n; j += 1) augmented[row][j] -= factor * augmented[column][j];
    }
  }
  return augmented.map((row) => row[n]);
}

function solveLeastSquares(matrix, vector) {
  const rows = matrix.length;
  const columns = matrix[0].length;
  if (rows < columns) throw new Error("Not enough equations for the projective transform.");
  const qr = matrix.map((row) => [...row]);
  const transformed = [...vector];
  for (let column = 0; column < columns; column += 1) {
    const norm = Math.hypot(...qr.slice(column).map((row) => row[column]));
    if (norm < EPSILON) throw new Error("Control points are degenerate or nearly collinear.");
    const alpha = qr[column][column] >= 0 ? -norm : norm;
    const reflector = Array(rows - column).fill(0);
    reflector[0] = qr[column][column] - alpha;
    for (let row = column + 1; row < rows; row += 1) reflector[row - column] = qr[row][column];
    const reflectorNorm = reflector.reduce((sum, value) => sum + value ** 2, 0);
    if (reflectorNorm < EPSILON) continue;
    for (let targetColumn = column; targetColumn < columns; targetColumn += 1) {
      let projection = 0;
      for (let row = column; row < rows; row += 1) projection += reflector[row - column] * qr[row][targetColumn];
      projection *= 2 / reflectorNorm;
      for (let row = column; row < rows; row += 1) qr[row][targetColumn] -= projection * reflector[row - column];
    }
    let vectorProjection = 0;
    for (let row = column; row < rows; row += 1) vectorProjection += reflector[row - column] * transformed[row];
    vectorProjection *= 2 / reflectorNorm;
    for (let row = column; row < rows; row += 1) transformed[row] -= vectorProjection * reflector[row - column];
  }
  const solution = Array(columns).fill(0);
  for (let row = columns - 1; row >= 0; row -= 1) {
    const known = qr[row].slice(row + 1, columns).reduce((sum, value, index) => sum + value * solution[row + 1 + index], 0);
    if (Math.abs(qr[row][row]) < EPSILON) throw new Error("Control points do not uniquely determine a projective transform.");
    solution[row] = (transformed[row] - known) / qr[row][row];
  }
  return solution;
}

function normalization(points) {
  const center = points.reduce((sum, [x, y]) => [sum[0] + x, sum[1] + y], [0, 0])
    .map((value) => value / points.length);
  const meanDistance = points.reduce((sum, [x, y]) =>
    sum + Math.hypot(x - center[0], y - center[1]), 0) / points.length;
  if (!Number.isFinite(meanDistance) || meanDistance < EPSILON) {
    throw new Error("Control points do not span a usable area.");
  }
  const scale = Math.SQRT2 / meanDistance;
  const matrix = [[scale, 0, -scale * center[0]], [0, scale, -scale * center[1]], [0, 0, 1]];
  return { matrix, points: points.map((point) => applyHomography(matrix, point)) };
}

function maxTriangleArea(points) {
  let maximum = 0;
  for (let a = 0; a < points.length - 2; a += 1) {
    for (let b = a + 1; b < points.length - 1; b += 1) {
      for (let c = b + 1; c < points.length; c += 1) {
        const [p, q, r] = [points[a], points[b], points[c]];
        maximum = Math.max(maximum, Math.abs(
          (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]),
        ) / 2);
      }
    }
  }
  return maximum;
}

function validatePointSet(points, label) {
  if (points.length < 4) throw new Error(`${label} must contain at least four points.`);
  if (points.some((point) => point.length !== 2 || point.some((value) => !Number.isFinite(value)))) {
    throw new Error(`${label} must contain finite two-dimensional coordinates.`);
  }
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const diagonalSquared = (Math.max(...xs) - Math.min(...xs)) ** 2 + (Math.max(...ys) - Math.min(...ys)) ** 2;
  if (diagonalSquared < EPSILON || maxTriangleArea(points) / diagonalSquared < 1e-5) {
    throw new Error(`${label} are collinear or too tightly clustered.`);
  }
}

/** Solve a projective transform from four exact or five-plus least-squares pairs. */
export function computeHomography(sourcePoints, targetPoints) {
  validatePointSet(sourcePoints, "Image control points");
  validatePointSet(targetPoints, "Map control points");
  if (sourcePoints.length !== targetPoints.length) throw new Error("Image and map control-point counts differ.");
  const source = normalization(sourcePoints);
  const target = normalization(targetPoints);
  const equations = [];
  const values = [];
  for (let index = 0; index < sourcePoints.length; index += 1) {
    const [x, y] = source.points[index];
    const [X, Y] = target.points[index];
    equations.push([x, y, 1, 0, 0, 0, -x * X, -y * X]);
    values.push(X);
    equations.push([0, 0, 0, x, y, 1, -x * Y, -y * Y]);
    values.push(Y);
  }
  const h = equations.length === 8 ? solveLinearSystem(equations, values) : solveLeastSquares(equations, values);
  const normalized = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
  let result = multiplyMatrices(multiplyMatrices(invert3x3(target.matrix), normalized), source.matrix);
  const divisor = Math.abs(result[2][2]) > EPSILON ? result[2][2] : Math.hypot(...result.flat());
  result = result.map((row) => row.map((value) => value / divisor));
  return result;
}

function signedPolygonArea(points) {
  return points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0) / 2;
}

function isConvex(points) {
  let sign = 0;
  for (let index = 0; index < points.length; index += 1) {
    const a = points[index];
    const b = points[(index + 1) % points.length];
    const c = points[(index + 2) % points.length];
    const cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
    if (Math.abs(cross) < EPSILON) continue;
    const current = Math.sign(cross);
    if (sign && sign !== current) return false;
    sign = current;
  }
  return Boolean(sign);
}

export function analyzeImageFootprint(matrix, imageWidth, imageHeight) {
  if (!(imageWidth > 0 && imageHeight > 0)) throw new Error("Image dimensions must be positive.");
  const imageCorners = [[0, 0], [imageWidth, 0], [imageWidth, imageHeight], [0, imageHeight]];
  const denominators = imageCorners.map(([x, y]) => matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]);
  if (denominators.some((value) => !Number.isFinite(value) || Math.abs(value) < EPSILON)
      || denominators.some((value) => Math.sign(value) !== Math.sign(denominators[0]))) {
    throw new Error("The transform crosses the projective horizon inside the image.");
  }
  const cornersMercator = imageCorners.map((point) => applyHomography(matrix, point));
  if (!isConvex(cornersMercator) || Math.abs(signedPolygonArea(cornersMercator)) < 1e-4) {
    throw new Error("The transformed image footprint is folded or degenerate; check point pairing.");
  }
  const xs = cornersMercator.map((point) => point[0]);
  const ys = cornersMercator.map((point) => point[1]);
  return {
    imageCorners,
    cornersMercator,
    cornersLonLat: cornersMercator.map(([x, y]) => mercatorToLonLat(x, y)),
    boundsMercator: {
      minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys),
    },
    areaSquareMetres: Math.abs(signedPolygonArea(cornersMercator)),
  };
}

export function solveRegistration(controlPoints, imageWidth, imageHeight) {
  if (!Array.isArray(controlPoints) || controlPoints.length < 4) {
    throw new Error("At least four complete image/map control-point pairs are required.");
  }
  const imagePoints = controlPoints.map((point) => [Number(point.image.x), Number(point.image.y)]);
  const mapPoints = controlPoints.map((point) => lonLatToMercator(
    Number(point.geographic.longitude), Number(point.geographic.latitude),
  ));
  const matrix = computeHomography(imagePoints, mapPoints);
  const inverseMatrix = invert3x3(matrix);
  const residualsMetres = imagePoints.map((point, index) => {
    const estimated = applyHomography(matrix, point);
    return projectedGroundDistanceMetres(estimated, mapPoints[index]);
  });
  const rmseMetres = Math.sqrt(residualsMetres.reduce((sum, value) => sum + value ** 2, 0) / residualsMetres.length);
  const footprint = analyzeImageFootprint(matrix, imageWidth, imageHeight);
  return {
    type: "projective_homography",
    sourceCrs: "image_pixel",
    targetCrs: "EPSG:3857",
    matrix,
    inverseMatrix,
    residualsMetres,
    rmseMetres,
    maxResidualMetres: Math.max(...residualsMetres),
    distanceMeasurement: "spherical_geodesic_ground_metres",
    footprint,
  };
}

export function planNorthUpRaster(matrix, imageWidth, imageHeight, maxDimension = 2048) {
  const footprint = analyzeImageFootprint(matrix, imageWidth, imageHeight);
  const { minX, minY, maxX, maxY } = footprint.boundsMercator;
  const widthMetres = maxX - minX;
  const heightMetres = maxY - minY;
  if (!(maxDimension >= 64 && maxDimension <= 8192)) {
    throw new Error("Maximum output dimension must be between 64 and 8192 pixels.");
  }
  let width;
  let height;
  if (widthMetres >= heightMetres) {
    width = Math.round(maxDimension);
    height = Math.max(1, Math.round(maxDimension * heightMetres / widthMetres));
  } else {
    height = Math.round(maxDimension);
    width = Math.max(1, Math.round(maxDimension * widthMetres / heightMetres));
  }
  const [west, south] = mercatorToLonLat(minX, minY);
  const [east, north] = mercatorToLonLat(maxX, maxY);
  return {
    width,
    height,
    maxDimension,
    boundsMercator: { minX, minY, maxX, maxY },
    boundsWgs84: { west, south, east, north },
    pixelSizeMetres: { x: widthMetres / width, y: heightMetres / height },
    footprint,
  };
}

export function initialBearing(fromLonLat, toLonLat) {
  const radians = (value) => value * Math.PI / 180;
  const [lon1, lat1] = fromLonLat.map(radians);
  const [lon2, lat2] = toLonLat.map(radians);
  const deltaLon = lon2 - lon1;
  const y = Math.sin(deltaLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2)
    - Math.sin(lat1) * Math.cos(lat2) * Math.cos(deltaLon);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

export function destinationPoint(originLonLat, bearingDegrees, distanceMetres) {
  const radius = 6371008.8;
  const [longitude, latitude] = originLonLat;
  const phi1 = latitude * Math.PI / 180;
  const lambda1 = longitude * Math.PI / 180;
  const theta = bearingDegrees * Math.PI / 180;
  const delta = distanceMetres / radius;
  const phi2 = Math.asin(Math.sin(phi1) * Math.cos(delta)
    + Math.cos(phi1) * Math.sin(delta) * Math.cos(theta));
  const lambda2 = lambda1 + Math.atan2(
    Math.sin(theta) * Math.sin(delta) * Math.cos(phi1),
    Math.cos(delta) - Math.sin(phi1) * Math.sin(phi2),
  );
  return [((lambda2 * 180 / Math.PI + 540) % 360) - 180, phi2 * 180 / Math.PI];
}

function localMetresPerPixel(matrix, [x, y]) {
  const center = applyHomography(matrix, [x, y]);
  const horizontal = applyHomography(matrix, [x + 1, y]);
  const vertical = applyHomography(matrix, [x, y + 1]);
  return Math.sqrt((projectedGroundDistanceMetres(center, horizontal) ** 2
    + projectedGroundDistanceMetres(center, vertical) ** 2) / 2);
}

export function orientationFromImageSegment({
  matrix,
  endpointA,
  endpointB,
  transformRmseMetres = 0,
  groundControlUncertaintyMetres = 0,
  endpointClickUncertaintyPixels = 1,
  directionality = "bidirectional",
}) {
  if (!["forward", "reverse", "bidirectional"].includes(directionality)) {
    throw new Error("Directionality must be forward, reverse, or bidirectional.");
  }
  const projectedA = applyHomography(matrix, endpointA);
  const projectedB = applyHomography(matrix, endpointB);
  const lonLatA = mercatorToLonLat(...projectedA);
  const lonLatB = mercatorToLonLat(...projectedB);
  const lengthMetres = greatCircleDistanceMetres(lonLatA, lonLatB);
  if (lengthMetres < 0.01) throw new Error("Straight-component endpoints are too close together.");
  const forwardBearing = initialBearing(lonLatA, lonLatB);
  const reverseBearing = initialBearing(lonLatB, lonLatA);
  const baseSigma = Math.hypot(transformRmseMetres, groundControlUncertaintyMetres);
  const sigmaA = Math.hypot(baseSigma, localMetresPerPixel(matrix, endpointA) * endpointClickUncertaintyPixels);
  const sigmaB = Math.hypot(baseSigma, localMetresPerPixel(matrix, endpointB) * endpointClickUncertaintyPixels);
  const uncertaintyDegrees = Math.min(180, Math.atan2(Math.hypot(sigmaA, sigmaB), lengthMetres) * 180 / Math.PI);
  const midpointLonLat = geographicMidpoint(lonLatA, lonLatB);
  const originUncertaintyMetres = Math.max(sigmaA, sigmaB);
  return {
    endpointA: { image: { x: endpointA[0], y: endpointA[1] }, longitude: lonLatA[0], latitude: lonLatA[1] },
    endpointB: { image: { x: endpointB[0], y: endpointB[1] }, longitude: lonLatB[0], latitude: lonLatB[1] },
    midpoint: { longitude: midpointLonLat[0], latitude: midpointLonLat[1] },
    lengthMetres,
    forwardBearingTrueDegrees: forwardBearing,
    reverseBearingTrueDegrees: reverseBearing,
    azimuthTrueDegrees: directionality === "reverse" ? reverseBearing : forwardBearing,
    azimuthUncertaintyDegrees: uncertaintyDegrees,
    originUncertaintyMetres,
    directionality,
    uncertaintyMethod: "propagated_registration_ground_control_and_endpoint_click_error",
    distanceMeasurement: "spherical_geodesic_ground_metres",
    uncertaintyInputs: {
      transformRmseMetres,
      groundControlUncertaintyMetres,
      endpointClickUncertaintyPixels,
      endpointSigmaMetres: { a: sigmaA, b: sigmaB },
    },
  };
}
