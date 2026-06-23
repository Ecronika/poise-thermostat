import assert from "node:assert/strict";
import { test } from "node:test";
import {
  angleToValue,
  arcPath,
  clampAngleToTrack,
  pointToValue,
  polar,
  valueToAngle,
} from "../src/dial.ts";

test("value<->angle round trips across the track", () => {
  assert.equal(valueToAngle(16), 135); // min at start
  assert.equal(valueToAngle(22), 270); // middle -> top
  assert.equal(valueToAngle(28), 405); // max at start+sweep
  assert.ok(Math.abs(angleToValue(270) - 22) < 1e-9);
  for (const v of [16, 18.5, 22, 25, 28]) {
    assert.ok(Math.abs(angleToValue(valueToAngle(v)) - v) < 1e-9);
  }
});

test("value clamps outside range", () => {
  assert.equal(valueToAngle(10), 135); // below min clamps
  assert.equal(valueToAngle(40), 405); // above max clamps
});

test("gap angles clamp to nearer track end", () => {
  // straight down (90°) is the bottom gap centre -> clamps to an end
  const a = clampAngleToTrack(90);
  assert.ok(a === 135 || a === 405);
  // 100° leans toward the 135 (min) end
  assert.equal(clampAngleToTrack(100), 135);
  // 80° leans toward the 405 (max) end
  assert.equal(clampAngleToTrack(80), 405);
});

test("pointToValue: straight up = middle of range", () => {
  // up = -y in screen coords -> atan2(-1,0) = -90 -> 270
  assert.ok(Math.abs(pointToValue(0, -10) - 22) < 1e-9);
});

test("polar + arcPath basics", () => {
  const p = polar(100, 100, 80, 0); // east
  assert.ok(Math.abs(p.x - 180) < 1e-6 && Math.abs(p.y - 100) < 1e-6);
  const d = arcPath(100, 100, 80, 135, 405);
  assert.ok(d.startsWith("M ") && d.includes(" A 80 80 0 1 1 ")); // large-arc flag set
  assert.equal(arcPath(100, 100, 80, 200, 200), ""); // degenerate
});
