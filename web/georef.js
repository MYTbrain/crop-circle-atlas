import {
  REGISTRATION_SCHEMA,
  applyHomography,
  destinationPoint,
  orientationFromImageSegment,
  planNorthUpRaster,
  solveRegistration,
} from "./georef-core.mjs";

const $ = (id) => document.getElementById(id);
const PUBLIC_RIGHTS = new Set(["public_domain", "cc0", "cc_by", "cc_by_sa", "licensed", "permission_granted", "owner_supplied_publication_authorized"]);
const LICENSE_RIGHTS = new Set(["cc0", "cc_by", "cc_by_sa", "licensed"]);
const HOLDER_REQUIRED_RIGHTS = new Set(["cc_by", "cc_by_sa", "licensed", "permission_granted", "owner_supplied_publication_authorized"]);
const MAX_CONTROL_POINTS = 12;
const state = {
  image: null,
  imageFile: null,
  imageHash: "",
  previewScale: 1,
  controlPoints: [],
  pendingImagePoint: null,
  transform: null,
  componentMode: false,
  componentEndpoints: [],
  orientation: null,
  raster: null,
  importedMetadata: null,
  catalog: [],
};

const canvas = $("imageCanvas");
const canvasContext = canvas.getContext("2d");

function normalizeRightsStatus(status, license = "") {
  if (status !== "open_license") return status || "local_analysis_only";
  const normalizedLicense = license.toLowerCase();
  if (normalizedLicense.includes("cc0")) return "cc0";
  if (normalizedLicense.includes("by-sa") || normalizedLicense.includes("by sa")) return "cc_by_sa";
  if (normalizedLicense.includes("cc by")) return "cc_by";
  return "licensed";
}

function rightsAssessment() {
  const status = $("rightsStatus").value;
  if (!PUBLIC_RIGHTS.has(status)) return { allowed: false, reasons: ["rights status is not publication-authorized"] };
  const reasons = [];
  if (!$("rightsProof").value.trim()) reasons.push("license or permission proof is missing");
  if (LICENSE_RIGHTS.has(status) && !$("license").value.trim()) reasons.push("license identifier is missing");
  if (HOLDER_REQUIRED_RIGHTS.has(status) && !$("rightsHolder").value.trim()) reasons.push("rights holder is missing");
  return { allowed: reasons.length === 0, reasons };
}

if (!globalThis.L) {
  $("registrationStatus").textContent = "The map library could not load. Check the network connection and reload.";
  $("registrationStatus").classList.add("error");
  throw new Error("Leaflet failed to load");
}

const map = L.map("georefMap", { zoomControl: false }).setView([38, -96], 4);
L.control.zoom({ position: "topright" }).addTo(map);
const streets = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 20,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);
const imagery = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 20,
  attribution: "Tiles &copy; Esri and imagery partners",
});
L.control.layers({ "Street map": streets, "Satellite imagery": imagery }, {}, { position: "topright" }).addTo(map);
const controlMarkerLayer = L.layerGroup().addTo(map);
const componentLayer = L.layerGroup().addTo(map);

function markerIcon(label, component = false) {
  return L.divIcon({
    className: `control-marker${component ? " component-marker" : ""}`,
    html: label,
    iconSize: [26, 26],
  });
}

function safeSlug(value, fallback = "crop_circle_overlay") {
  const slug = String(value || "").trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  return slug || fallback;
}

function xmlEscape(value) {
  return String(value ?? "").replace(/[<>&"']/g, (character) => ({
    "<": "&lt;", ">": "&gt;", "&": "&amp;", "\"": "&quot;", "'": "&apos;",
  }[character]));
}

