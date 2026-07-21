import { bearingLateralUncertainty, crossAlongTrack, destination, normalizeBearing } from './atlas-geodesy.mjs';

const map = L.map('map', { preferCanvas: true, zoomControl: false }).setView([38, -96], 4);
const pointRenderer = L.canvas({ padding: 0.5 });
L.control.zoom({ position: 'topright' }).addTo(map);
const streets = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
const imagery = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Tiles &copy; Esri and imagery partners' });
const layerControl = L.control.layers({ 'Street map': streets, 'Satellite imagery': imagery }, {}, { position: 'topright' }).addTo(map);

let collection, visibleFeatures = [], selected = null, rayLayer = null, hitLayer = null, lastManualRay = null;
const markerLayer = L.layerGroup().addTo(map);
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function marker(feature) {
  const us = feature.properties.country_code === 'US';
  const reviewedLine = feature.properties.has_straight_component === 'yes_evidence_reviewed';
  const pdfCandidate = ['high','medium'].includes(feature.properties.straight_component_tier);
  const sourceImageCandidate = ['high','medium'].includes(feature.properties.source_image_straight_tier);
  const straight = reviewedLine || pdfCandidate || sourceImageCandidate;
  const sourceImageOnly = sourceImageCandidate && !reviewedLine && !pdfCandidate;
  const circle = L.circleMarker([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], {
    radius: (us ? 5 : 3.2) + (straight ? 1.2 : 0), color: sourceImageOnly ? '#d6b3ff' : straight ? '#fff1b8' : (us ? '#ffbd73' : '#79ddd0'), weight: straight ? 2 : 1, dashArray: sourceImageOnly ? '3 2' : null, fillColor: us ? '#e67f2e' : '#2d9e91', fillOpacity: .76, renderer: pointRenderer
  });
  const p = feature.properties;
  const firstUrl = (p.source_urls || '').split('; ')[0];
  const straightNote = p.has_straight_component === 'yes_evidence_reviewed'
    ? '<p>Line/axis evidence: human-reviewed true-north orientation</p>'
    : p.straight_component_tier && p.straight_component_tier !== 'not_analyzed' ? `<p>Straight component: ${esc(p.straight_component_tier)} automated tier${p.diagram_angle_deg ? ` · image angle ${esc(p.diagram_angle_deg)}°` : ''}</p>` : '';
  const sourceImageStraightNote = ['high','medium','low'].includes(p.source_image_straight_tier)
    ? `<p>ICCRA source-image review queue: ${esc(p.source_image_straight_tier)} automated tier${p.source_image_axis_deg ? ` · image-space axis ${esc(p.source_image_axis_deg)}° ± ${esc(p.source_image_axis_uncertainty_deg)}°` : ''}. Not human-validated; no true-north meaning.</p>`
    : p.source_image_straight_status === 'analyzed_no_candidate' ? '<p>ICCRA source image analyzed: no automated line-review threshold met.</p>' : '';
  const imageNote = Number(p.source_image_count) ? `<p>Source-page images: ${esc(p.source_image_count)} (linked; rights unverified)</p>` : '';
  circle.bindPopup(`<div class="popup"><h3>${esc(p.place || 'Unnamed report')}</h3><p>${esc([p.region,p.country].filter(Boolean).join(', '))}</p><p>${esc(p.date_iso)} · ${esc(p.date_precision)}</p><p>Coordinate: ${esc(p.geocode_method || 'unknown method')} · uncertainty ${esc(p.coordinate_uncertainty_km)} km</p>${straightNote}${sourceImageStraightNote}${imageNote}<p>Orientation: ${esc(p.orientation_status)}</p><p>${esc(p.source_names)}</p>${firstUrl ? `<a href="${esc(firstUrl)}" target="_blank" rel="noreferrer">Open primary source</a>` : ''}<button onclick="selectFormation('${esc(p.formation_id)}')">Use in alignment lab</button><button class="secondary" onclick="openGeorefForFormation('${esc(p.formation_id)}')">Register aerial image</button></div>`);
  return circle;
}

