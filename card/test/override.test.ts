import { test } from "node:test";
import assert from "node:assert/strict";
import {
  airHint,
  clampLabel,
  clockLabel,
  heldSetpoint,
  holdDirection,
  holdOrigin,
  holdView,
  minutesUntil,
  presetChip,
  resumeSchedule,
} from "../src/override.ts";
import { DIAL, setpointForKey } from "../src/dial.ts";
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

test("holdDirection: maps hvac_action to a localized direction word (V4)", () => {
  assert.equal(holdDirection("de", "cooling"), "kühlt");
  assert.equal(holdDirection("de", "heating"), "heizt");
  assert.equal(holdDirection("de", "drying"), "entfeuchtet");
  assert.equal(holdDirection("en", "cooling"), "cooling");
  assert.equal(holdDirection("en", "COOLING"), "cooling"); // case-insensitive
  // idle / off / unknown / absent -> no direction shown
  assert.equal(holdDirection("de", "idle"), null);
  assert.equal(holdDirection("de", "off"), null);
  assert.equal(holdDirection("de", null), null);
  assert.equal(holdDirection("de", undefined), null);
});

test("holdView: exposes the direction from hvac_action (V4)", () => {
  // the reported defect: a cooling override must read "kühlt" on the pill
  const cool = holdView("de", 22, "schedule", "2026-07-11T22:00:00Z", NOW, "cooling");
  assert.equal(cool.direction, "kühlt");
  assert.equal(cool.label, "Manuell 22.0°");
  // permanent hold still carries the direction
  const perm = holdView("de", 22, "permanent", null, NOW, "heating");
  assert.equal(perm.direction, "heizt");
  // no action -> null direction (back-compatible default)
  assert.equal(holdView("de", 22, "schedule", null, NOW).direction, null);
});

test("holdOrigin: maps override_reason to a localized provenance (K3)", () => {
  assert.equal(holdOrigin("de", "device_adopt_mode"), "Gerät");
  assert.equal(holdOrigin("de", "device_adopt_setpoint"), "Gerät");
  assert.equal(holdOrigin("de", "ui_setpoint"), "App");
  assert.equal(holdOrigin("en", "device_adopt_setpoint"), "device");
  assert.equal(holdOrigin("en", "ui_setpoint"), "app");
  // frost_rescue / unknown / absent -> no origin shown
  assert.equal(holdOrigin("de", "frost_rescue"), null);
  assert.equal(holdOrigin("de", null), null);
  assert.equal(holdOrigin("de", undefined), null);
});

test("holdView: carries the hold origin from override_reason (K3)", () => {
  const dev = holdView(
    "de",
    22,
    "schedule",
    "2026-07-11T22:00:00Z",
    NOW,
    "cooling",
    "device_adopt_mode",
  );
  assert.equal(dev.origin, "Gerät");
  const app = holdView("en", 22, "permanent", null, NOW, null, "ui_setpoint");
  assert.equal(app.origin, "app");
  // back-compatible default: no reason -> null origin
  assert.equal(holdView("de", 22, "schedule", null, NOW).origin, null);
});