function csvEscape(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function setStatus(element, message, type = "") {
  element.textContent = message;
  element.classList.remove("error", "success");
  if (type) element.classList.add(type);
}

function revokeRaster() {
  if (state.raster?.url) URL.revokeObjectURL(state.raster.url);
  if (state.raster?.overlay) state.raster.overlay.remove();
  state.raster = null;
  $("downloadPng").disabled = true;
  $("downloadKml").disabled = true;
}

function invalidateTransform() {
  state.transform = null;
  state.componentMode = false;
  state.componentEndpoints = [];
  state.orientation = null;
  componentLayer.clearLayers();
  revokeRaster();
  $("generateRaster").disabled = true;
  $("downloadMetadata").disabled = true;
  $("markComponent").disabled = true;
  $("resetComponent").disabled = true;
  $("downloadOrientationCsv").disabled = true;
  $("downloadOrientationKml").disabled = true;
  $("orientationResult").textContent = "No component measured.";
}

function refreshButtons() {
  const hasAnyPoint = Boolean(state.pendingImagePoint || state.controlPoints.length);
  $("undoPoint").disabled = !hasAnyPoint;
  $("resetPoints").disabled = !hasAnyPoint;
  $("solveTransform").disabled = !(state.image && state.controlPoints.length >= 4 && !state.pendingImagePoint);
  $("useCoordinates").disabled = !state.pendingImagePoint;
}

function redrawCanvas() {
  if (!state.image) return;
  canvasContext.clearRect(0, 0, canvas.width, canvas.height);
  canvasContext.drawImage(state.image, 0, 0, canvas.width, canvas.height);
  const drawPoint = (point, label, color) => {
    const x = point[0] * state.previewScale;
    const y = point[1] * state.previewScale;
    canvasContext.save();
    canvasContext.beginPath();
    canvasContext.arc(x, y, 10, 0, Math.PI * 2);
    canvasContext.fillStyle = color;
    canvasContext.fill();
    canvasContext.lineWidth = 2;
    canvasContext.strokeStyle = "white";
    canvasContext.stroke();
    canvasContext.fillStyle = "#08100f";
    canvasContext.font = "bold 12px system-ui";
    canvasContext.textAlign = "center";
    canvasContext.textBaseline = "middle";
    canvasContext.fillText(label, x, y);
    canvasContext.restore();
  };
  state.controlPoints.forEach((point, index) => drawPoint([point.image.x, point.image.y], String(index + 1), "#59d9c5"));
  if (state.pendingImagePoint) drawPoint(state.pendingImagePoint, String(state.controlPoints.length + 1), "#f5ac58");
  if (state.componentEndpoints.length) {
    if (state.componentEndpoints.length === 2) {
      canvasContext.save();
      canvasContext.beginPath();
      canvasContext.moveTo(state.componentEndpoints[0][0] * state.previewScale, state.componentEndpoints[0][1] * state.previewScale);
      canvasContext.lineTo(state.componentEndpoints[1][0] * state.previewScale, state.componentEndpoints[1][1] * state.previewScale);
      canvasContext.strokeStyle = "#ff8f79";
      canvasContext.lineWidth = 4;
      canvasContext.stroke();
      canvasContext.restore();
    }
    state.componentEndpoints.forEach((point, index) => drawPoint(point, index ? "B" : "A", "#f5ac58"));
  }
}

function redrawControlPoints() {
  controlMarkerLayer.clearLayers();
  state.controlPoints.forEach((point, index) => {
    L.marker([point.geographic.latitude, point.geographic.longitude], { icon: markerIcon(String(index + 1)) })
      .bindTooltip(`Control point ${index + 1}`)
      .addTo(controlMarkerLayer);
  });
  const list = $("controlPointList");
  list.replaceChildren();
  if (!state.controlPoints.length && !state.pendingImagePoint) {
    const item = document.createElement("li");
    item.textContent = "No pairs recorded.";
    list.append(item);
  }
  state.controlPoints.forEach((point, index) => {
    const item = document.createElement("li");
    item.textContent = `${index + 1}: image ${point.image.x.toFixed(1)}, ${point.image.y.toFixed(1)} px -> ${point.geographic.latitude.toFixed(7)}, ${point.geographic.longitude.toFixed(7)}`;
    list.append(item);
  });
  if (state.pendingImagePoint) {
    const item = document.createElement("li");
    item.className = "pending";
    item.textContent = `${state.controlPoints.length + 1}: image ${state.pendingImagePoint[0].toFixed(1)}, ${state.pendingImagePoint[1].toFixed(1)} px -> awaiting map point`;
    list.append(item);
  }
  refreshButtons();
}

function canvasPoint(event) {
  const bounds = canvas.getBoundingClientRect();
  return [
    Math.max(0, Math.min(state.image.width, (event.clientX - bounds.left) / bounds.width * state.image.width)),
    Math.max(0, Math.min(state.image.height, (event.clientY - bounds.top) / bounds.height * state.image.height)),
  ];
}

canvas.addEventListener("click", (event) => {
  if (!state.image) return;
  const point = canvasPoint(event);
  if (state.componentMode) {
    if (state.componentEndpoints.length >= 2) return;
    state.componentEndpoints.push(point);
    redrawCanvas();
    if (state.componentEndpoints.length === 1) {
      $("imagePrompt").textContent = "Endpoint A set. Click endpoint B.";
      $("orientationResult").textContent = "Endpoint A set; awaiting endpoint B.";
    } else {
      state.componentMode = false;
      $("markComponent").textContent = "Remark endpoints";
      updateOrientation();
    }
    return;
  }
  if (state.controlPoints.length >= MAX_CONTROL_POINTS) {
    setStatus($("registrationStatus"), `${MAX_CONTROL_POINTS} pairs already exist. Solve, undo, or reset before changing them.`);
    return;
  }
  if (state.pendingImagePoint) {
    setStatus($("registrationStatus"), "Finish the pending pair on the map before selecting another image point.", "error");
    return;
  }
  invalidateTransform();
  state.pendingImagePoint = point;
  $("imagePrompt").textContent = `Image point ${state.controlPoints.length + 1} set. Click its matching map landmark.`;
  setStatus($("registrationStatus"), `Image point ${state.controlPoints.length + 1} set; awaiting the matching map point.`);
  redrawCanvas();
  redrawControlPoints();
});

function completePendingMapPoint(latitude, longitude) {
  if (!state.pendingImagePoint) return;
  if (!(Number.isFinite(latitude) && latitude >= -85.051128 && latitude <= 85.051128
      && Number.isFinite(longitude) && longitude >= -180 && longitude <= 180)) {
    setStatus($("registrationStatus"), "Enter valid WGS84 latitude and longitude values.", "error");
    return;
  }
  const index = state.controlPoints.length + 1;
  state.controlPoints.push({
    id: `cp${index}`,
    image: { x: state.pendingImagePoint[0], y: state.pendingImagePoint[1] },
    geographic: { latitude, longitude, crs: "EPSG:4326" },
  });
  state.pendingImagePoint = null;
  $("manualLat").value = "";
  $("manualLon").value = "";
  $("imagePrompt").textContent = state.controlPoints.length < 4
    ? `Pair ${index} complete. Click image landmark ${index + 1}.`
    : `${state.controlPoints.length} pairs complete. Solve now or add another landmark.`;
  setStatus($("registrationStatus"), state.controlPoints.length < 4
    ? `${state.controlPoints.length} of 4 control-point pairs recorded.`
    : `${state.controlPoints.length} pairs recorded. Ready to solve or add more.`, state.controlPoints.length >= 4 ? "success" : "");
  redrawCanvas();
  redrawControlPoints();
}

map.on("click", (event) => completePendingMapPoint(event.latlng.lat, event.latlng.lng));
$("useCoordinates").addEventListener("click", () => completePendingMapPoint(Number($("manualLat").value), Number($("manualLon").value)));

$("undoPoint").addEventListener("click", () => {
  invalidateTransform();
  if (state.pendingImagePoint) state.pendingImagePoint = null;
  else state.controlPoints.pop();
  setStatus($("registrationStatus"), `${state.controlPoints.length} of 4 control-point pairs recorded.`);
  $("imagePrompt").textContent = `Click image landmark ${state.controlPoints.length + 1}.`;
  redrawCanvas();
  redrawControlPoints();
});

$("resetPoints").addEventListener("click", () => {
  invalidateTransform();
  state.controlPoints = [];
  state.pendingImagePoint = null;
  setStatus($("registrationStatus"), "At least four complete pairs are required.");
  $("imagePrompt").textContent = "Click image landmark 1.";
  redrawCanvas();
  redrawControlPoints();
});

async function sha256(file) {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function loadBrowserImage(file) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => { URL.revokeObjectURL(objectUrl); resolve(image); };
    image.onerror = () => { URL.revokeObjectURL(objectUrl); reject(new Error("The browser could not decode this image format.")); };
    image.src = objectUrl;
  });
}

