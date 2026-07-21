import assert from "node:assert/strict";
import test from "node:test";

import { applyOrientationToAlignmentLab } from "../web/georef-atlas-adapter.mjs";

if (!globalThis.CustomEvent) {
  globalThis.CustomEvent = class CustomEvent extends Event {
    constructor(type, options = {}) {
      super(type, options);
      this.detail = options.detail;
    }
  };
}

function fakeRoot(selectedFormationId = "cc_selected") {
  const controls = Object.fromEntries(
    ["bearing", "bearingUncertainty", "bidirectional", "range", "corridor"]
      .map((id) => [id, { value: "", checked: false, dispatchEvent() {} }]),
  );
  return {
    defaultView: { selectedFormationId },
    getElementById(id) { return controls[id] || null; },
    dispatchEvent() {},
    controls,
  };
}

const observation = {
  formation_id: "cc_selected",
  azimuth_true_deg: 359,
  azimuth_uncertainty_deg: 2.5,
  directionality: "forward",
  max_range_km: 500,
  corridor_km: 2,
};

test("registration bridge rejects a different selected formation", () => {
  assert.throws(
    () => applyOrientationToAlignmentLab(observation, fakeRoot("cc_other")),
    /does not match/,
  );
});

test("registration bridge applies bearing and uncertainty to the matching formation", () => {
  const root = fakeRoot();
  applyOrientationToAlignmentLab(observation, root);
  assert.equal(root.controls.bearing.value, "359");
  assert.equal(root.controls.bearingUncertainty.value, "2.5");
  assert.equal(root.controls.bidirectional.checked, false);
  assert.equal(root.controls.range.value, "500");
  assert.equal(root.controls.corridor.value, "2");
});