test("airHint: shows air temperature only when it diverges from operative (V3a/D1)", () => {
  assert.equal(airHint(21.4, 22.1), 22.1); // 0.7 K gap -> show air
  assert.equal(airHint(21.4, 21.5), null); // 0.1 K < 0.3 threshold -> hide
  assert.equal(airHint(22.0, 22.3), 22.3); // exactly at threshold -> show
  assert.equal(airHint(22.0, 22.0), null); // identical -> hide
  // absent values -> null (never invents a hint)
  assert.equal(airHint(null, 22.1), null);
  assert.equal(airHint(21.4, null), null);
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

test("heldSetpoint: reads the commanded `temperature`, ignores the heat_sp band edge", () => {
  // VT#1980 — the UI must mirror internal (written) state. `temperature` is the
  // clamped write target (= target_temperature); `heat_sp` is only the
  // comfort-band lower edge and is always set.
  assert.equal(heldSetpoint({ temperature: 24, heat_sp: 20 }), 24);
  assert.equal(heldSetpoint({ temperature: "22.5", heat_sp: 20 }), 22.5); // string coercion
  // graceful degradation: no `temperature` -> null (never falls back to heat_sp)
  assert.equal(heldSetpoint({ heat_sp: 20 }), null);
  assert.equal(heldSetpoint({}), null);
});

test("hold-pill + clamp read `temperature` (24°), not the heat_sp band edge (20°)", () => {
  // Regression guard for ADR-0059 Defekt 1: with an upward clamp the requested
  // 26° is capped to the held/effective 24° (`temperature`), while `heat_sp` is
  // the 20° band edge. The card reads these attributes via heldSetpoint(a); the
  // Hold-pill and clamp chip must reflect 24 (and 26 as requested), never 20.
  const a = {
    override_active: true,
    override_clamped: true,
    temperature: 24,
    override_requested: 26,
    heat_sp: 20,
    cool_sp: 24,
  };
  const held = heldSetpoint(a);
  assert.equal(held, 24); // NOT 20 (heat_sp band edge)

  // _holdPill: holdView(lang, heldSetpoint(a), …) -> "Manuell 24.0°", not 20.0°
  assert.equal(
    holdView("de", held, undefined, undefined, NOW).label,
    "Manuell 24.0°",
  );

  // clamp chip: clampLabel(lang, heldSetpoint(a), num(override_requested))
  //  -> effective 24 vs requested 26, not "20° statt 26°"
  assert.equal(
    clampLabel("de", held, a["override_requested"]),
    "24.0° statt 26.0° (Normgrenze)",
  );
});

// num() mirrors poise-card.ts's null-safe numeric coercion (heldSetpoint uses
// the same rules internally) so these tests exercise the card's own idioms.
function num(v: unknown): number | null {
  const n = typeof v === "string" ? parseFloat(v) : (v as number);
  return typeof n === "number" && !Number.isNaN(n) ? n : null;
}

test("dial centre setpoint shows the commanded `temperature` (23°), not the heat_sp band edge (20.2°)", () => {
  // ADR-0059 Defekt 1 (v0.162.2): the MAIN dial number + handle marker must
  // read the held/commanded setpoint (`temperature`). Live: a 23° hold exposes
  // heat_sp:20.2 / cool_sp:27.1 as the comfort-band edges — the dial previously
  // rendered 20.2 (the band lower edge) instead of 23 ("Text zeigt 20,2 statt 23").
  const a = {
    temperature: 23,
    heat_sp: 20.2,
    cool_sp: 27.1,
    override_active: true,
  };
  // The dial's shown setpoint = `_pending ?? heldSetpoint(a) ?? op ?? min`
  // (poise-card.ts _dial). No drag/pending here, so it resolves via heldSetpoint.
  const pending: number | null = null;
  const op = 22.4; // operative temperature
  const dialMin = 16;
  const shown = pending ?? heldSetpoint(a) ?? op ?? dialMin;
  assert.equal(shown, 23); // NOT 20.2 (heat_sp band edge)

  // Regression guard: the OLD idiom (heat_sp first) resolved to the band edge.
  const oldShown = num(a.heat_sp) ?? num(a.temperature);
  assert.equal(oldShown, 20.2);
});

test("history graph setpoint series plots `temperature` (23°), not the heat_sp band edge (20.2°)", () => {
  // ADR-0059 Defekt 1 (v0.162.2): the chart setpoint line reads the commanded
  // `temperature` per history sample (poise-card.ts _loadHistory), never the
  // `heat_sp` band edge (the comfort band is shaded separately from low/high).
  const attrs = { temperature: 23, heat_sp: 20.2, cool_sp: 27.1 };
  const sp = num(attrs.temperature); // the new Sample.sp extraction
  assert.equal(sp, 23); // NOT 20.2

  // Regression guard: the OLD idiom (heat_sp first) plotted the band edge.
  const oldSp = num(attrs.heat_sp) ?? num(attrs.temperature);
  assert.equal(oldSp, 20.2);
});

test("+/- nudge and arrow keys re-base from the held setpoint (23°), not the heat_sp edge (20.2°)", () => {
  // ADR-0059 Defekt 1 (v0.162.2): after the dial was fixed to SHOW heldSetpoint,
  // the +/- buttons (_setpoint) and arrow keys (_onKey) must re-base from the
  // SAME held/commanded `temperature`, not the `heat_sp` band edge. A single
  // +0.5 step on a 23° hold must land on 23.5, never ~20.7 (20.2 edge + step).
  const a = { temperature: 23, heat_sp: 20.2, cool_sp: 27.1, override_active: true };
  const step = 0.5;
  const pending: number | null = null;

  // New base, mirroring poise-card.ts _setpoint/_onKey: `_pending ?? heldSetpoint(a) ?? …`.
  const base = pending ?? heldSetpoint(a) ?? 21;
  assert.equal(base, 23); // held/commanded temperature, NOT the 20.2 band edge

  // +/- button path (_setpoint): Math.round((cur + delta*step)*10)/10
  assert.equal(Math.round((base + 1 * step) * 10) / 10, 23.5);
  assert.equal(Math.round((base - 1 * step) * 10) / 10, 22.5);

  // arrow-key path (_onKey): setpointForKey(key, cur, step, dialCfg)
  assert.equal(setpointForKey("ArrowUp", base, step, DIAL), 23.5);
  assert.equal(setpointForKey("ArrowDown", base, step, DIAL), 22.5);

  // Regression guard: the OLD heat_sp-first base produced the ~20.7 bug.
  const oldBase = num(a.heat_sp) ?? num(a.temperature);
  assert.equal(oldBase, 20.2);
  assert.equal(Math.round((oldBase + 1 * step) * 10) / 10, 20.7);
});