$("imageFile").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    setStatus($("imageStatus"), "Reading the image locally and calculating its SHA-256 digest...");
    const [image, hash] = await Promise.all([loadBrowserImage(file), sha256(file)]);
    state.image = image;
    state.imageFile = file;
    state.imageHash = hash;
    state.previewScale = Math.min(1, 1800 / image.width, 1400 / image.height);
    canvas.width = Math.max(1, Math.round(image.width * state.previewScale));
    canvas.height = Math.max(1, Math.round(image.height * state.previewScale));
    canvas.style.display = "block";
    $("canvasEmpty").style.display = "none";
    if (!$("assetId").value) {
      const prefix = safeSlug($("formationId").value, "image");
      $("assetId").value = `${prefix}-${hash.slice(0, 12)}`;
    }
    invalidateTransform();
    setStatus($("imageStatus"), `${file.name} | ${image.width} x ${image.height} px | SHA-256 ${hash.slice(0, 16)}...`, "success");
    if (state.importedMetadata) restoreImportedControlPoints();
    redrawCanvas();
    redrawControlPoints();
  } catch (error) {
    setStatus($("imageStatus"), error.message, "error");
  }
});

function restoreImportedControlPoints() {
  const metadata = state.importedMetadata;
  if (!metadata || !state.image) return;
  const source = metadata.source_image || metadata.asset || {};
  if (source.width_px && Number(source.width_px) !== state.image.width
      || source.height_px && Number(source.height_px) !== state.image.height) {
    setStatus($("imageStatus"), "The selected image dimensions do not match the imported registration.", "error");
    return;
  }
  if (source.sha256 && state.imageHash && source.sha256.toLowerCase() !== state.imageHash.toLowerCase()) {
    setStatus($("imageStatus"), "The selected image SHA-256 does not match the imported registration. Points were not restored.", "error");
    return;
  }
  state.controlPoints = metadata.control_points.map((point, index) => ({
    id: point.id || `cp${index + 1}`,
    image: { x: Number(point.image.x), y: Number(point.image.y) },
    geographic: {
      latitude: Number(point.geographic.latitude),
      longitude: Number(point.geographic.longitude),
      crs: "EPSG:4326",
    },
  }));
  redrawCanvas();
  redrawControlPoints();
  setStatus($("registrationStatus"), `Imported ${state.controlPoints.length} control-point pairs. Solve to recompute and validate the transform.`, "success");
  if (metadata.straight_component?.endpoint_a?.image && metadata.straight_component?.endpoint_b?.image) {
    state.componentEndpoints = [
      [metadata.straight_component.endpoint_a.image.x, metadata.straight_component.endpoint_a.image.y],
      [metadata.straight_component.endpoint_b.image.x, metadata.straight_component.endpoint_b.image.y],
    ];
  }
}

