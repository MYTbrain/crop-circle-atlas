/** Integration helpers for connecting georef.html to the existing alignment lab. */

export function registrationLabUrl(formationId, baseUrl = "georef.html") {
  const url = new URL(baseUrl, window.location.href);
  if (formationId) url.searchParams.set("formation_id", formationId);
  return url.href;
}

export function openRegistrationLab(formationId, { target = "crop-circle-georef" } = {}) {
  const lab = window.open(registrationLabUrl(formationId), target);
  if (!lab) throw new Error("The image registration window was blocked by the browser.");
  return lab;
}

export function applyOrientationToAlignmentLab(observation, root = document) {
  if (!observation || !Number.isFinite(Number(observation.azimuth_true_deg))) {
    throw new Error("Orientation observation is missing a finite true-north azimuth.");
  }
  if (!["forward", "bidirectional"].includes(observation.directionality)) {
    throw new Error("Qualified orientation directionality must be forward or bidirectional.");
  }
  const selectedFormationId = root.defaultView?.selectedFormationId;
  if (!selectedFormationId || observation.formation_id !== selectedFormationId) {
    throw new Error("Registered orientation does not match the currently selected formation.");
  }
  const bearing = root.getElementById("bearing");
  const bearingUncertainty = root.getElementById("bearingUncertainty");
  const bidirectional = root.getElementById("bidirectional");
  const range = root.getElementById("range");
  const corridor = root.getElementById("corridor");
  if (!bearing || !bidirectional) throw new Error("Alignment-lab bearing controls were not found.");
  bearing.value = String(Number(observation.azimuth_true_deg));
  if (bearingUncertainty && Number.isFinite(Number(observation.azimuth_uncertainty_deg))) {
    bearingUncertainty.value = String(Number(observation.azimuth_uncertainty_deg));
  }
  bidirectional.checked = observation.directionality === "bidirectional";
  if (range && Number.isFinite(Number(observation.max_range_km))) range.value = String(Number(observation.max_range_km));
  if (corridor && Number.isFinite(Number(observation.corridor_km))) corridor.value = String(Number(observation.corridor_km));
  for (const control of [bearing, bearingUncertainty, bidirectional, range, corridor].filter(Boolean)) {
    control.dispatchEvent(new Event("change", { bubbles: true }));
  }
  root.dispatchEvent(new CustomEvent("crop-circle-atlas:orientation-applied", { detail: observation }));
  return observation;
}

export function installOrientationBridge({ root = document, onOrientation, onError } = {}) {
  const handler = (event) => {
    if (event.origin !== window.location.origin || event.data?.type !== "crop-circle-atlas:orientation-ready") return;
    const observation = event.data.orientation;
    try {
      applyOrientationToAlignmentLab(observation, root);
      if (onOrientation) onOrientation(observation, event.data.registration);
    } catch (error) {
      if (onError) onError(error, observation);
    }
  };
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
}
