import { bearingLateralUncertainty, crossAlongTrack, destination, normalizeBearing } from './atlas-geodesy.mjs';
import { projectiveImageOverlay } from './projective-image-overlay.mjs';

const map = L.map('map', { preferCanvas: true, zoomControl: false }).setView([38, -96], 4);
map.createPane('registeredImageryPane');
map.getPane('registeredImageryPane').style.zIndex = '350';
map.getPane('registeredImageryPane').style.pointerEvents = 'none';
map.createPane('localityPointPane');
map.getPane('localityPointPane').style.zIndex = '420';
map.createPane('overlayFootprintPane');
map.getPane('overlayFootprintPane').style.zIndex = '445';
map.createPane('rayPane');
map.getPane('rayPane').style.zIndex = '460';
map.getPane('rayPane').style.pointerEvents = 'none';
map.createPane('sitePointPane');
map.getPane('sitePointPane').style.zIndex = '480';
const localityRenderer = L.canvas({ pane: 'localityPointPane', padding: 0.5 });
const siteRenderer = L.canvas({ pane: 'sitePointPane', padding: 0.5 });
L.control.zoom({ position: 'topright' }).addTo(map);

const streets = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors',
}).addTo(map);
const imagery = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
  maxZoom: 19,
  attribution: 'Tiles &copy; Esri and imagery partners',
});
const layerControl = L.control.layers(
  { 'Street map': streets, 'Satellite imagery': imagery },
  {},
  { position: 'topright' },
).addTo(map);

const siteLayer = L.layerGroup().addTo(map);
const localityLayer = L.layerGroup();
const registeredFootprintLayer = L.layerGroup().addTo(map);
layerControl.addOverlay(siteLayer, 'Field candidates and reviewed sites');
layerControl.addOverlay(localityLayer, 'Rough locality references (not sites)');

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[character]));

let allFormations = [];
let visibleFormations = [];
let selected = null;
let rayLayer = null;
let hitLayer = null;
let lastManualRay = null;
let activeOverlay = null;
let activeOverlayRecord = null;
let overlayRecords = [];
let siteCollection = { type: 'FeatureCollection', features: [] };
let localityCollection = { type: 'FeatureCollection', features: [] };
let provisionalCollection = { type: 'FeatureCollection', features: [] };
let localityLoadPromise = null;

const formationsById = new Map();
const siteFeaturesById = new Map();
const localityFeaturesById = new Map();
const renderedMarkersById = new Map();
const overlayFootprintsByFormation = new Map();
const provisionalByFormation = new Map();

const ACTUAL_SITE_STATUSES = new Set([
  'corroborated_field', 'registered_site', 'exact_source_gps',
  'verified_historical_imagery', 'georeferenced_aerial_photo',
]);

function locationStatus(record = {}) {
  const status = record.location_status || record.site_status || record.location_role;
  if (status) return status;
  if (record.geocode_method === 'geonames_locality_centroid') return 'locality_reference';
  if (record.latitude !== '' && record.latitude != null) return 'exact_source_gps';
  return 'unresolved';
}

function locationRole(record = {}) {
  const explicit = record.location_role;
  const status = locationStatus(record);
  if (explicit === 'formation_site') {
    if (status === 'candidate_field' || status === 'probable_field') return 'candidate_field';
    return status === 'registered_site' ? 'registered_site' : 'corroborated_field';
  }
  if (explicit) return explicit;
  if (ACTUAL_SITE_STATUSES.has(status)) return status === 'registered_site' ? 'registered_site' : 'corroborated_field';
  if (status === 'candidate_field' || status === 'probable_field') return 'candidate_field';
  if (status === 'locality_reference' || status === 'locality_reference_only') return 'locality_reference';
  return 'unresolved';
}

function isActualSite(record) {
  return ['corroborated_field', 'registered_site'].includes(locationRole(record))
    || ACTUAL_SITE_STATUSES.has(locationStatus(record));
}

function isAlignmentEligibleSite(record) {
  return String(record.site_alignment_eligible || '').toLowerCase() === 'true';
}

function locationLabel(record) {
  const role = locationRole(record);
  if (role === 'registered_site') {
    return record.site_review_status === 'source_report_not_independently_reviewed'
      ? 'Source-reported coordinate (not independently reviewed)'
      : 'Registered site';
  }
  if (role === 'corroborated_field') return 'Corroborated field/site';
  if (role === 'candidate_field') return 'Candidate field (not exact)';
  if (role === 'locality_reference') return 'Reference locality—not the formation site';
  return 'Unresolved—no point placed';
}