$("registrationFile").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const metadata = JSON.parse(await file.text());
    if (metadata.schema_version !== REGISTRATION_SCHEMA || !Array.isArray(metadata.control_points) || metadata.control_points.length < 4) {
      throw new Error("This is not a supported v1 registration with four or more control points.");
    }
    state.importedMetadata = metadata;
    $("formationId").value = metadata.formation_id || "";
    $("assetId").value = metadata.asset?.asset_id || "";
    $("sourceUrl").value = metadata.asset?.source_url || "";
    $("rightsStatus").value = normalizeRightsStatus(metadata.asset?.rights?.status, metadata.asset?.rights?.license);
    $("rightsHolder").value = metadata.asset?.rights?.holder || "";
    $("license").value = metadata.asset?.rights?.license || "";
    $("rightsProof").value = metadata.asset?.rights?.proof || "";
    $("reviewer").value = metadata.review?.reviewer || "";
    updatePublicationNotice();
    if (state.image) restoreImportedControlPoints();
    else setStatus($("imageStatus"), "Registration metadata loaded. Select its original local image to verify the hash and restore points.");
  } catch (error) {
    setStatus($("imageStatus"), `Could not restore registration: ${error.message}`, "error");
  }
});

function solveCurrentTransform() {
  try {
    state.transform = solveRegistration(state.controlPoints, state.image.width, state.image.height);
    const footprint = state.transform.footprint.boundsMercator;
    const width = footprint.maxX - footprint.minX;
    const height = footprint.maxY - footprint.minY;
    setStatus($("registrationStatus"),
      `Projective transform solved from ${state.controlPoints.length} pairs. Ground-distance fit RMSE ${state.transform.rmseMetres.toFixed(4)} m; projected EPSG:3857 footprint ${width.toFixed(1)} x ${height.toFixed(1)} m. Visually review independent landmarks against the basemap.`, "success");
    $("generateRaster").disabled = false;
    $("downloadMetadata").disabled = false;
    $("markComponent").disabled = false;
    $("resetComponent").disabled = !state.componentEndpoints.length;
    if (state.componentEndpoints.length === 2) updateOrientation();
    return true;
  } catch (error) {
    state.transform = null;
    setStatus($("registrationStatus"), `Registration failed: ${error.message}`, "error");
    return false;
  }
}

$("solveTransform").addEventListener("click", solveCurrentTransform);

function updatePublicationNotice() {
  const assessment = rightsAssessment();
  const notice = $("publicationNotice");
  if (assessment.allowed) {
    notice.textContent = "The recorded status and proof fields permit a publication export, subject to final human verification of the cited proof.";
  } else if (PUBLIC_RIGHTS.has($("rightsStatus").value)) {
    notice.textContent = `Publication is blocked: ${assessment.reasons.join("; ")}.`;
  } else {
    notice.textContent = "Current rights status permits local analysis only. Do not publish the image or its derivative overlay.";
  }
}
["rightsStatus", "rightsHolder", "license", "rightsProof"].forEach((id) => $(id).addEventListener(id === "rightsStatus" ? "change" : "input", updatePublicationNotice));

