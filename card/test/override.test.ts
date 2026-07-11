import { test } from "node:test";
import assert from "node:assert/strict";
import {
  clampLabel,
  clockLabel,
  holdView,
  minutesUntil,
  presetChip,
  resumeSchedule,
} from "../src/override.ts";
import type { HomeAssistant } from "../src/ha-types.ts";

const NOW = Date.parse("2026-07-11T21:15:00Z");

test("minutesUntil: rounds remaining minutes, floors at 0, null when absent", () => {
  assert.equal(minutesUntil("2026-07-11T22:00:00Z", NOW), 45);
  assert.equal(minutesUntil("2026-07-11T21:15:20Z", NOW), 0); // <30 s rounds to 0
  assert.equal(minutesUntil("2026-07-11T21:00:00Z", NOW), 0); // already past -> clamped
  assert.equal(minutesUntil(null, NOW), null);
  assert.equal(minutesUntil(undefined, NOW), null);
  assert.equal(minutesUntil("not-a-date", NOW), null);
});

test("holdView: pill shows remaining time from override_expires_at", () => {
  const v = holdView("de", 22.5, "schedule", "2026-07-11T22:00:00Z", NOW);
  assert.equal(v.label, "Manuell 22.5°");
  assert.equal(v.minutes, 45);
  assert.equal(v.permanent, false);
});

test("holdView: permanent policy drops the countdown", () => {
  const v = holdView("de", 22.5, "permanent", null, NOW);
  assert.equal(v.label, "Manuell (dauerhaft)");
  assert.equal(v.minutes, null);
  assert.equal(v.permanent, true);
  assert.equal(
    holdView("en", 21, "permanent", null, NOW).label,
    "Manual (permanent)",
  );
});

test("holdView: missing setpoint still labels the hold", () => {
  assert.equal(
    holdView("en", null, "timer", "2026-07-11T22:00:00Z", NOW).label,
    "Manual",
  );
});

test("clampLabel: explains the clamp from request vs effective setpoint", () => {
  assert.equal(clampLabel("de", 22.5, 24), "22.5° statt 24.0° (Normgrenze)");
  assert.equal(clampLabel("en", 22.5, 24), "22.5° instead of 24.0° (norm limit)");
  // falls back to the generic label when a value is missing
  assert.equal(clampLabel("de", null, 24), "Sollwert geklemmt");
  assert.equal(clampLabel("en", 22.5, null), "Setpoint clamped");
});

test("clockLabel: null for missing/invalid, HH:MM otherwise", () => {
  assert.equal(clockLabel(null), null);
  assert.equal(clockLabel("nope"), null);
  const s = clockLabel("2026-07-11T22:00:00Z", "en-GB");
  assert.equal(typeof s, "string");
  assert.match(s as string, /\d{2}:\d{2}/);
});

test("presetChip: live when preset set and preset section off; else null", () => {
  assert.deepEqual(presetChip("en", "eco", false), { key: "eco", label: "Eco" });
  assert.deepEqual(presetChip("de", "boost", false), { key: "boost", label: "Boost" });
  // none / section-on / null -> no chip
  assert.equal(presetChip("en", "none", false), null);
  assert.equal(presetChip("en", "eco", true), null);
  assert.equal(presetChip("en", null, false), null);
  // unknown preset keeps its raw key as the label
  assert.deepEqual(presetChip("en", "party", false), { key: "party", label: "party" });
});

test("resumeSchedule: X calls poise.resume_schedule for the entity", () => {
  const calls: Array<[string, string, Record<string, unknown> | undefined]> = [];
  const hass = {
    states: {},
    callService: (
      domain: string,
      service: string,
      data?: Record<string, unknown>,
    ) => {
      calls.push([domain, service, data]);
      return Promise.resolve();
    },
  } as unknown as HomeAssistant;
  resumeSchedule(hass, "climate.wohnzimmer");
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], [
    "poise",
    "resume_schedule",
    { entity_id: "climate.wohnzimmer" },
  ]);
});