function coordinateUncertaintyKm(record) {
  const metres = Number(record.coordinate_uncertainty_m || record.site_coordinate_uncertainty_m || record.site_uncertainty_m);
  if (Number.isFinite(metres)) return metres / 1000;
  const kilometres = Number(record.coordinate_uncertainty_km);
  return Number.isFinite(kilometres) ? kilometres : Infinity;
}

function primaryRows(payload) {
  const rows = Array.isArray(payload) ? payload : payload?.formations || payload?.records || [];
  return rows.filter((row) => !row.alias_of && locationStatus(row) !== 'alias_of');
}

function fullRecord(feature) {
  return formationsById.get(feature.properties.formation_id) || feature.properties;
}

function sourceLink(record) {
  return record.site_evidence_source_url || record.location_evidence_url || record.coordinate_source_url
    || String(record.source_urls || '').split('; ')[0] || '';
}

function straightNotes(record) {
  const notes = [];
  if (record.has_straight_component === 'yes_evidence_reviewed') {
    notes.push('Line/axis evidence: human-reviewed true-north orientation.');
  } else if (record.straight_component_tier && record.straight_component_tier !== 'not_analyzed') {
    notes.push(`PDF diagram: ${record.straight_component_tier} automated review tier${record.diagram_angle_deg ? `; image angle ${record.diagram_angle_deg}°` : ''}.`);
  }
  if (['high', 'medium', 'low'].includes(record.source_image_straight_tier)) {
    notes.push(`Source-image queue: ${record.source_image_straight_tier} automated tier${record.source_image_axis_deg ? `; image-space axis ${record.source_image_axis_deg}° ± ${record.source_image_axis_uncertainty_deg}°` : ''}. This is not a true-north bearing.`);
  }
  const provisional = provisionalByFormation.get(record.formation_id);
  if (provisional) {
    notes.push(`Provisional registered axis: ${provisional.properties.azimuth_true_deg}°/${(Number(provisional.properties.azimuth_true_deg) + 180) % 360}° true ± ${provisional.properties.azimuth_uncertainty_deg}°. Independent checkpoints are still pending.`);
  }
  return notes.map((note) => `<p>${esc(note)}</p>`).join('');
}

function popupFor(records) {
  const multiple = records.length > 1;
  const body = records.map((record) => {
    const role = locationRole(record);
    const uncertainty = coordinateUncertaintyKm(record);
    const evidence = sourceLink(record);
    const hasOverlay = overlayRecords.some((overlay) => overlay.formation_id === record.formation_id);
    const canAlign = isAlignmentEligibleSite(record);
    const method = record.site_coordinate_method || record.location_method || record.geocode_method || 'not resolved';
    return `<article class="popup-record">
      <h3>${esc(record.place || 'Unnamed report')}</h3>
      <p>${esc([record.region, record.country].filter(Boolean).join(', '))}</p>
      <p>${esc(record.date_iso)} · ${esc(record.date_precision)}</p>
      <p><strong>${esc(locationLabel(record))}</strong></p>
      <p>Method: ${esc(method)}${Number.isFinite(uncertainty) ? ` · uncertainty ${(uncertainty * 1000).toFixed(0)} m` : ''}</p>
      <p>Review: ${esc(record.site_review_status || 'not reviewed')} · directly visible: ${esc(record.site_directly_visible || 'not recorded')} · alignment target: ${isAlignmentEligibleSite(record) ? 'eligible by current site-quality gate' : 'not eligible'}</p>
      ${record.site_notes || record.location_notes ? `<p>${esc(record.site_notes || record.location_notes)}</p>` : ''}
      ${straightNotes(record)}
      ${Number(record.source_image_count) ? `<p>Source-page images: ${esc(record.source_image_count)}; publication rights not assumed.</p>` : ''}
      <p>Sources: ${esc(record.source_names || '')}</p>
      ${evidence ? `<a href="${esc(evidence)}" target="_blank" rel="noreferrer">Open supporting source</a>` : ''}
      <button onclick="selectFormation('${esc(record.formation_id)}')" ${canAlign ? '' : 'disabled'}>Use in alignment lab</button>
      ${hasOverlay ? `<button class="secondary" onclick="showOverlayForFormation('${esc(record.formation_id)}')">Load registered aerial image</button>` : ''}
      <button class="secondary" onclick="openGeorefForFormation('${esc(record.formation_id)}')">Register another aerial image</button>
    </article>`;
  }).join(multiple ? '<hr>' : '');
  return `<div class="popup">${multiple ? `<p><strong>${records.length} reports share this reference point.</strong></p>` : ''}${body}</div>`;
}