async function warpNorthUp() {
  if (!state.transform && !solveCurrentTransform()) return;
  revokeRaster();
  const maxDimension = Number($("maxDimension").value);
  let plan;
  try {
    plan = planNorthUpRaster(state.transform.matrix, state.image.width, state.image.height, maxDimension);
  } catch (error) {
    setStatus($("rasterStatus"), error.message, "error");
    return;
  }
  $("generateRaster").disabled = true;
  setStatus($("rasterStatus"), `Warping ${plan.width} x ${plan.height} pixels locally...`);
  await new Promise((resolve) => requestAnimationFrame(resolve));

  try {
    const sourceScale = Math.min(1, 4096 / Math.max(state.image.width, state.image.height));
    const sourceCanvas = document.createElement("canvas");
    sourceCanvas.width = Math.max(1, Math.round(state.image.width * sourceScale));
    sourceCanvas.height = Math.max(1, Math.round(state.image.height * sourceScale));
    const sourceContext = sourceCanvas.getContext("2d", { willReadFrequently: true });
    sourceContext.drawImage(state.image, 0, 0, sourceCanvas.width, sourceCanvas.height);
    const source = sourceContext.getImageData(0, 0, sourceCanvas.width, sourceCanvas.height);
    const outputCanvas = document.createElement("canvas");
    outputCanvas.width = plan.width;
    outputCanvas.height = plan.height;
    const outputContext = outputCanvas.getContext("2d");
    const output = outputContext.createImageData(plan.width, plan.height);
    const { minX, minY, maxX, maxY } = plan.boundsMercator;
    const inverse = state.transform.inverseMatrix;
    const [a, b, c, d, e, f, g, h, i] = inverse.flat();
    const sourceWidth = sourceCanvas.width;
    const sourceHeight = sourceCanvas.height;
    let row = 0;

    await new Promise((resolve, reject) => {
      const processRows = () => {
        try {
          const stop = Math.min(plan.height, row + 24);
          for (; row < stop; row += 1) {
            const Y = maxY - (row + 0.5) / plan.height * (maxY - minY);
            for (let column = 0; column < plan.width; column += 1) {
              const X = minX + (column + 0.5) / plan.width * (maxX - minX);
              const denominator = g * X + h * Y + i;
              const originalX = ((a * X + b * Y + c) / denominator) * sourceScale;
              const originalY = ((d * X + e * Y + f) / denominator) * sourceScale;
              if (originalX < 0 || originalY < 0 || originalX > sourceWidth - 1 || originalY > sourceHeight - 1) continue;
              const x0 = Math.floor(originalX);
              const y0 = Math.floor(originalY);
              const x1 = Math.min(sourceWidth - 1, x0 + 1);
              const y1 = Math.min(sourceHeight - 1, y0 + 1);
              const dx = originalX - x0;
              const dy = originalY - y0;
              const weights = [(1 - dx) * (1 - dy), dx * (1 - dy), (1 - dx) * dy, dx * dy];
              const indices = [
                (y0 * sourceWidth + x0) * 4, (y0 * sourceWidth + x1) * 4,
                (y1 * sourceWidth + x0) * 4, (y1 * sourceWidth + x1) * 4,
              ];
              const target = (row * plan.width + column) * 4;
              for (let channel = 0; channel < 4; channel += 1) {
                output.data[target + channel] = Math.round(indices.reduce((sum, index, sample) =>
                  sum + source.data[index + channel] * weights[sample], 0));
              }
            }
          }
          setStatus($("rasterStatus"), `Warping locally... ${Math.round(row / plan.height * 100)}%`);
          if (row < plan.height) requestAnimationFrame(processRows);
          else resolve();
        } catch (error) { reject(error); }
      };
      processRows();
    });
    outputContext.putImageData(output, 0, 0);
    const blob = await new Promise((resolve, reject) => outputCanvas.toBlob((value) => value ? resolve(value) : reject(new Error("PNG encoding failed.")), "image/png"));
    const url = URL.createObjectURL(blob);
    const bounds = [[plan.boundsWgs84.south, plan.boundsWgs84.west], [plan.boundsWgs84.north, plan.boundsWgs84.east]];
    const overlay = L.imageOverlay(url, bounds, { opacity: Number($("overlayOpacity").value), interactive: false }).addTo(map);
    map.fitBounds(bounds, { padding: [30, 30] });
    state.raster = { canvas: outputCanvas, blob, url, overlay, plan };
    $("downloadPng").disabled = false;
    $("downloadKml").disabled = false;
    setStatus($("rasterStatus"), `North-up ${plan.width} x ${plan.height} PNG generated locally at ${plan.pixelSizeMetres.x.toFixed(3)} x ${plan.pixelSizeMetres.y.toFixed(3)} projected EPSG:3857 m/pixel.`, "success");
  } catch (error) {
    setStatus($("rasterStatus"), `Raster generation failed: ${error.message}`, "error");
  } finally {
    $("generateRaster").disabled = false;
  }
}

$("generateRaster").addEventListener("click", warpNorthUp);
$("overlayOpacity").addEventListener("input", () => state.raster?.overlay?.setOpacity(Number($("overlayOpacity").value)));

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadText(text, filename, type) {
  downloadBlob(new Blob([text], { type }), filename);
}

function orientationObservation() {
  if (!state.orientation) return null;
  const formationId = $("formationId").value.trim();
  const assetId = $("assetId").value.trim();
  const directionality = state.orientation.directionality === "bidirectional" ? "bidirectional" : "forward";
  return {
    observation_id: `orientation-${safeSlug(formationId, "formation")}-${safeSlug(assetId, state.imageHash.slice(0, 16) || "asset")}`,
    formation_id: formationId,
    assertion_id: "",
    origin_latitude: state.orientation.midpoint.latitude,
    origin_longitude: state.orientation.midpoint.longitude,
    origin_uncertainty_m: state.orientation.originUncertaintyMetres,
    evidence_sha256: state.imageHash,
    evidence_cache_path: "",
    azimuth_true_deg: state.orientation.azimuthTrueDegrees,
    azimuth_uncertainty_deg: state.orientation.azimuthUncertaintyDegrees,
    directionality,
    max_range_km: Number($("rayRange").value),
    corridor_km: Number($("corridorKm").value),
    orientation_method: "landmark_registration",
    origin_coordinate_method: "registered_component_midpoint",
    evidence_url: $("sourceUrl").value.trim(),
    reviewer: $("reviewer").value.trim(),
    reviewed_at: new Date().toISOString(),
    notes: `Ray origin is the registered straight-component midpoint; asset_id=${assetId}; selected_direction=${state.orientation.directionality}; forward=${state.orientation.forwardBearingTrueDegrees.toFixed(6)}; reverse=${state.orientation.reverseBearingTrueDegrees.toFixed(6)}; length_m=${state.orientation.lengthMetres.toFixed(3)}.`,
  };
}

