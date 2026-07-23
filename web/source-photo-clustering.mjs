export const SOURCE_PHOTO_CLUSTER_CONFIG = Object.freeze([
  Object.freeze({ maxZoom: 2, radiusPx: 32, bufferPx: 50 }),
  Object.freeze({ maxZoom: 4, radiusPx: 70, bufferPx: 70 }),
  Object.freeze({ maxZoom: 7, radiusPx: 90, bufferPx: 80 }),
  Object.freeze({ maxZoom: 10, radiusPx: 64, bufferPx: 70 }),
  Object.freeze({ maxZoom: Infinity, radiusPx: 18, bufferPx: 40 }),
]);

const rerenderInstallations = new WeakMap();

export function sourcePhotoClusterSettings(zoom) {
  const numericZoom = Number.isFinite(Number(zoom)) ? Number(zoom) : 0;
  return SOURCE_PHOTO_CLUSTER_CONFIG.find((entry) => numericZoom <= entry.maxZoom)
    || SOURCE_PHOTO_CLUSTER_CONFIG.at(-1);
}

export function filterSourcePhotoLocations(points, visibleFormationIds = null, mappedOverlayIds = null) {
  const visible = visibleFormationIds ? new Set(visibleFormationIds) : null;
  const mapped = mappedOverlayIds ? new Set(mappedOverlayIds) : new Set();
  const unique = new Map();
  for (const point of points || []) {
    const formationId = String(point?.formationId || '');
    if (!formationId || (visible && !visible.has(formationId)) || mapped.has(formationId)) continue;
    const latitude = Number(point.latitude);
    const longitude = Number(point.longitude);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)
        || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) continue;
    const prior = unique.get(formationId);
    if (!prior || Number(point.imageCount || 0) > Number(prior.imageCount || 0)) {
      unique.set(formationId, {
        ...point,
        formationId,
        latitude,
        longitude,
        imageCount: Math.max(0, Number(point.imageCount || 0)),
        selected: Boolean(point.selected || prior?.selected),
      });
    } else if (point.selected && !prior.selected) {
      unique.set(formationId, { ...prior, selected: true });
    }
  }
  return [...unique.values()].sort((left, right) => left.formationId.localeCompare(right.formationId));
}

export function clusterSourcePhotoLocations(points, {
  zoom,
  project,
  width,
  height,
  settings = sourcePhotoClusterSettings(zoom),
} = {}) {
  if (typeof project !== 'function') throw new TypeError('project must be a function');
  const viewportWidth = Math.max(0, Number(width || 0));
  const viewportHeight = Math.max(0, Number(height || 0));
  const radius = Math.max(1, Number(settings.radiusPx || 1));
  const buffer = Math.max(0, Number(settings.bufferPx || 0));
  const projected = [];

  for (const point of filterSourcePhotoLocations(points)) {
    const screen = project(point);
    const x = Number(screen?.x);
    const y = Number(screen?.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    if (x < -buffer || y < -buffer || x > viewportWidth + buffer || y > viewportHeight + buffer) continue;
    projected.push({ ...point, x, y });
  }
  projected.sort((left, right) => left.x - right.x || left.y - right.y
    || left.formationId.localeCompare(right.formationId));

  const clusters = [];
  for (const point of projected) {
    let nearest = null;
    let nearestDistance = Infinity;
    for (const cluster of clusters) {
      const distance = Math.hypot(point.x - cluster.x, point.y - cluster.y);
      if (distance <= radius && distance < nearestDistance) {
        nearest = cluster;
        nearestDistance = distance;
      }
    }
    if (!nearest) {
      clusters.push({
        x: point.x,
        y: point.y,
        minX: point.x,
        maxX: point.x,
        minY: point.y,
        maxY: point.y,
        records: [point],
      });
      continue;
    }
    const count = nearest.records.length;
    nearest.x = ((nearest.x * count) + point.x) / (count + 1);
    nearest.y = ((nearest.y * count) + point.y) / (count + 1);
    nearest.minX = Math.min(nearest.minX, point.x);
    nearest.maxX = Math.max(nearest.maxX, point.x);
    nearest.minY = Math.min(nearest.minY, point.y);
    nearest.maxY = Math.max(nearest.maxY, point.y);
    nearest.records.push(point);
  }

  return clusters.map((cluster) => {
    cluster.records.sort((left, right) => String(left.record?.date_iso || '').localeCompare(
      String(right.record?.date_iso || ''),
    ) || left.formationId.localeCompare(right.formationId));
    const locationRoleCounts = {};
    let imageCount = 0;
    let selected = false;
    for (const record of cluster.records) {
      const role = String(record.locationRole || 'unresolved');
      locationRoleCounts[role] = (locationRoleCounts[role] || 0) + 1;
      imageCount += record.imageCount;
      selected ||= record.selected;
    }
    const latitudes = cluster.records.map((record) => record.latitude);
    const longitudes = cluster.records.map((record) => record.longitude);
    return {
      ...cluster,
      formationIds: cluster.records.map((record) => record.formationId),
      reportCount: cluster.records.length,
      imageCount,
      locationRoleCounts,
      geographicBounds: {
        south: Math.min(...latitudes),
        west: Math.min(...longitudes),
        north: Math.max(...latitudes),
        east: Math.max(...longitudes),
      },
      selected,
    };
  }).sort((left, right) => left.x - right.x || left.y - right.y
    || left.formationIds[0].localeCompare(right.formationIds[0]));
}

export function sourcePhotoMarkerPresentation(cluster, zoom) {
  const reportCount = Number(cluster?.reportCount || 0);
  const clusterMarker = Number(zoom) <= 7 || reportCount > 1;
  const sizeTier = reportCount >= 50 ? 'large' : reportCount >= 10 ? 'medium' : 'small';
  let label = 'PIC';
  if (Number(zoom) <= 4) label = String(reportCount);
  else if (clusterMarker) label = `PIC ${reportCount}`;
  return { kind: clusterMarker ? 'cluster' : 'individual', label, sizeTier };
}

export function sourcePhotoClusterAction(cluster, zoom) {
  const reportCount = Number(cluster?.reportCount || 0);
  if (reportCount <= 1) return Number(zoom) < 8 ? 'zoom' : 'open_archive';
  const screenExtent = Math.max(
    Number(cluster?.maxX || 0) - Number(cluster?.minX || 0),
    Number(cluster?.maxY || 0) - Number(cluster?.minY || 0),
  );
  return screenExtent > 8 && Number(zoom) < 11 ? 'zoom' : 'choose';
}

export function installDebouncedSourcePhotoRerender(map, callback, delayMs = 90) {
  if (rerenderInstallations.has(map)) return rerenderInstallations.get(map);
  let timer = null;
  const handler = () => {
    clearTimeout(timer);
    timer = setTimeout(callback, delayMs);
  };
  const installation = { handler, eventNames: 'zoomend moveend' };
  rerenderInstallations.set(map, installation);
  map.on(installation.eventNames, handler);
  return installation;
}
