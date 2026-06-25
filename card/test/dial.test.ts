import assert from "node:assert/strict";
import { test } from "node:test";
import {
  angleToValue,
  arcPath,
  clampAngleToTrack,
  pointToValue,
  polar,
  setpointForKey,
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

test("setpointForKey steps, pages, snaps and clamps (a11y D2)", () => {
  const c = { min: 16, max: 28, start: 135, sweep: 270 };
  // arrows step by one step in both orientations
  assert.equal(setpointForKey("ArrowUp", 21, 0.5, c), 21.5);
  assert.equal(setpointForKey("ArrowRight", 21, 0.5, c), 21.5);
  assert.equal(setpointForKey("ArrowDown", 21, 0.5, c), 20.5);
  assert.equal(setpointForKey("ArrowLeft", 21, 0.5, c), 20.5);
  // page keys jump five steps
  assert.equal(setpointForKey("PageUp", 21, 0.5, c), 23.5);
  assert.equal(setpointForKey("PageDown", 21, 0.5, c), 18.5);
  // home/end go to the device limits
  assert.equal(setpointForKey("Home", 21, 0.5, c), 16);
  assert.equal(setpointForKey("End", 21, 0.5, c), 28);
  // clamps at the edges, never past the device range
  assert.equal(setpointForKey("ArrowUp", 28, 0.5, c), 28);
  assert.equal(setpointForKey("ArrowDown", 16, 0.5, c), 16);
  // an off-grid current value snaps onto the step grid
  assert.equal(setpointForKey("ArrowUp", 21.2, 0.5, c), 21.5);
  // unrelated keys return null so the caller leaves the event alone
  assert.equal(setpointForKey("Tab", 21, 0.5, c), null);
  assert.equal(setpointForKey("a", 21, 0.5, c), null);
});