function buildMetadata() {
  if (!state.transform) throw new Error("Solve the registration before exporting metadata.");
  const plan = state.raster?.plan || planNorthUpRaster(
    state.transform.matrix, state.image.width, state.image.height, Number($("maxDimension").value),
  );
  const rightsStatus = $("rightsStatus").value;
  const rights = rightsAssessment();
  const metadata = {
    schema_version: REGISTRATION_SCHEMA,
    registration_id: `${safeSlug($("assetId").value)}-registration-v1`,
    formation_id: $("formationId").value.trim(),
    asset: {
      asset_id: $("assetId").value.trim(),
      source_url: $("sourceUrl").value.trim(),
      original_filename: state.imageFile?.name || "",
      rights: {
        status: rightsStatus,
        holder: $("rightsHolder").value.trim(),
        license: $("license").value.trim(),
        proof: $("rightsProof").value.trim(),
        public_derivative_export_allowed: rights.allowed,
      },
    },
    source_image: {
      sha256: state.imageHash,
      width_px: state.image.width,
      height_px: state.image.height,
      local_path: null,
      pixels_embedded: false,
    },
    control_points: state.controlPoints,
    transform: {
      type: state.transform.type,
      source_crs: state.transform.sourceCrs,
      target_crs: state.transform.targetCrs,
      image_pixel_to_web_mercator: state.transform.matrix,
      web_mercator_to_image_pixel: state.transform.inverseMatrix,
      control_point_residuals_m: state.transform.residualsMetres,
      control_point_rmse_m: state.transform.rmseMetres,
      max_control_point_residual_m: state.transform.maxResidualMetres,
      distance_measurement: state.transform.distanceMeasurement,
      accuracy_note: "A four-point fit is exact by construction. With additional points, residual measures internal fit but is not independent positional accuracy.",
    },
    output: {
      crs: "EPSG:3857",
      width_px: plan.width,
      height_px: plan.height,
      bounds_web_mercator: plan.boundsMercator,
      bounds_wgs84: plan.boundsWgs84,
      pixel_size_m: plan.pixelSizeMetres,
      pixel_size_unit: "EPSG:3857_projected_metre",
      north_up: true,
      transparent_outside_footprint: true,
    },
    straight_component: state.orientation ? {
      endpoint_a: state.orientation.endpointA,
      endpoint_b: state.orientation.endpointB,
      midpoint: state.orientation.midpoint,
      ray_origin: {
        representative_point: "straight_component_midpoint",
        latitude: state.orientation.midpoint.latitude,
        longitude: state.orientation.midpoint.longitude,
        uncertainty_m: state.orientation.originUncertaintyMetres,
      },
      length_m: state.orientation.lengthMetres,
      forward_azimuth_true_deg: state.orientation.forwardBearingTrueDegrees,
      reverse_azimuth_true_deg: state.orientation.reverseBearingTrueDegrees,
      selected_azimuth_true_deg: state.orientation.azimuthTrueDegrees,
      azimuth_uncertainty_deg: state.orientation.azimuthUncertaintyDegrees,
      directionality: state.orientation.directionality,
      uncertainty_method: state.orientation.uncertaintyMethod,
      distance_measurement: state.orientation.distanceMeasurement,
      uncertainty_inputs: state.orientation.uncertaintyInputs,
      ray_range_km: Number($("rayRange").value),
      corridor_km: Number($("corridorKm").value),
    } : null,
    review: {
      reviewer: $("reviewer").value.trim(),
      reviewed_at: new Date().toISOString(),
      visual_basemap_review_required: true,
    },
    privacy: { processing: "local_browser_only", image_uploaded: false },
  };
  return metadata;
}