function applyFilters() {
  if (!collection) return;
  const query = $('search').value.trim().toLowerCase();
  const min = Number($('yearMin').value || -Infinity), max = Number($('yearMax').value || Infinity);
  const country = $('country').value, usOnly = $('usOnly').checked, straightOnly = $('straightOnly').checked;
  visibleFeatures = collection.features.filter(f => {
    const p = f.properties;
    const hay = `${p.place} ${p.region} ${p.country} ${p.county}`.toLowerCase();
    const lineOrAxis = p.has_straight_component === 'yes_evidence_reviewed' || ['high','medium'].includes(p.straight_component_tier) || ['high','medium'].includes(p.source_image_straight_tier);
    return p.year >= min && p.year <= max && (!country || p.country_code === country) && (!usOnly || p.country_code === 'US') && (!straightOnly || lineOrAxis) && (!query || hay.includes(query));
  });
  markerLayer.clearLayers();
  visibleFeatures.forEach(f => marker(f).addTo(markerLayer));
  $('visibleCount').textContent = visibleFeatures.length.toLocaleString();
  const results=$('resultsList');
  results.replaceChildren();
  visibleFeatures.slice(0,100).forEach(feature=>{
    const p=feature.properties;
    const button=document.createElement('button');
    button.type='button'; button.className='result-item'; button.setAttribute('role','listitem');
    button.textContent=`${p.date_iso} — ${p.place}, ${p.region || p.country}`;
    button.addEventListener('click',()=>{window.selectFormation(p.formation_id);map.setView([feature.geometry.coordinates[1],feature.geometry.coordinates[0]],Math.max(map.getZoom(),10));});
    results.appendChild(button);
  });
  if(visibleFeatures.length>100){const note=document.createElement('p');note.className='muted';note.textContent=`Showing the first 100 of ${visibleFeatures.length.toLocaleString()} visible results. Narrow the filters or search to reach another record.`;results.appendChild(note);}
}

window.selectFormation = id => {
  selected = collection.features.find(f => f.properties.formation_id === id);
  if (!selected) return;
  const p = selected.properties;
  $('selectedLabel').textContent = `${p.date_iso} · ${p.place}, ${p.region || p.country}`;
  $('drawRay').disabled = false;
  $('exportRay').disabled = true;
  lastManualRay = null;
  $('openGeoref').disabled = false;
  window.selectedFormationId = id;
  if (window.registeredRayFormationId !== id) {
    window.registeredRayOrigin = null;
    window.registeredRayOriginUncertaintyKm = null;
    window.registeredRayAzimuthUncertaintyDeg = null;
    window.registeredRayFormationId = null;
    $('bearingUncertainty').value = '';
  }
  map.closePopup();
};

function selectedRayOrigin() {
  if (window.registeredRayFormationId === selected?.properties.formation_id && Array.isArray(window.registeredRayOrigin)) {
    return window.registeredRayOrigin;
  }
  return [selected.geometry.coordinates[1],selected.geometry.coordinates[0]];
}

