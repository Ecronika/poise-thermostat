import assert from "node:assert/strict";
import { test } from "node:test";
import { buildBand, clamp, frac, verdictFor } from "../src/comfort.ts";

test("verdictFor classifies position in band", () => {
  assert.equal(verdictFor(null, 20, 24), "unknown");
  assert.equal(verdictFor(19, 20, 24), "below");
  assert.equal(verdictFor(25, 20, 24), "above");
  assert.equal(verdictFor(20.5, 20, 24), "cool_edge"); // r=0.125 <0.25
  assert.equal(verdictFor(22, 20, 24), "in_band");
  assert.equal(verdictFor(23.5, 20, 24), "warm_edge"); // r=0.875 >0.75
});

test("frac is clamped to 0..1", () => {
  assert.equal(frac(18, 20, 24), 0);
  assert.equal(frac(26, 20, 24), 1);
  assert.equal(frac(22, 20, 24), 0.5);
  assert.equal(frac(5, 5, 5), 0.5); // degenerate axis
});

test("clamp", () => {
  assert.equal(clamp(-1, 0, 1), 0);
  assert.equal(clamp(2, 0, 1), 1);
  assert.equal(clamp(0.4, 0, 1), 0.4);
});

test("buildBand returns null on invalid band", () => {
  assert.equal(buildBand({ operative: 22, setpoint: 22, low: null, high: 24 }), null);
  assert.equal(buildBand({ operative: 22, setpoint: 22, low: 24, high: 20 }), null);
});

test("buildBand computes positions and verdict", () => {
  const b = buildBand({ operative: 22, setpoint: 21.5, low: 20, high: 24, category: "II" });
  assert.ok(b);
  assert.equal(b!.axisLow, 18.5);
  assert.equal(b!.axisHigh, 25.5);
  assert.equal(b!.verdict, "in_band");
  // low at 20 -> (20-18.5)/7 ; operative 22 -> (22-18.5)/7 = 0.5
  assert.ok(Math.abs(b!.operativeFrac! - 0.5) < 1e-9);
  assert.ok(b!.lowFrac < b!.operativeFrac!);
  assert.equal(b!.category, "II");
});
