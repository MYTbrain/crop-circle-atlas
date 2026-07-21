const EARTH_RADIUS_KM = 6371.0088;
const radians = (value) => value * Math.PI / 180;
const degrees = (value) => value * 180 / Math.PI;

export function normalizeBearing(value) {
  return ((Number(value) % 360) + 360) % 360;
}

export function signedAngularDifference(a, b) {
  return ((Number(a) - Number(b) + 540) % 360) - 180;
}

export function angularDifference(a, b) {
  return Math.abs(signedAngularDifference(a, b));
}

export function destination([latitude, longitude], bearing, distanceKm) {
  const phi1 = radians(latitude);
  const lambda1 = radians(longitude);
  const theta = radians(normalizeBearing(bearing));
  const delta = Number(distanceKm) / EARTH_RADIUS_KM;
  const phi2 = Math.asin(
    Math.sin(phi1) * Math.cos(delta)
      + Math.cos(phi1) * Math.sin(delta) * Math.cos(theta),
  );
  const lambda2 = lambda1 + Math.atan2(
    Math.sin(theta) * Math.sin(delta) * Math.cos(phi1),
    Math.cos(delta) - Math.sin(phi1) * Math.sin(phi2),
  );
  return [degrees(phi2), ((degrees(lambda2) + 540) % 360) - 180];
}

export function distanceBearing(origin, target) {
  const [phi1, lambda1, phi2, lambda2] = [...origin, ...target].map(radians);
  const deltaPhi = phi2 - phi1;
  const deltaLambda = lambda2 - lambda1;
  const h = Math.sin(deltaPhi / 2) ** 2
    + Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) ** 2;
  const distanceKm = EARTH_RADIUS_KM * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
  const theta = Math.atan2(
    Math.sin(deltaLambda) * Math.cos(phi2),
    Math.cos(phi1) * Math.sin(phi2)
      - Math.sin(phi1) * Math.cos(phi2) * Math.cos(deltaLambda),
  );
  return [distanceKm, normalizeBearing(degrees(theta))];
}

export function crossAlongTrack(origin, target, rayBearing) {
  const [distanceKm, targetBearing] = distanceBearing(origin, target);
  const delta = distanceKm / EARTH_RADIUS_KM;
  const angle = radians(signedAngularDifference(targetBearing, rayBearing));
  const crossTrackKm = Math.asin(
    Math.max(-1, Math.min(1, Math.sin(delta) * Math.sin(angle))),
  ) * EARTH_RADIUS_KM;
  const alongTrackKm = Math.atan2(
    Math.sin(delta) * Math.cos(angle),
    Math.cos(delta),
  ) * EARTH_RADIUS_KM;
  return { crossTrackKm, alongTrackKm, targetBearing, distanceKm };
}

export function bearingLateralUncertainty(distanceKm, uncertaintyDegrees) {
  const delta = Number(distanceKm) / EARTH_RADIUS_KM;
  const theta = radians(Number(uncertaintyDegrees));
  return Math.abs(Math.asin(
    Math.max(-1, Math.min(1, Math.sin(delta) * Math.sin(theta))),
  ) * EARTH_RADIUS_KM);
}
