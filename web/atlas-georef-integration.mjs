import {
  installOrientationBridge,
  openRegistrationLab,
} from "./georef-atlas-adapter.mjs";

const openButton = document.getElementById("openGeoref");

function openForFormation(formationId) {
  try {
    if (!formationId) throw new Error("Select a formation before opening the registration lab.");
    return openRegistrationLab(formationId);
  } catch (error) {
    const summary = document.getElementById("hitSummary");
    if (summary) summary.textContent = error.message;
    return null;
  }
}

window.openGeorefForFormation = openForFormation;
openButton?.addEventListener("click", () => openForFormation(window.selectedFormationId));

installOrientationBridge({
  onOrientation(observation) {
    if (Number.isFinite(Number(observation.origin_latitude)) && Number.isFinite(Number(observation.origin_longitude))) {
      window.registeredRayOrigin = [Number(observation.origin_latitude), Number(observation.origin_longitude)];
      window.registeredRayOriginUncertaintyKm = Number(observation.origin_uncertainty_m || 0) / 1000;
      window.registeredRayAzimuthUncertaintyDeg = Number(observation.azimuth_uncertainty_deg);
      window.registeredRayFormationId = observation.formation_id;
    }
    const summary = document.getElementById("hitSummary");
    if (summary) {
      summary.textContent = `Imported registered bearing ${Number(observation.azimuth_true_deg).toFixed(2)}° true ± ${Number(observation.azimuth_uncertainty_deg).toFixed(2)}°. Review it, then draw the ray.`;
    }
  },
  onError(error) {
    const summary = document.getElementById("hitSummary");
    if (summary) summary.textContent = error.message;
  },
});
