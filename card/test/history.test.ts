import assert from "node:assert/strict";
import { test } from "node:test";
import { chartGeometry, type Sample } from "../src/history.ts";

test("returns null on empty input", () => {
  assert.equal(chartGeometry([], 20, 24), null);
  assert.equal(chartGeometry([{ t: 1, op: null, sp: null }], null, null), null);
});

test("inverts temperature axis and builds paths", () => {
  const s: Sample[] = [
    { t: 0, op: 21, sp: 20 },
    { t: 1000, op: 23, sp: 20 },
  ];
  const g = chartGeometry(s, 20, 24, 100, 80, 0);
  assert.ok(g);
  // value range = [min 20, max 24] (band+samples), no pad
  assert.equal(g!.vMin, 20);
  assert.equal(g!.vMax, 24);
  // higher temp -> smaller y (inverted); op goes 21->23 so y decreases
  const ys = g!.opPath.split(" ").map((p) => parseFloat(p.split(",")[1]));
  assert.ok(ys[0] > ys[1]);
  // band: high(24)=top y0, low(20)=bottom y80
  assert.equal(g!.bandTop, 0);
  assert.equal(g!.bandBottom, 80);
  // two points each
  assert.equal(g!.opPath.split(" ").length, 2);
  assert.equal(g!.spPath.split(" ").length, 2);
});

test("skips null points in a series", () => {
  const s: Sample[] = [
    { t: 0, op: 21, sp: null },
    { t: 1, op: null, sp: 20 },
    { t: 2, op: 22, sp: 20 },
  ];
  const g = chartGeometry(s, null, null, 100, 80, 0);
  assert.ok(g);
  assert.equal(g!.opPath.split(" ").length, 2); // two non-null op
  assert.equal(g!.spPath.split(" ").length, 2); // two non-null sp
});