function drawRay() {
  if (!selected) return;
  const origin=selectedRayOrigin(), bearing=normalizeBearing($('bearing').value);
  const range=Number($('range').value), corridor=Number($('corridor').value), both=$('bidirectional').checked;
  const bearingUncertaintyDeg=Number($('bearingUncertainty').value);
  const hasBearingUncertainty=$('bearingUncertainty').value!==''&&Number.isFinite(bearingUncertaintyDeg)&&bearingUncertaintyDeg>=0;
  if (!Number.isFinite(bearing) || !Number.isFinite(range) || range <= 0 || !Number.isFinite(corridor) || corridor <= 0) {
    $('hitSummary').textContent='Enter a finite true bearing, positive range, and positive corridor.';
    $('exportRay').disabled=true;
    lastManualRay=null;
    return;
  }
  const points=both?[destination(origin,bearing+180,range),destination(origin,bearing,range)]:[origin,destination(origin,bearing,range)];
  if (rayLayer) rayLayer.remove(); if (hitLayer) hitLayer.remove();
  rayLayer=L.polyline(points,{color:'#54d6c2',weight:3,dashArray:'8 7'}).addTo(map);
  const hits=[];
  const originUncertaintyKm=window.registeredRayFormationId===selected.properties.formation_id&&Number.isFinite(Number(window.registeredRayOriginUncertaintyKm))?Number(window.registeredRayOriginUncertaintyKm):Number(selected.properties.coordinate_uncertainty_km||Infinity);
  const originMethod=window.registeredRayFormationId===selected.properties.formation_id&&Array.isArray(window.registeredRayOrigin)?'registered_component_midpoint':(selected.properties.geocode_method||'unknown');
  collection.features.forEach(f=>{
    if(f===selected)return; const target=[f.geometry.coordinates[1],f.geometry.coordinates[0]];
    const tracks=[crossAlongTrack(origin,target,bearing)];
    if(both)tracks.push(crossAlongTrack(origin,target,bearing+180));
    const inRange=tracks.filter(track=>track.alongTrackKm>=0&&track.alongTrackKm<=range);
    if(!inRange.length)return;
    const best=inRange.sort((a,b)=>Math.abs(a.crossTrackKm)-Math.abs(b.crossTrackKm))[0];
    const cross=Math.abs(best.crossTrackKm);
    if(cross<=corridor){const angularUncertainty=hasBearingUncertainty?bearingLateralUncertainty(best.alongTrackKm,bearingUncertaintyDeg):Infinity;const positionalUncertainty=originUncertaintyKm+Number(f.properties.coordinate_uncertainty_km||Infinity)+angularUncertainty;hits.push({f,d:best.distanceKm,cross,along:best.alongTrackKm,eligible:positionalUncertainty<=corridor,positionalUncertainty,angularUncertainty});}
  });
  hits.sort((a,b)=>a.cross-b.cross);
  hitLayer=L.layerGroup(hits.map(h=>L.circleMarker([h.f.geometry.coordinates[1],h.f.geometry.coordinates[0]],{radius:7,color:'#fff',weight:2,fillColor:h.eligible?'#54d6c2':'#f6ad55',fillOpacity:.9}).bindTooltip(`${h.f.properties.place}: ${h.cross.toFixed(2)} km cross-track; ${Number.isFinite(h.positionalUncertainty)?`${h.positionalUncertainty.toFixed(1)} km combined spatial uncertainty`:'bearing uncertainty not supplied'}`))).addTo(map);
  const eligible=hits.filter(h=>h.eligible).length;
  const exportReady=hasBearingUncertainty&&Number.isFinite(originUncertaintyKm);
  $('hitSummary').textContent=`${hits.length} catalog point${hits.length===1?'':'s'} fall inside this centerline corridor; ${eligible} also have combined origin, target, and bearing uncertainty no wider than the corridor. Results remain exploratory and uncorrected for clustering or multiple testing.${exportReady?' Any manual KML export is labeled as an unqualified hypothesis.':' Supply bearing and origin uncertainty before exporting the unqualified hypothesis.'}`;
  lastManualRay=exportReady?{origin,bearing,range,corridor,both,bearingUncertaintyDeg,originUncertaintyKm,originMethod,points}:null;
  $('exportRay').disabled=!exportReady; map.fitBounds(rayLayer.getBounds(),{padding:[30,30]});
}