function markerStyle(record, reference = false) {
  const role = locationRole(record);
  const hasLine = record.has_straight_component === 'yes_evidence_reviewed'
    || provisionalByFormation.has(record.formation_id)
    || ['high', 'medium'].includes(record.straight_component_tier)
    || ['high', 'medium'].includes(record.source_image_straight_tier);
  if (reference || role === 'locality_reference') {
    return {
      radius: 5, color: '#f6ad55', weight: 2.25, opacity: 1, dashArray: '3 2',
      fillColor: '#f6ad55', fillOpacity: 0.08, renderer: localityRenderer,
    };
  }
  const verified = isActualSite(record);
  return {
    radius: (verified ? 8 : 9) + (hasLine ? 1 : 0),
    color: verified ? '#d8fff9' : '#fff4c7',
    weight: hasLine ? 3.5 : 3,
    fillColor: verified ? '#2d9e91' : '#f6ad55',
    fillOpacity: 1,
    renderer: siteRenderer,
  };
}

function renderFeatures(features, targetLayer, reference = false) {
  const groups = new Map();
  for (const feature of features) {
    const [longitude, latitude] = feature.geometry.coordinates;
    const key = `${Number(latitude).toFixed(7)},${Number(longitude).toFixed(7)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(feature);
  }
  const orderedGroups = [...groups.values()].sort((left, right) => {
    if (reference) return 0;
    const priority = (group) => locationRole(fullRecord(group[0])) === 'candidate_field' ? 1 : 0;
    return priority(left) - priority(right);
  });
  for (const group of orderedGroups) {
    const records = group.map(fullRecord);
    const feature = group[0];
    const [longitude, latitude] = feature.geometry.coordinates;
    const marker = L.circleMarker([latitude, longitude], markerStyle(records[0], reference));
    marker.bindPopup(popupFor(records), { maxWidth: 360 });
    marker.addTo(targetLayer);
    records.forEach((record) => renderedMarkersById.set(record.formation_id, marker));
  }
}

function lineOrAxis(record) {
  return record.has_straight_component === 'yes_evidence_reviewed'
    || provisionalByFormation.has(record.formation_id)
    || ['high', 'medium'].includes(record.straight_component_tier)
    || ['high', 'medium'].includes(record.source_image_straight_tier);
}

function filteredRows() {
  const query = $('search').value.trim().toLowerCase();
  const minimum = Number($('yearMin').value || -Infinity);
  const maximum = Number($('yearMax').value || Infinity);
  const country = $('country').value;
  const usOnly = $('usOnly').checked;
  const straightOnly = $('straightOnly').checked;
  return allFormations.filter((record) => {
    const haystack = `${record.place || ''} ${record.region || ''} ${record.country || ''} ${record.county || ''} ${record.date_iso || ''} ${record.site_search_aliases || ''} ${record.site_notes || ''}`.toLowerCase();
    const year = Number(record.year);
    return year >= minimum && year <= maximum
      && (!country || record.country_code === country)
      && (!usOnly || record.country_code === 'US')
      && (!straightOnly || lineOrAxis(record))
      && (!query || haystack.includes(query));
  });
}

function applyFilters() {
  if (!allFormations.length) return;
  visibleFormations = filteredRows();
  const visibleIds = new Set(visibleFormations.map((record) => record.formation_id));
  if (activeOverlayRecord && !visibleIds.has(activeOverlayRecord.formation_id)) {
    resetOverlaySelection();
  }
  if (selected && !visibleIds.has(selected.formation_id)) {
    $('toggleOverlay').disabled = true;
    $('overlayNotice').textContent = 'The selected formation and its source-photo overlay are hidden by the active filters. Change the filters or select a visible report.';
  } else if (selected && !activeOverlay) {
    updateOverlayControls();
  }
  siteLayer.clearLayers();
  localityLayer.clearLayers();
  renderedMarkersById.clear();
  renderFeatures(siteCollection.features.filter((feature) => visibleIds.has(feature.properties.formation_id)), siteLayer);
  if ($('showLocalities').checked && localityCollection.features.length) {
    renderFeatures(localityCollection.features.filter((feature) => visibleIds.has(feature.properties.formation_id)), localityLayer, true);
  }
  if ($('showLocalities').checked && !map.hasLayer(localityLayer)) localityLayer.addTo(map);
  if (!$('showLocalities').checked && map.hasLayer(localityLayer)) map.removeLayer(localityLayer);
  renderRegisteredFootprints(visibleIds);
  $('visibleCount').textContent = visibleFormations.length.toLocaleString();

  const results = $('resultsList');
  results.replaceChildren();
  visibleFormations.slice(0, 200).forEach((record) => {
    const button = document.createElement('button');
    const role = locationRole(record);
    button.type = 'button';
    button.className = 'result-item';
    button.dataset.locationRole = role;
    button.setAttribute('role', 'listitem');
    const title = document.createElement('span');
    title.textContent = `${record.date_iso} — ${record.place}, ${record.region || record.country}`;
    const detail = document.createElement('small');
    detail.textContent = locationLabel(record);
    button.append(title, detail);
    if (overlayRecords.some((overlay) => overlay.formation_id === record.formation_id)) {
      const badge = document.createElement('span');
      badge.className = 'result-badge';
      badge.textContent = 'REGISTERED IMAGE';
      button.appendChild(badge);
    }
    button.addEventListener('click', () => selectFormation(record.formation_id, true));
    results.appendChild(button);
  });
  if (visibleFormations.length > 200) {
    const note = document.createElement('p');
    note.className = 'muted';
    note.textContent = `Showing the first 200 of ${visibleFormations.length.toLocaleString()} matching reports. Narrow the filters to reach another record.`;
    results.appendChild(note);
  }
}

function selectedGeometry() {
  return siteFeaturesById.get(selected?.formation_id) || localityFeaturesById.get(selected?.formation_id) || null;
}

function selectedHasQualifiedOrigin() {
  return Boolean(selected && (isAlignmentEligibleSite(selected)
    || (window.registeredRayFormationId === selected.formation_id && Array.isArray(window.registeredRayOrigin))));
}

function setRegisteredFootprintVisible(record, visible) {
  const layers = overlayFootprintsByFormation.get(record?.formation_id);
  if (!layers) return;
  for (const layer of [layers.footprint, layers.marker]) {
    if (visible) layer.addTo(registeredFootprintLayer);
    else registeredFootprintLayer.removeLayer(layer);
  }
}

function resetOverlaySelection() {
  const previousRecord = activeOverlayRecord;
  activeOverlay?.remove();
  activeOverlay = null;
  activeOverlayRecord = null;
  if (previousRecord) setRegisteredFootprintVisible(previousRecord, true);
  $('toggleOverlay').textContent = 'Load and zoom to registered image';
  $('overlayOpacityLabel').hidden = true;
}

function updateOverlayControls() {
  const match = overlayRecords.find((overlay) => overlay.formation_id === selected?.formation_id);
  $('toggleOverlay').disabled = !match;
  if (!match) {
    $('overlayNotice').textContent = selected
      ? 'No reviewed source-photo footprint is registered for this formation yet.'
      : 'Select a formation to inspect its registered source-photo footprint.';
    return;
  }
  $('overlayOpacity').value = String(match.default_opacity || 0.68);
  const disclosure = match.quality_disclosure ? ` ${match.quality_disclosure}` : '';
  $('overlayNotice').textContent = `${match.title}. ${match.registration_status.replaceAll('_', ' ')}.${disclosure} Click the button to load the source-hosted photograph over its mapped footprint.`;
}

function renderRegisteredFootprints(visibleIds = null) {
  registeredFootprintLayer.clearLayers();
  overlayFootprintsByFormation.clear();
  for (const record of overlayRecords) {
    if (visibleIds && !visibleIds.has(record.formation_id)) continue;
    if (!Array.isArray(record.corners) || record.corners.length !== 4) continue;
    const footprint = L.polygon(record.corners, {
      pane: 'overlayFootprintPane', color: '#ffe08a', weight: 3,
      opacity: 0.95, dashArray: '8 5', fillColor: '#f6ad55', fillOpacity: 0.12,
    }).bindTooltip(`${record.title} — click to load the registered image`);
    const center = Array.isArray(record.center) ? record.center : footprint.getBounds().getCenter();
    const marker = L.marker(center, {
      pane: 'overlayFootprintPane',
      icon: L.divIcon({
        className: 'registered-image-marker',
        html: '<span aria-hidden="true">IMG</span>',
        iconSize: [34, 24], iconAnchor: [17, 31], tooltipAnchor: [0, -25],
      }),
      title: `${record.title} — click to load`,
    }).bindTooltip(`${record.title} — click to load the registered image`);
    const load = () => window.showOverlayForFormation(record.formation_id);
    footprint.on('click', load);
    marker.on('click', load);
    footprint.addTo(registeredFootprintLayer);
    marker.addTo(registeredFootprintLayer);
    overlayFootprintsByFormation.set(record.formation_id, { footprint, marker });
  }
}

function applyProvisionalOrientation(record) {
  const feature = provisionalByFormation.get(record.formation_id);
  if (!feature) return false;
  const properties = feature.properties;
  $('bearing').value = String(properties.azimuth_true_deg);
  $('bearingUncertainty').value = String(properties.azimuth_uncertainty_deg);
  $('range').value = String(properties.max_range_km || 500);
  $('corridor').value = String(properties.corridor_km || 2);
  $('bidirectional').checked = properties.directionality === 'bidirectional';
  $('hitSummary').textContent = `Loaded the user-demonstrated ${properties.azimuth_true_deg}°/${(Number(properties.azimuth_true_deg) + 180) % 360}° true axis ± ${properties.azimuth_uncertainty_deg}°. It is visibly georegistered but remains provisional pending independent checkpoints; any long-distance extension is an unqualified hypothesis.`;
  return true;
}

async function selectFormation(id, focus = false) {
  selected = formationsById.get(id) || null;
  if (!selected) return;
  if (focus && locationRole(selected) === 'locality_reference' && !localityFeaturesById.has(id)) {
    $('showLocalities').checked = true;
    try {
      await ensureLocalities();
    } catch {
      return;
    }
    if (selected?.formation_id !== id) return;
  }
  window.selectedFormationId = id;
  if (rayLayer) rayLayer.remove();
  if (hitLayer) hitLayer.remove();
  rayLayer = null;
  hitLayer = null;
  const geometry = selectedGeometry();
  const canAlign = selectedHasQualifiedOrigin();
  $('selectedLabel').textContent = `${selected.date_iso} · ${selected.place}, ${selected.region || selected.country} · ${locationLabel(selected)}`;
  $('drawRay').disabled = !canAlign;
  $('exportRay').disabled = true;
  $('openGeoref').disabled = false;
  lastManualRay = null;
  if (window.registeredRayFormationId !== id) {
    window.registeredRayOrigin = null;
    window.registeredRayOriginUncertaintyKm = null;
    window.registeredRayAzimuthUncertaintyDeg = null;
    window.registeredRayFormationId = null;
    $('bearingUncertainty').value = '';
  }
  resetOverlaySelection();
  updateOverlayControls();
  if (!applyProvisionalOrientation(selected)) {
    $('hitSummary').textContent = canAlign
      ? 'This reviewed field can originate an unqualified manual hypothesis. Enter a true bearing and uncertainty, then draw the line.'
      : `${locationLabel(selected)}. Resolve and review the actual field before drawing a geographic ray.`;
  }
  if (focus && geometry) {
    const [longitude, latitude] = geometry.geometry.coordinates;
    if (locationRole(selected) === 'locality_reference' && !$('showLocalities').checked) {
      $('showLocalities').checked = true;
      applyFilters();
    }
    map.setView([latitude, longitude], Math.max(map.getZoom(), isActualSite(selected) ? 16 : 10));
    renderedMarkersById.get(id)?.openPopup();
  }
}

window.selectFormation = selectFormation;

function selectedRayOrigin() {
  if (window.registeredRayFormationId === selected?.formation_id && Array.isArray(window.registeredRayOrigin)) {
    return window.registeredRayOrigin;
  }
  const feature = selectedGeometry();
  if (!feature || !isAlignmentEligibleSite(selected)) return null;
  return [feature.geometry.coordinates[1], feature.geometry.coordinates[0]];
}

function drawRay() {
  if (!selected || !selectedHasQualifiedOrigin()) return;
  const origin = selectedRayOrigin();
  const bearing = normalizeBearing($('bearing').value);
  const range = Number($('range').value);
  const corridor = Number($('corridor').value);
  const both = $('bidirectional').checked;
  const bearingUncertaintyDeg = Number($('bearingUncertainty').value);
  const hasBearingUncertainty = $('bearingUncertainty').value !== ''
    && Number.isFinite(bearingUncertaintyDeg) && bearingUncertaintyDeg >= 0;
  if (!origin || !Number.isFinite(bearing) || !Number.isFinite(range) || range <= 0
      || !Number.isFinite(corridor) || corridor <= 0) {
    $('hitSummary').textContent = 'Select a field-resolved origin and enter a finite true bearing, positive range, and positive corridor.';
    $('exportRay').disabled = true;
    lastManualRay = null;
    return;
  }
  const points = both
    ? [destination(origin, bearing + 180, range), destination(origin, bearing, range)]
    : [origin, destination(origin, bearing, range)];
  if (rayLayer) rayLayer.remove();
  if (hitLayer) hitLayer.remove();
  rayLayer = L.polyline(points, { color: '#54d6c2', weight: 3, dashArray: '8 7', pane: 'rayPane' }).addTo(map);
  const originUncertaintyKm = window.registeredRayFormationId === selected.formation_id
    && Number.isFinite(Number(window.registeredRayOriginUncertaintyKm))
    ? Number(window.registeredRayOriginUncertaintyKm) : coordinateUncertaintyKm(selected);
  const originMethod = window.registeredRayFormationId === selected.formation_id
    ? 'registered_component_midpoint' : (selected.location_method || selected.geocode_method || locationStatus(selected));
  const hits = [];
  let excludedSameCluster = 0;
  let excludedNearOrigin = 0;
  for (const feature of siteCollection.features) {
    const targetRecord = fullRecord(feature);
    if (targetRecord.formation_id === selected.formation_id) continue;
    if (selected.site_cluster_id && targetRecord.site_cluster_id === selected.site_cluster_id) {
      excludedSameCluster += 1;
      continue;
    }
    const target = [feature.geometry.coordinates[1], feature.geometry.coordinates[0]];
    const tracks = [crossAlongTrack(origin, target, bearing)];
    if (both) tracks.push(crossAlongTrack(origin, target, bearing + 180));
    const inRange = tracks.filter((track) => track.alongTrackKm >= 0 && track.alongTrackKm <= range);
    if (!inRange.length) continue;
    const best = inRange.sort((left, right) => Math.abs(left.crossTrackKm) - Math.abs(right.crossTrackKm))[0];
    if (best.distanceKm < 1) {
      excludedNearOrigin += 1;
      continue;
    }
    const cross = Math.abs(best.crossTrackKm);
    if (cross > corridor) continue;
    const angularUncertainty = hasBearingUncertainty
      ? bearingLateralUncertainty(best.alongTrackKm, bearingUncertaintyDeg) : Infinity;
    const positionalUncertainty = originUncertaintyKm + coordinateUncertaintyKm(targetRecord) + angularUncertainty;
    const qualityReady = isAlignmentEligibleSite(targetRecord) && positionalUncertainty <= corridor;
    hits.push({ feature, record: targetRecord, cross, along: best.alongTrackKm, qualityReady, positionalUncertainty });
  }
  hits.sort((left, right) => left.cross - right.cross);
  hitLayer = L.layerGroup(hits.map((hit) => L.circleMarker(
    [hit.feature.geometry.coordinates[1], hit.feature.geometry.coordinates[0]],
    { radius: 7, color: '#fff', weight: 2, fillColor: hit.qualityReady ? '#54d6c2' : '#f6ad55', fillOpacity: 0.9, pane: 'rayPane' },
  ).bindTooltip(`${hit.record.place}: ${hit.cross.toFixed(2)} km cross-track; ${Number.isFinite(hit.positionalUncertainty) ? `${hit.positionalUncertainty.toFixed(1)} km combined uncertainty` : 'bearing uncertainty not supplied'}`))).addTo(map);
  const qualityReady = hits.filter((hit) => hit.qualityReady).length;
  const exportReady = hasBearingUncertainty && Number.isFinite(originUncertaintyKm);
  $('hitSummary').textContent = `Unqualified manual hypothesis: ${hits.length} field candidate/site${hits.length === 1 ? '' : 's'} fall inside this centerline corridor; ${qualityReady} pass the current site-quality and combined-uncertainty screen, but none is a formal statistical hit. ${excludedSameCluster} same-field cluster record${excludedSameCluster === 1 ? '' : 's'} and ${excludedNearOrigin} target${excludedNearOrigin === 1 ? '' : 's'} within 1 km were excluded. Locality references and unresolved reports are never tested. Predictive validity has not been demonstrated.`;
  lastManualRay = exportReady ? {
    origin, bearing, range, corridor, both, bearingUncertaintyDeg, originUncertaintyKm, originMethod, points,
  } : null;
  $('exportRay').disabled = !exportReady;
  map.fitBounds(rayLayer.getBounds(), { padding: [30, 30] });
}

function exportRay() {
  if (!selected || !lastManualRay) return;
  const ray = lastManualRay;
  const coordinates = ray.points.map((point) => `${point[1]},${point[0]},0`).join(' ');
  const caveat = 'UNQUALIFIED MANUAL HYPOTHESIS. This line is user-entered or provisional, is not an acceptance-qualified atlas ray, and has no demonstrated predictive validity. Locality centroids and unresolved reports are excluded; apparent alignments still require correction for uncertainty, clustering, reporting bias, and multiple testing.';
  const extended = {
    qualification_status: 'unqualified_manual_hypothesis', predictive_validity: 'none',
    source_formation_id: selected.formation_id, source_date: selected.date_iso,
    source_place: selected.place, source_location_status: locationStatus(selected),
    azimuth_true_deg: ray.bearing, azimuth_uncertainty_deg: ray.bearingUncertaintyDeg,
    directionality: ray.both ? 'bidirectional' : 'forward', max_range_km: ray.range,
    corridor_km: ray.corridor, origin_method: ray.originMethod,
    origin_uncertainty_km: ray.originUncertaintyKm, generated_by: 'Crop Circle Atlas manual alignment lab',
  };
  const extendedXml = Object.entries(extended)
    .map(([name, value]) => `<Data name="${esc(name)}"><value>${esc(value)}</value></Data>`).join('');
  const kml = `<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>UNQUALIFIED HYPOTHESIS - ${esc(selected.formation_id)}</name><description>${esc(caveat)}</description><Style id="unqualified"><LineStyle><color>ff55adf6</color><width>3</width></LineStyle></Style><Placemark><name>UNQUALIFIED HYPOTHESIS - ${esc(ray.bearing)} degrees true</name><description>${esc(caveat)}</description><styleUrl>#unqualified</styleUrl><ExtendedData>${extendedXml}</ExtendedData><LineString><tessellate>1</tessellate><coordinates>${coordinates}</coordinates></LineString></Placemark></Document></kml>`;
  const anchor = document.createElement('a');
  anchor.href = URL.createObjectURL(new Blob([kml], { type: 'application/vnd.google-earth.kml+xml' }));
  anchor.download = `${selected.formation_id}_unqualified_hypothesis_${ray.bearing}.kml`;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

function toggleSelectedOverlay() {
  const record = overlayRecords.find((overlay) => overlay.formation_id === selected?.formation_id);
  if (!record) return;
  if (activeOverlay && activeOverlayRecord?.overlay_id === record.overlay_id) {
    resetOverlaySelection();
    updateOverlayControls();
    return;
  }
  resetOverlaySelection();
  if (map.hasLayer(streets)) {
    map.removeLayer(streets);
    imagery.addTo(map);
  }
  map.closePopup();
  activeOverlayRecord = record;
  activeOverlay = projectiveImageOverlay(record.source_image_url, record.corners, {
    opacity: Number($('overlayOpacity').value || record.default_opacity || 0.68),
    subdivisions: 20,
    pane: 'registeredImageryPane',
    zIndex: 0,
    attribution: `Source photo: ${record.source_page_url}`,
  });
  activeOverlay.on('load', () => {
    $('overlayNotice').textContent = `${record.title} loaded from the source website. ${record.notes}`;
  });
  activeOverlay.on('imageloaderror', () => {
    $('overlayNotice').textContent = 'The source-hosted image could not be loaded. Open the supporting source or register a local copy in the private registration lab.';
  });
  activeOverlay.addTo(map);
  activeOverlay.bringToFront?.();
  setRegisteredFootprintVisible(record, false);
  $('toggleOverlay').textContent = 'Hide registered image';
  $('overlayOpacityLabel').hidden = false;
  map.fitBounds(activeOverlay.getBounds(), { padding: [35, 35], maxZoom: 18 });
}

window.showOverlayForFormation = async (id) => {
  await selectFormation(id, true);
  toggleSelectedOverlay();
};

$('drawRay').addEventListener('click', drawRay);
$('exportRay').addEventListener('click', exportRay);
$('toggleOverlay').addEventListener('click', toggleSelectedOverlay);
$('overlayOpacity').addEventListener('input', () => activeOverlay?.setOpacity(Number($('overlayOpacity').value)));
['bearing', 'bearingUncertainty', 'range', 'corridor', 'bidirectional'].forEach((id) => $(id).addEventListener('input', () => {
  lastManualRay = null;
  $('exportRay').disabled = true;
}));
['search', 'yearMin', 'yearMax', 'country', 'usOnly', 'straightOnly'].forEach((id) => {
  $(id).addEventListener(id === 'search' ? 'input' : 'change', applyFilters);
});
$('showLocalities').addEventListener('change', async () => {
  if ($('showLocalities').checked) {
    try {
      await ensureLocalities();
    } catch {
      return;
    }
  }
  applyFilters();
});
map.on('overlayadd', async (event) => {
  if (event.layer === localityLayer && !$('showLocalities').checked) {
    $('showLocalities').checked = true;
    try {
      await ensureLocalities();
    } catch {
      return;
    }
    applyFilters();
  }
});
map.on('overlayremove', (event) => {
  if (event.layer === localityLayer && $('showLocalities').checked) $('showLocalities').checked = false;
});

function addOrientationLayers() {
  fetch('data/orientation_rays.geojson').then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }).then((data) => {
    const qualified = L.geoJSON(data, {
      style: { color: '#54d6c2', weight: 3, dashArray: '8 7', pane: 'rayPane' },
      onEachFeature(feature, layer) {
        const properties = feature.properties;
        layer.bindPopup(`<div class="popup"><h3>Experimental extension of accepted local orientation</h3><p>${esc(properties.date_iso)} · ${esc(properties.place)}</p><p>${esc(properties.azimuth_true_deg)}° true ± ${esc(properties.azimuth_uncertainty_deg)}°</p><p>${esc(properties.orientation_method)} · origin ${esc(properties.origin_method)} ± ${esc(properties.origin_uncertainty_m)} m</p><p>No predictive validity has been demonstrated.</p>${properties.evidence_url ? `<a href="${esc(properties.evidence_url)}" target="_blank" rel="noreferrer">Open orientation evidence</a>` : ''}</div>`);
      },
    });
    layerControl.addOverlay(qualified, `Accepted local axes extended experimentally (${data.features.length})`);
  }).catch((error) => console.warn('Accepted orientation layer unavailable:', error));

  if (!provisionalCollection.features.length) return;
  const provisional = L.geoJSON(provisionalCollection, {
    style: { color: '#f6ad55', weight: 3, dashArray: '3 8', pane: 'rayPane' },
    onEachFeature(feature, layer) {
      const properties = feature.properties;
      layer.bindPopup(`<div class="popup"><h3>Provisional user-demonstrated axis</h3><p>${esc(properties.place)} · ${esc(properties.date_iso)}</p><p>${esc(properties.azimuth_true_deg)}°/${esc((Number(properties.azimuth_true_deg) + 180) % 360)}° true ± ${esc(properties.azimuth_uncertainty_deg)}°</p><p>Independent registration checkpoints are pending. This line is excluded from formal alignment-hit calculations.</p>${properties.evidence_url ? `<a href="${esc(properties.evidence_url)}" target="_blank" rel="noreferrer">Open source report</a>` : ''}</div>`);
    },
  }).addTo(map);
  layerControl.addOverlay(provisional, `Provisional registered axes (${provisionalCollection.features.length})`);
}

