const map = L.map('map', { preferCanvas: true, zoomControl: false }).setView([38, -96], 4);
const pointRenderer = L.canvas({ padding: 0.5 });
L.control.zoom({ position: 'topright' }).addTo(map);
const streets = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
const imagery = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Tiles &copy; Esri and imagery partners' });
L.control.layers({ 'Street map': streets, 'Satellite imagery': imagery }, {}, { position: 'topright' }).addTo(map);

let collection, visibleFeatures = [], selected = null, rayLayer = null, hitLayer = null;
let overlayDataUrl = null, overlayClicks = [], imageOverlay = null;
const markerLayer = L.layerGroup().addTo(map);
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function marker(feature) {
  const us = feature.properties.country_code === 'US';
  const circle = L.circleMarker([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], {
    radius: us ? 5 : 3.2, color: us ? '#ffbd73' : '#79ddd0', weight: 1, fillColor: us ? '#e67f2e' : '#2d9e91', fillOpacity: .76, renderer: pointRenderer
  });
  const p = feature.properties;
  const firstUrl = (p.source_urls || '').split('; ')[0];
  circle.bindPopup(`<div class="popup"><h3>${esc(p.place || 'Unnamed report')}</h3><p>${esc([p.region,p.country].filter(Boolean).join(', '))}</p><p>${esc(p.date_iso)} · ${esc(p.date_precision)}</p><p>Approx. uncertainty: ${esc(p.coordinate_uncertainty_km)} km</p><p>${esc(p.source_names)}</p>${firstUrl ? `<a href="${esc(firstUrl)}" target="_blank" rel="noreferrer">Open primary source</a>` : ''}<button onclick="selectFormation('${esc(p.formation_id)}')">Use in alignment lab</button></div>`);
  return circle;
}

function applyFilters() {
  if (!collection) return;
  const query = $('search').value.trim().toLowerCase();
  const min = Number($('yearMin').value || -Infinity), max = Number($('yearMax').value || Infinity);
  const country = $('country').value, usOnly = $('usOnly').checked;
  visibleFeatures = collection.features.filter(f => {
    const p = f.properties;
    const hay = `${p.place} ${p.region} ${p.country} ${p.county}`.toLowerCase();
    return p.year >= min && p.year <= max && (!country || p.country_code === country) && (!usOnly || p.country_code === 'US') && (!query || hay.includes(query));
  });
  markerLayer.clearLayers();
  visibleFeatures.forEach(f => marker(f).addTo(markerLayer));
  $('visibleCount').textContent = visibleFeatures.length.toLocaleString();
}

window.selectFormation = id => {
  selected = collection.features.find(f => f.properties.formation_id === id);
  if (!selected) return;
  const p = selected.properties;
  $('selectedLabel').textContent = `${p.date_iso} · ${p.place}, ${p.region || p.country}`;
  $('drawRay').disabled = false;
  map.closePopup();
};

function destination([lat, lon], bearing, distanceKm) {
  const R = 6371.0088, p1 = lat*Math.PI/180, l1 = lon*Math.PI/180, t = bearing*Math.PI/180, d = distanceKm/R;
  const p2 = Math.asin(Math.sin(p1)*Math.cos(d)+Math.cos(p1)*Math.sin(d)*Math.cos(t));
  const l2 = l1+Math.atan2(Math.sin(t)*Math.sin(d)*Math.cos(p1),Math.cos(d)-Math.sin(p1)*Math.sin(p2));
  return [p2*180/Math.PI, ((l2*180/Math.PI+540)%360)-180];
}
function distanceBearing(a,b) {
  const rad=x=>x*Math.PI/180, [p1,l1,p2,l2]=[...a,...b].map(rad), dp=p2-p1, dl=l2-l1;
  const h=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
  const d=6371.0088*2*Math.asin(Math.min(1,Math.sqrt(h)));
  const t=Math.atan2(Math.sin(dl)*Math.cos(p2),Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(dl));
  return [d,(t*180/Math.PI+360)%360];
}
const angleDiff=(a,b)=>Math.abs((a-b+180)%360-180);

