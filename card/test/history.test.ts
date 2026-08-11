import assert from "node:assert/strict";
import { test } from "node:test";
import {
  chartGeometry,
  HIST_REFRESH_MS,
  HIST_RETRY_MS,
  histCurrent,
  histKey,
  shouldLoadHistory,
  type Sample,
} from "../src/history.ts";

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

// --- refresh scheduling (review plan A.1) --------------------------------------

const T = Date.parse("2026-08-11T12:00:00Z");

test("shouldLoadHistory: loads on first use and when entity or hours change", () => {
  assert.equal(shouldLoadHistory(null, histKey("climate.a", 24), T), true);
  const cur = { key: histKey("climate.a", 24), at: T, failedAt: null };
  assert.equal(shouldLoadHistory(cur, histKey("climate.a", 24), T + 1000), false);
  assert.equal(shouldLoadHistory(cur, histKey("climate.b", 24), T + 1000), true);
  // a changed history.hours config re-keys the series (old guard missed this)
  assert.equal(shouldLoadHistory(cur, histKey("climate.a", 6), T + 1000), true);
});

test("shouldLoadHistory: periodic re-sync after the refresh interval", () => {
  const cur = { key: "k", at: T, failedAt: null };
  assert.equal(shouldLoadHistory(cur, "k", T + HIST_REFRESH_MS - 1), false);
  assert.equal(shouldLoadHistory(cur, "k", T + HIST_REFRESH_MS), true);
});

test("shouldLoadHistory: a failed fetch retries after the backoff, not before", () => {
  const failed = { key: "k", at: 0, failedAt: T };
  assert.equal(shouldLoadHistory(failed, "k", T + HIST_RETRY_MS - 1), false);
  assert.equal(shouldLoadHistory(failed, "k", T + HIST_RETRY_MS), true);
  // the retry backoff must be much tighter than the refresh interval
  assert.ok(HIST_RETRY_MS < HIST_REFRESH_MS);
});

test("histCurrent: only the fetch for the current key may commit", () => {
  const cur = { key: "a|24", at: T, failedAt: null };
  assert.equal(histCurrent(cur, "a|24"), true);
  assert.equal(histCurrent(cur, "a|48"), false); // re-keyed while in flight
  assert.equal(histCurrent(null, "a|24"), false); // reset while in flight
});