function buildKml({ overlay = false, orientation = false } = {}) {
  const slug = safeSlug($("assetId").value);
  const rightsStatus = $("rightsStatus").value;
  const rightsHolder = $("rightsHolder").value.trim();
  const license = $("license").value.trim();
  const rightsProof = $("rightsProof").value.trim();
  const sourceUrl = $("sourceUrl").value.trim();
  let overlayXml = "";
  if (overlay) {
    const plan = state.raster?.plan || planNorthUpRaster(state.transform.matrix, state.image.width, state.image.height, Number($("maxDimension").value));
    const bounds = plan.boundsWgs84;
    const attribution = `Rights status: ${rightsStatus}; rights holder/creator: ${rightsHolder || "not supplied"}; license: ${license || "not supplied"}; rights proof: ${rightsProof || "not supplied"}; source: ${sourceUrl || "not supplied"}. A local-analysis export is not publication authorization.`;
    overlayXml = `<GroundOverlay><name>${xmlEscape(slug)} north-up overlay</name><description>${xmlEscape(attribution)}</description><ExtendedData><Data name="rights_status"><value>${xmlEscape(rightsStatus)}</value></Data><Data name="rights_holder"><value>${xmlEscape(rightsHolder)}</value></Data><Data name="license"><value>${xmlEscape(license)}</value></Data><Data name="rights_proof"><value>${xmlEscape(rightsProof)}</value></Data><Data name="source_url"><value>${xmlEscape(sourceUrl)}</value></Data></ExtendedData><Icon><href>${xmlEscape(`${slug}_north_up.png`)}</href></Icon><LatLonBox><north>${bounds.north.toFixed(10)}</north><south>${bounds.south.toFixed(10)}</south><east>${bounds.east.toFixed(10)}</east><west>${bounds.west.toFixed(10)}</west><rotation>0</rotation></LatLonBox></GroundOverlay>`;
  }
  let orientationXml = "";
  if (orientation && state.orientation) {
    const measured = state.orientation;
    const a = measured.endpointA;
    const b = measured.endpointB;
    const origin = [measured.midpoint.longitude, measured.midpoint.latitude];
    const rangeMetres = Number($("rayRange").value) * 1000;
    const rayPoints = measured.directionality === "bidirectional"
      ? [destinationPoint(origin, measured.reverseBearingTrueDegrees, rangeMetres), destinationPoint(origin, measured.forwardBearingTrueDegrees, rangeMetres)]
      : [origin, destinationPoint(origin, measured.azimuthTrueDegrees, rangeMetres)];
    const rayCoordinates = rayPoints.map(([longitude, latitude]) => `${longitude.toFixed(10)},${latitude.toFixed(10)},0`).join(" ");
    orientationXml = `<Folder><name>Measured component and unreviewed experimental projection</name><Placemark><name>Measured straight component</name><LineString><tessellate>1</tessellate><coordinates>${a.longitude.toFixed(10)},${a.latitude.toFixed(10)},0 ${b.longitude.toFixed(10)},${b.latitude.toFixed(10)},0</coordinates></LineString></Placemark><Placemark><name>UNREVIEWED EXPERIMENTAL ${xmlEscape(measured.directionality)} projection ${measured.azimuthTrueDegrees.toFixed(3)} degrees true</name><description>This local registration has not passed the atlas evidence-review gate. Extending the measured component is an exploratory hypothesis with no demonstrated predictive validity.</description><ExtendedData><Data name="qualification_status"><value>unreviewed_local_registration</value></Data><Data name="predictive_validity"><value>none_demonstrated</value></Data><Data name="azimuth_uncertainty_deg"><value>${measured.azimuthUncertaintyDegrees.toFixed(6)}</value></Data><Data name="origin_uncertainty_m"><value>${measured.originUncertaintyMetres.toFixed(6)}</value></Data><Data name="corridor_km"><value>${Number($("corridorKm").value).toFixed(3)}</value></Data></ExtendedData><Style><LineStyle><color>ff55adf6</color><width>3</width></LineStyle></Style><LineString><tessellate>1</tessellate><coordinates>${rayCoordinates}</coordinates></LineString></Placemark></Folder>`;
  }
  return `<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>${xmlEscape(slug)} georeference</name><description>Local image-registration output. Image publication depends on the embedded rights record. Any projection is unreviewed and has no demonstrated predictive validity.</description>${overlayXml}${orientationXml}</Document></kml>\n`;
}

$("downloadPng").addEventListener("click", () => {
  if (state.raster) downloadBlob(state.raster.blob, `${safeSlug($("assetId").value)}_north_up.png`);
});
$("downloadKml").addEventListener("click", () => downloadText(buildKml({ overlay: true, orientation: Boolean(state.orientation) }), `${safeSlug($("assetId").value)}.kml`, "application/vnd.google-earth.kml+xml"));
$("downloadMetadata").addEventListener("click", () => downloadText(`${JSON.stringify(buildMetadata(), null, 2)}\n`, `${safeSlug($("assetId").value)}.registration.json`, "application/json"));

$("markComponent").addEventListener("click", () => {
  if (!state.transform) return;
  state.componentEndpoints = [];
  state.orientation = null;
  state.componentMode = true;
  componentLayer.clearLayers();
  $("imagePrompt").textContent = "Component mode: click endpoint A.";
  $("orientationResult").textContent = "Click endpoint A in the image.";
  $("markComponent").textContent = "Marking...";
  $("resetComponent").disabled = false;
  $("downloadOrientationCsv").disabled = true;
  $("downloadOrientationKml").disabled = true;
  redrawCanvas();
});

$("resetComponent").addEventListener("click", () => {
  state.componentMode = false;
  state.componentEndpoints = [];
  state.orientation = null;
  componentLayer.clearLayers();
  $("orientationResult").textContent = "No component measured.";
  $("imagePrompt").textContent = "Registration solved. Mark a straight component or inspect the overlay.";
  $("markComponent").textContent = "Mark endpoints";
  $("resetComponent").disabled = true;
  $("downloadOrientationCsv").disabled = true;
  $("downloadOrientationKml").disabled = true;
  redrawCanvas();
});

function emitOrientation() {
  const detail = { orientation: orientationObservation(), registration: buildMetadata() };
  window.dispatchEvent(new CustomEvent("crop-circle-atlas:orientation-ready", { detail }));
  try {
    if (window.opener && window.opener !== window) {
      window.opener.postMessage({ type: "crop-circle-atlas:orientation-ready", ...detail }, window.location.origin);
    }
  } catch { /* Standalone operation remains available if opener access is restricted. */ }
}