async function ensureLocalities() {
  if (localityCollection.features.length) return localityCollection;
  if (!localityLoadPromise) {
    localityLoadPromise = fetch('data/locality_references.geojson').then((response) => {
      if (!response.ok) throw new Error(`locality layer HTTP ${response.status}`);
      return response.json();
    }).then((localities) => {
      localityCollection = localities;
      localityFeaturesById.clear();
      localityCollection.features.forEach((feature) => localityFeaturesById.set(feature.properties.formation_id, feature));
      return localityCollection;
    }).catch((error) => {
      localityLoadPromise = null;
      $('showLocalities').checked = false;
      if (map.hasLayer(localityLayer)) map.removeLayer(localityLayer);
      $('hitSummary').textContent = `The optional locality-reference layer could not load: ${error.message}. Field sites and the searchable catalog remain available.`;
      throw error;
    });
  }
  return localityLoadPromise;
}

Promise.all([
  fetch('data/formation_index.json').then((response) => {
    if (!response.ok) throw new Error(`formation index HTTP ${response.status}`);
    return response.json();
  }),
  fetch('data/formation_sites.geojson').then((response) => {
    if (!response.ok) throw new Error(`site layer HTTP ${response.status}`);
    return response.json();
  }),
  fetch('data/registered_overlays.json?v=20260721.3').then((response) => response.ok ? response.json() : { overlays: [] }),
  fetch('data/provisional_orientation_rays.geojson').then((response) => response.ok ? response.json() : { type: 'FeatureCollection', features: [] }),
]).then(([indexPayload, sites, overlays, provisionalRays]) => {
  allFormations = primaryRows(indexPayload);
  allFormations.forEach((record) => formationsById.set(record.formation_id, record));
  siteCollection = sites;
  provisionalCollection = provisionalRays;
  siteCollection.features.forEach((feature) => siteFeaturesById.set(feature.properties.formation_id, feature));
  provisionalCollection.features.forEach((feature) => provisionalByFormation.set(feature.properties.formation_id, feature));
  overlayRecords = overlays.overlays || [];
  layerControl.addOverlay(registeredFootprintLayer, `Registered aerial-photo footprints (${overlayRecords.length})`);

  const years = allFormations.map((record) => Number(record.year)).filter(Number.isFinite);
  $('yearMin').value = Math.min(...years);
  $('yearMax').value = Math.max(...years);
  const countries = [...new Map(allFormations.map((record) => [record.country_code, record.country])).entries()]
    .filter(([code]) => code).sort((left, right) => left[1].localeCompare(right[1]));
  countries.forEach(([code, name]) => $('country').add(new Option(name, code)));
  $('siteCount').textContent = siteCollection.features.length.toLocaleString();
  $('referenceCount').textContent = Number(indexPayload.metadata?.site_status_counts?.locality_reference || 0).toLocaleString();
  $('unresolvedCount').textContent = allFormations.filter((record) => locationRole(record) === 'unresolved').length.toLocaleString();
  applyFilters();
  addOrientationLayers();
}).catch((error) => {
  $('visibleCount').textContent = 'Error';
  $('hitSummary').textContent = `Could not load the evidence-separated atlas data: ${error.message}.`;
});
