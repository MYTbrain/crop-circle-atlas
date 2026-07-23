import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  clusterSourcePhotoLocations,
  filterSourcePhotoLocations,
  installDebouncedSourcePhotoRerender,
  sourcePhotoClusterAction,
  sourcePhotoClusterSettings,
  sourcePhotoMarkerPresentation,
} from '../web/source-photo-clustering.mjs';

const appSource = readFileSync(new URL('../web/app.js', import.meta.url), 'utf8');
const htmlSource = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8');
const cssSource = readFileSync(new URL('../web/styles.css', import.meta.url), 'utf8');

function point(id, x, y, imageCount = 1, extra = {}) {
  return {
    formationId: id,
    latitude: y / 10,
    longitude: x / 10,
    imageCount,
    locationRole: 'locality_reference',
    screen: { x, y },
    ...extra,
  };
}

function cluster(points, zoom = 9, width = 1200, height = 800) {
  return clusterSourcePhotoLocations(points, {
    zoom,
    width,
    height,
    project: (entry) => entry.screen,
  });
}

test('world view renders a bounded number of regional clusters', () => {
  const points = [];
  for (let regionRow = 0; regionRow < 4; regionRow += 1) {
    for (let regionColumn = 0; regionColumn < 6; regionColumn += 1) {
      for (let member = 0; member < 40; member += 1) {
        points.push(point(
          `world-${regionRow}-${regionColumn}-${member}`,
          70 + regionColumn * 235 + (member % 8) * 2,
          80 + regionRow * 205 + Math.floor(member / 8) * 2,
        ));
      }
    }
  }
  const clusters = cluster(points, 2, 1440, 900);
  assert.ok(clusters.length >= 15, `expected regional coverage, got ${clusters.length}`);
  assert.ok(clusters.length <= 35, `expected at most 35 markers, got ${clusters.length}`);
  assert.ok(clusters.length < points.length / 20);
});

test('nearby non-identical coordinates cluster', () => {
  const clusters = cluster([point('a', 100, 100), point('b', 145, 126)], 9);
  assert.equal(clusters.length, 1);
  assert.deepEqual(clusters[0].formationIds, ['a', 'b']);
});

test('distant coordinates remain separate', () => {
  assert.equal(cluster([point('a', 100, 100), point('b', 400, 400)], 9).length, 2);
});

test('cluster totals count unique reports and images', () => {
  const clusters = cluster([
    point('a', 100, 100, 3),
    point('a', 101, 101, 3),
    point('b', 120, 115, 4),
  ], 9);
  assert.equal(clusters[0].reportCount, 2);
  assert.equal(clusters[0].imageCount, 7);
  assert.deepEqual(clusters[0].locationRoleCounts, { locality_reference: 2 });
  assert.ok(clusters[0].geographicBounds.north >= clusters[0].geographicBounds.south);
});

test('registered-overlay formations stay out of availability markers', () => {
  const filtered = filterSourcePhotoLocations(
    [point('registered', 10, 10), point('available', 20, 20)],
    null,
    new Set(['registered']),
  );
  assert.deepEqual(filtered.map((entry) => entry.formationId), ['available']);
});

test('reviewed overlays retain the dominant interactive pane', () => {
  assert.match(appSource, /sourcePhotoPane'\)\.style\.zIndex = '440'/);
  assert.match(appSource, /overlayFootprintPane'\)\.style\.zIndex = '520'/);
  assert.match(appSource, /=== 'candidate_field' \? 0 : 1/);
  assert.match(appSource, /footprint\.on\('click', load\)/);
  assert.match(appSource, /marker\.on\('click', load\)/);
});

test('cluster interaction chooses zoom, archive, or chooser deterministically', () => {
  assert.equal(sourcePhotoClusterAction({ reportCount: 1 }, 4), 'zoom');
  assert.equal(sourcePhotoClusterAction({ reportCount: 1 }, 11), 'open_archive');
  assert.equal(sourcePhotoClusterAction({ reportCount: 3, minX: 0, maxX: 40, minY: 0, maxY: 3 }, 7), 'zoom');
  assert.equal(sourcePhotoClusterAction({ reportCount: 3, minX: 0, maxX: 2, minY: 0, maxY: 2 }, 12), 'choose');
});

test('high zoom reveals an isolated source-photo dot without a text label', () => {
  assert.deepEqual(sourcePhotoMarkerPresentation({ reportCount: 1 }, 11), {
    kind: 'individual', sizeTier: 'small',
  });
  assert.equal(sourcePhotoMarkerPresentation({ reportCount: 2 }, 11).kind, 'cluster');
  assert.equal('label' in sourcePhotoMarkerPresentation({ reportCount: 100 }, 2), false);
});

test('filter changes alter cluster membership', () => {
  const points = [point('a', 100, 100), point('b', 120, 110), point('c', 140, 120)];
  const filtered = filterSourcePhotoLocations(points, new Set(['a', 'c']));
  assert.deepEqual(filtered.map((entry) => entry.formationId), ['a', 'c']);
  assert.equal(cluster(filtered, 9)[0].reportCount, 2);
});

test('repeated installation does not duplicate map listeners', async () => {
  const handlers = [];
  const map = { on(events, handler) { handlers.push({ events, handler }); } };
  let calls = 0;
  const first = installDebouncedSourcePhotoRerender(map, () => { calls += 1; }, 0);
  const second = installDebouncedSourcePhotoRerender(map, () => { calls += 10; }, 0);
  assert.equal(first, second);
  assert.equal(handlers.length, 1);
  assert.equal(handlers[0].events, 'zoomend moveend');
  handlers[0].handler();
  handlers[0].handler();
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(calls, 1);
});

test('selected-report clusters retain a visible selection state', () => {
  const clusters = cluster([
    point('a', 100, 100, 1, { selected: true }),
    point('b', 120, 110),
  ], 9);
  assert.equal(clusters[0].selected, true);
  assert.match(cssSource, /source-photo-dot\.is-selected/);
  assert.match(appSource, /cluster\.selected \? ' is-selected'/);
});

test('mobile layout and disclosure remain usable', () => {
  assert.match(cssSource, /@media \(max-width:780px\)/);
  assert.match(appSource, /\? 26 : presentation\.sizeTier === 'medium' \? 22 : 18/);
  assert.match(htmlSource, /Availability dots are clustered when zoomed out\./);
  assert.match(cssSource, /\.map-marker-legend \{ max-width:205px;/);
  assert.equal(sourcePhotoClusterSettings(10).radiusPx >= 55, true);
});

test('normal map markers use semantic dots without visible badge abbreviations', () => {
  assert.match(appSource, /className: `source-photo-dot \$\{markerClass\}/);
  assert.match(appSource, /html: ''/);
  assert.match(appSource, /L\.circleMarker\(center/);
  assert.doesNotMatch(appSource, /registered-image-marker/);
  assert.doesNotMatch(appSource, /aria-hidden="true">PIC/);
  assert.match(appSource, /Source-photo availability only; not a registered image placement\./);
  assert.match(appSource, /Rough locality reference; not the formation site\./);
  assert.match(htmlSource, /solid green dots show source-photo availability only/i);
  assert.match(htmlSource, /solid yellow dots mark candidate, reviewed, or registered locations/i);
  assert.doesNotMatch(htmlSource, /<strong>(PIC|IMG|GEO)<\/strong>/);
  assert.match(cssSource, /\.source-photo-dot \{[^}]*background:#1d9b68/);
  assert.match(cssSource, /\.map-marker-legend/);
});