function updateOrientation() {
  if (!state.transform || state.componentEndpoints.length !== 2) return;
  try {
    state.orientation = orientationFromImageSegment({
      matrix: state.transform.matrix,
      endpointA: state.componentEndpoints[0],
      endpointB: state.componentEndpoints[1],
      transformRmseMetres: state.transform.rmseMetres,
      groundControlUncertaintyMetres: Number($("groundUncertainty").value),
      endpointClickUncertaintyPixels: Number($("clickUncertainty").value),
      directionality: $("directionality").value,
    });
    const result = state.orientation;
    const directionLabel = result.directionality === "bidirectional" ? "both directions" : result.directionality === "forward" ? "A to B" : "B to A";
    $("orientationResult").textContent = `Selected ${result.azimuthTrueDegrees.toFixed(3)} degrees true (${directionLabel}); forward ${result.forwardBearingTrueDegrees.toFixed(3)} degrees, reverse ${result.reverseBearingTrueDegrees.toFixed(3)} degrees; component ${result.lengthMetres.toFixed(2)} m; estimated azimuth uncertainty +/-${result.azimuthUncertaintyDegrees.toFixed(3)} degrees; midpoint-origin uncertainty ${result.originUncertaintyMetres.toFixed(2)} m.`;
    $("imagePrompt").textContent = "Straight component measured in geographic coordinates.";
    $("downloadOrientationCsv").disabled = false;
    $("downloadOrientationKml").disabled = false;
    $("resetComponent").disabled = false;
    componentLayer.clearLayers();
    const a = result.endpointA;
    const b = result.endpointB;
    L.marker([a.latitude, a.longitude], { icon: markerIcon("A", true) }).addTo(componentLayer);
    L.marker([b.latitude, b.longitude], { icon: markerIcon("B", true) }).addTo(componentLayer);
    L.polyline([[a.latitude, a.longitude], [b.latitude, b.longitude]], { color: "#ff8f79", weight: 4 }).addTo(componentLayer);
    emitOrientation();
  } catch (error) {
    $("orientationResult").textContent = `Could not measure component: ${error.message}`;
  }
}

["directionality", "groundUncertainty", "clickUncertainty", "rayRange", "corridorKm"].forEach((id) => {
  $(id).addEventListener("change", updateOrientation);
});

$("downloadOrientationCsv").addEventListener("click", () => {
  const observation = orientationObservation();
  const headers = ["observation_id", "formation_id", "assertion_id", "azimuth_true_deg", "azimuth_uncertainty_deg", "directionality", "max_range_km", "corridor_km", "orientation_method", "evidence_url", "evidence_sha256", "evidence_cache_path", "origin_latitude", "origin_longitude", "origin_uncertainty_m", "origin_coordinate_method", "reviewer", "reviewed_at", "notes"];
  const csv = `${headers.join(",")}\r\n${headers.map((header) => csvEscape(observation[header])).join(",")}\r\n`;
  downloadText(csv, `${safeSlug($("formationId").value, "formation")}_orientation.csv`, "text/csv;charset=utf-8");
});
$("downloadOrientationKml").addEventListener("click", () => downloadText(buildKml({ orientation: true }), `${safeSlug($("formationId").value, "formation")}_orientation.kml`, "application/vnd.google-earth.kml+xml"));

function focusFormation(feature) {
  const [longitude, latitude] = feature.geometry.coordinates;
  map.setView([latitude, longitude], 17);
  $("formationId").value = feature.properties.formation_id || "";
  if (!$("assetId").value && state.imageHash) $("assetId").value = `${safeSlug($("formationId").value, "image")}-${state.imageHash.slice(0, 12)}`;
  L.popup().setLatLng([latitude, longitude]).setContent(`<strong>${xmlEscape(feature.properties.place || feature.properties.formation_id)}</strong><br>Catalog coordinate is approximate; select actual ground landmarks.`).openOn(map);
}

$("findFormation").addEventListener("click", () => {
  const query = $("catalogSearch").value.trim().toLowerCase();
  if (!query || !state.catalog.length) return;
  const match = state.catalog.find((feature) => feature.properties.formation_id?.toLowerCase() === query)
    || state.catalog.find((feature) => `${feature.properties.place} ${feature.properties.region} ${feature.properties.country}`.toLowerCase().includes(query));
  if (match) focusFormation(match);
  else setStatus($("registrationStatus"), "No mapped catalog formation matched that search.", "error");
});

fetch("data/formations.geojson")
  .then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
  .then((collection) => {
    state.catalog = collection.features || [];
    const formationId = new URLSearchParams(location.search).get("formation_id");
    if (formationId) {
      const match = state.catalog.find((feature) => feature.properties.formation_id === formationId);
      if (match) focusFormation(match);
      else $("formationId").value = formationId;
    }
  })
  .catch(() => setStatus($("registrationStatus"), "Catalog lookup is unavailable; manual map registration still works."));

window.CropCircleGeoref = Object.freeze({
  schemaVersion: REGISTRATION_SCHEMA,
  getRegistrationMetadata: () => state.transform ? buildMetadata() : null,
  getOrientationObservation: orientationObservation,
  focusFormationById: (formationId) => {
    const match = state.catalog.find((feature) => feature.properties.formation_id === formationId);
    if (match) focusFormation(match);
    return Boolean(match);
  },
});

redrawControlPoints();
updatePublicationNotice();
