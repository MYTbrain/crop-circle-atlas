import assert from "node:assert/strict";
import test from "node:test";

import {
  angularDifference,
  bearingLateralUncertainty,
  crossAlongTrack,
  destination,
  distanceBearing,
} from "../web/atlas-geodesy.mjs";

test("angular difference wraps through zero", () => {
  assert.equal(angularDifference(0, 359), 1);
  assert.equal(angularDifference(359, 0), 1);
  assert.equal(angularDifference(1, 181), 180);
});

test("bearing uncertainty produces distance-dependent lateral error", () => {
  assert.ok(Math.abs(bearingLateralUncertainty(500, 22.5) - 191.2) < 0.5);
});

test("spherical cross and along track match a generated ray", () => {
  const origin = [40, -100];
  const onAxis = destination(origin, 90, 250);
  const result = crossAlongTrack(origin, onAxis, 90);
  assert.ok(Math.abs(result.crossTrackKm) < 1e-6);
  assert.ok(Math.abs(result.alongTrackKm - 250) < 1e-5);
});

test("spherical cross track measures a ten kilometre offset", () => {
  const origin = [40, -100];
  const onAxis = destination(origin, 90, 250);
  const target = destination(onAxis, 0, 10);
  const result = crossAlongTrack(origin, target, 90);
  assert.ok(Math.abs(Math.abs(result.crossTrackKm) - 10) < 0.05);
  assert.ok(Math.abs(result.alongTrackKm - 250) < 0.5);
});

test("distance and bearing remain correct across the antimeridian", () => {
  const [distanceKm, bearing] = distanceBearing([0, 179.5], [0, -179.5]);
  assert.ok(Math.abs(distanceKm - 111.195) < 0.05);
  assert.ok(Math.abs(bearing - 90) < 1e-8);
});