function exportRay() {
  if(!selected||!lastManualRay)return;
  const ray=lastManualRay;
  const coords=ray.points.map(p=>`${p[1]},${p[0]},0`).join(' ');
  const caveat='UNQUALIFIED MANUAL HYPOTHESIS. This line is user-entered, is not an evidence-qualified atlas ray, and has no demonstrated predictive validity. Apparent alignments require correction for uncertainty, clustering, reporting bias, and multiple testing.';
  const extended={
    qualification_status:'unqualified_manual_hypothesis', predictive_validity:'none',
    source_formation_id:selected.properties.formation_id, source_date:selected.properties.date_iso,
    source_place:selected.properties.place, azimuth_true_deg:ray.bearing,
    azimuth_uncertainty_deg:ray.bearingUncertaintyDeg, directionality:ray.both?'bidirectional':'forward',
    max_range_km:ray.range, corridor_km:ray.corridor, origin_method:ray.originMethod,
    origin_uncertainty_km:ray.originUncertaintyKm, generated_by:'Crop Circle Atlas manual alignment lab'
  };
  const extendedXml=Object.entries(extended).map(([name,value])=>`<Data name="${esc(name)}"><value>${esc(value)}</value></Data>`).join('');
  const kml=`<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>UNQUALIFIED HYPOTHESIS - ${esc(selected.properties.formation_id)}</name><description>${esc(caveat)}</description><Style id="unqualified"><LineStyle><color>ff55adf6</color><width>3</width></LineStyle></Style><Placemark><name>UNQUALIFIED HYPOTHESIS - ${esc(ray.bearing)} degrees true</name><description>${esc(caveat)}</description><styleUrl>#unqualified</styleUrl><ExtendedData>${extendedXml}</ExtendedData><LineString><tessellate>1</tessellate><coordinates>${coords}</coordinates></LineString></Placemark></Document></kml>`;
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([kml],{type:'application/vnd.google-earth.kml+xml'})); a.download=`${selected.properties.formation_id}_unqualified_hypothesis_${ray.bearing}.kml`; a.click(); URL.revokeObjectURL(a.href);
}

$('drawRay').addEventListener('click',drawRay); $('exportRay').addEventListener('click',exportRay);
['bearing','bearingUncertainty','range','corridor','bidirectional'].forEach(id=>$(id).addEventListener('input',()=>{lastManualRay=null;$('exportRay').disabled=true;}));
['search','yearMin','yearMax','country','usOnly','straightOnly'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',applyFilters));

fetch('data/formations.geojson').then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}).then(data=>{
  collection=data; const years=data.features.map(f=>f.properties.year); $('yearMin').value=Math.min(...years); $('yearMax').value=Math.max(...years);
  const countries=[...new Map(data.features.map(f=>[f.properties.country_code,f.properties.country])).entries()].filter(x=>x[0]).sort((a,b)=>a[1].localeCompare(b[1]));
  countries.forEach(([code,name])=>$('country').add(new Option(name,code))); $('totalCount').textContent=data.features.length.toLocaleString(); $('usCount').textContent=data.features.filter(f=>f.properties.country_code==='US').length.toLocaleString(); $('straightCount').textContent=data.features.filter(f=>f.properties.has_straight_component==='yes_evidence_reviewed'||['high','medium'].includes(f.properties.straight_component_tier)||['high','medium'].includes(f.properties.source_image_straight_tier)).length.toLocaleString(); applyFilters();
}).catch(error=>{$('visibleCount').textContent='Error';$('hitSummary').textContent=`Could not load map data: ${error.message}. Serve this folder with a local web server.`});

fetch('data/orientation_rays.geojson').then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}).then(data=>{
  const qualifiedRays=L.geoJSON(data,{style:{color:'#54d6c2',weight:3,dashArray:'8 7'},onEachFeature:(feature,layer)=>{
    const p=feature.properties;
    layer.bindPopup(`<div class="popup"><h3>Experimental projection from documented orientation</h3><p>${esc(p.date_iso)} · ${esc(p.place)}</p><p>${esc(p.azimuth_true_deg)}° true ± ${esc(p.azimuth_uncertainty_deg)}°</p><p>${esc(p.orientation_method)} · origin ${esc(p.origin_method)} ± ${esc(p.origin_uncertainty_m)} m</p><p>Evidence review: ${esc(p.reviewed_at || 'date unavailable')} · observation ${esc(p.observation_id || 'unknown')}</p><p>The local orientation is evidence-reviewed; extending it across distance is an exploratory experiment with no demonstrated predictive validity.</p>${p.notes?`<p>${esc(p.notes)}</p>`:''}${p.evidence_url?`<a href="${esc(p.evidence_url)}" target="_blank" rel="noreferrer">Open orientation evidence</a>`:''}</div>`);
  }}).addTo(map);
  layerControl.addOverlay(qualifiedRays,`Experimental projections from documented orientations (${data.features.length})`);
}).catch(error=>console.warn('Qualified ray layer unavailable:',error));