function drawRay() {
  if (!selected) return;
  const origin=[selected.geometry.coordinates[1],selected.geometry.coordinates[0]], bearing=Number($('bearing').value)%360;
  const range=Number($('range').value), corridor=Number($('corridor').value), both=$('bidirectional').checked;
  const points=both?[destination(origin,bearing+180,range),destination(origin,bearing,range)]:[origin,destination(origin,bearing,range)];
  if (rayLayer) rayLayer.remove(); if (hitLayer) hitLayer.remove();
  rayLayer=L.polyline(points,{color:'#54d6c2',weight:3,dashArray:'8 7'}).addTo(map);
  const hits=[];
  collection.features.forEach(f=>{
    if(f===selected)return; const target=[f.geometry.coordinates[1],f.geometry.coordinates[0]]; const [d,b]=distanceBearing(origin,target);
    const diff=Math.min(angleDiff(b,bearing),both?angleDiff(b,bearing+180):999); const cross=Math.abs(d*Math.sin(diff*Math.PI/180)); const along=d*Math.cos(diff*Math.PI/180);
    if(along>=0&&along<=range&&cross<=corridor)hits.push({f,d,cross});
  });
  hits.sort((a,b)=>a.cross-b.cross);
  hitLayer=L.layerGroup(hits.map(h=>L.circleMarker([h.f.geometry.coordinates[1],h.f.geometry.coordinates[0]],{radius:7,color:'#fff',weight:2,fillColor:'#f6ad55',fillOpacity:.9}).bindTooltip(`${h.f.properties.place}: ${h.cross.toFixed(2)} km cross-track`))).addTo(map);
  $('hitSummary').textContent=`${hits.length} catalog point${hits.length===1?'':'s'} fall inside this corridor. This is exploratory and uncorrected for clustering or multiple testing.`;
  $('exportRay').disabled=false; map.fitBounds(rayLayer.getBounds(),{padding:[30,30]});
}

function exportRay() {
  if(!selected)return; const origin=[selected.geometry.coordinates[1],selected.geometry.coordinates[0]],b=Number($('bearing').value)%360,r=Number($('range').value),both=$('bidirectional').checked;
  const pts=both?[destination(origin,b+180,r),destination(origin,b,r)]:[origin,destination(origin,b,r)]; const coords=pts.map(p=>`${p[1]},${p[0]},0`).join(' ');
  const kml=`<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>${esc(selected.properties.formation_id)} bearing ${b}</name><LineString><tessellate>1</tessellate><coordinates>${coords}</coordinates></LineString></Placemark></Document></kml>`;
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([kml],{type:'application/vnd.google-earth.kml+xml'})); a.download=`${selected.properties.formation_id}_bearing_${b}.kml`; a.click(); URL.revokeObjectURL(a.href);
}

$('overlayFile').addEventListener('change', event=>{ const file=event.target.files[0]; if(!file)return; const reader=new FileReader(); reader.onload=()=>{overlayDataUrl=reader.result;overlayClicks=[];$('overlayStatus').textContent='Image ready. Click southwest, then northeast.'}; reader.readAsDataURL(file); });
map.on('click', event=>{ if(!overlayDataUrl||overlayClicks.length>=2)return; overlayClicks.push(event.latlng); if(overlayClicks.length===1){$('overlayStatus').textContent='Southwest corner set. Click northeast.';return;} if(imageOverlay)imageOverlay.remove(); imageOverlay=L.imageOverlay(overlayDataUrl,L.latLngBounds(overlayClicks),{opacity:Number($('overlayOpacity').value)}).addTo(map); $('overlayStatus').textContent='Local overlay placed. Use opacity to compare it with the basemap.'; });
$('overlayOpacity').addEventListener('input',()=>imageOverlay&&imageOverlay.setOpacity(Number($('overlayOpacity').value)));
$('clearOverlay').addEventListener('click',()=>{if(imageOverlay)imageOverlay.remove();imageOverlay=null;overlayDataUrl=null;overlayClicks=[];$('overlayFile').value='';$('overlayStatus').textContent='No image loaded.'});
$('drawRay').addEventListener('click',drawRay); $('exportRay').addEventListener('click',exportRay);
['search','yearMin','yearMax','country','usOnly'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',applyFilters));

fetch('data/formations.geojson').then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}).then(data=>{
  collection=data; const years=data.features.map(f=>f.properties.year); $('yearMin').value=Math.min(...years); $('yearMax').value=Math.max(...years);
  const countries=[...new Map(data.features.map(f=>[f.properties.country_code,f.properties.country])).entries()].filter(x=>x[0]).sort((a,b)=>a[1].localeCompare(b[1]));
  countries.forEach(([code,name])=>$('country').add(new Option(name,code))); $('totalCount').textContent=data.features.length.toLocaleString(); $('usCount').textContent=data.features.filter(f=>f.properties.country_code==='US').length.toLocaleString(); applyFilters();
}).catch(error=>{$('visibleCount').textContent='Error';$('hitSummary').textContent=`Could not load map data: ${error.message}. Serve this folder with a local web server.`});
