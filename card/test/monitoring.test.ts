import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildMonitor,
  caVerdict,
  co2Thresholds,
  co2Verdict,
  comfortMeasure,
  humidityVerdict,
  levelColor,
  pmvVerdict,
  ppdFromPmv,
  tempVerdictAsrOffice,
  tempVerdictComfort,
  ventChip,
} from "../src/monitoring.ts";
import { t } from "../src/localize.ts";

test("co2Verdict uses UBA absolute defaults 1000/2000", () => {
  assert.equal(co2Verdict(null), "unknown");
  assert.equal(co2Verdict(800), "ok");
  assert.equal(co2Verdict(999), "ok");
  assert.equal(co2Verdict(1000), "warn");
  assert.equal(co2Verdict(1999), "warn");
  assert.equal(co2Verdict(2000), "alert");
  assert.equal(co2Verdict(3500), "alert");
});

test("co2Verdict honours custom thresholds, falls back silently on bad input", () => {
  assert.equal(co2Verdict(850, { thresholds: [800, 1500] }), "warn");
  assert.equal(co2Verdict(1600, { thresholds: [800, 1500] }), "alert");
  // descending / too short -> silent UBA fallback (no throw, ADR-0049 §6)
  assert.equal(co2Verdict(1000, { thresholds: [2000, 800] }), "warn");
  assert.equal(co2Verdict(1000, { thresholds: [1000] }), "warn");
});

test("co2 EN 16798 mode offsets thresholds over outdoor", () => {
  // outdoor 420 + rise [800,1350] -> [1220, 1770]
  assert.deepEqual(co2Thresholds({ scheme: "en16798" }), [1220, 1770]);
  assert.equal(co2Verdict(1200, { scheme: "en16798" }), "ok");
  assert.equal(co2Verdict(1300, { scheme: "en16798" }), "warn");
  assert.equal(co2Verdict(1800, { scheme: "en16798" }), "alert");
  assert.deepEqual(
    co2Thresholds({ scheme: "en16798", outdoor: 500 }),
    [1300, 1850],
  );
});

test("humidityVerdict: green 40-60, warn side-bands, alert <30 or >=65", () => {
  assert.equal(humidityVerdict(null), "unknown");
  assert.equal(humidityVerdict(50), "ok");
  assert.equal(humidityVerdict(40), "ok");
  assert.equal(humidityVerdict(60), "ok");
  assert.equal(humidityVerdict(35), "warn");
  assert.equal(humidityVerdict(62), "warn");
  assert.equal(humidityVerdict(29), "alert");
  assert.equal(humidityVerdict(65), "alert");
  assert.equal(humidityVerdict(80), "alert");
  // custom thresholds + silent fallback on non-ascending
  assert.equal(humidityVerdict(45, [40, 50, 60, 70]), "warn");
  assert.equal(humidityVerdict(35, [60, 50, 40, 30]), "warn");
});

test("humidityVerdict ADR-0066: absolute g/m³ drives the dry side", () => {
  // 24 °C / 32 % RH = 6.98 g/m³ -> today wrongly warn; abs says warn is right
  // at 6.98 (<7) but ok at 7.2 — the warm room is no longer needlessly yellow.
  assert.equal(humidityVerdict(32, undefined, 7.2), "ok");
  // 18 °C / 44 % RH = 6.8 g/m³ -> RH says ok, abs finally flags the cool dry room.
  assert.equal(humidityVerdict(44, undefined, 6.8), "warn");
  assert.equal(humidityVerdict(44, undefined, 4.9), "alert");
  // exact floor values are not below the floor
  assert.equal(humidityVerdict(40, undefined, 5.0), "warn");
  assert.equal(humidityVerdict(40, undefined, 7.0), "ok");
  // moist side stays RELATIVE regardless of a healthy absolute value
  assert.equal(humidityVerdict(62, undefined, 10), "warn");
  assert.equal(humidityVerdict(66, undefined, 10), "alert");
  // custom floors + silent fallback on a non-ascending pair
  assert.equal(humidityVerdict(40, undefined, 5.5, [6, 8]), "alert");
  assert.equal(humidityVerdict(40, undefined, 5.5, [8, 6]), "warn");
  // no absolute value -> exact pre-ADR-0066 RH behaviour (silent degrade)
  assert.equal(humidityVerdict(32, undefined, null), "warn");
  assert.equal(humidityVerdict(29, undefined, null), "alert");
});

test("tempVerdictComfort maps band verdict to level", () => {
  assert.equal(tempVerdictComfort("in_band"), "ok");
  assert.equal(tempVerdictComfort("cool_edge"), "warn");
  assert.equal(tempVerdictComfort("warm_edge"), "warn");
  assert.equal(tempVerdictComfort("below"), "alert");
  assert.equal(tempVerdictComfort("above"), "alert");
  assert.equal(tempVerdictComfort("unknown"), "unknown");
  assert.equal(tempVerdictComfort(null), "unknown");
});

test("tempVerdictAsrOffice: <=26 ok / 26-30 warn / >30 alert", () => {
  assert.equal(tempVerdictAsrOffice(null), "unknown");
  assert.equal(tempVerdictAsrOffice(24), "ok");
  assert.equal(tempVerdictAsrOffice(26), "ok");
  assert.equal(tempVerdictAsrOffice(28), "warn");
  assert.equal(tempVerdictAsrOffice(30), "warn");
  assert.equal(tempVerdictAsrOffice(31), "alert");
  assert.equal(tempVerdictAsrOffice(36), "alert");
});

test("levelColor maps to HA theme variables", () => {
  assert.match(levelColor("ok"), /--success-color/);
  assert.match(levelColor("warn"), /--warning-color/);
  assert.match(levelColor("alert"), /--error-color/);
  assert.match(levelColor("unknown"), /--disabled-text-color/);
});

test("buildMonitor: temperature always, humidity/co2 only when present", () => {
  const only = buildMonitor({
    temperature: 22,
    comfortVerdict: "in_band",
    humidity: null,
    co2: null,
  });
  assert.equal(only.length, 1);
  assert.equal(only[0].key, "temperature");
  assert.equal(only[0].level, "ok");

  const all = buildMonitor(
    { temperature: 31, comfortVerdict: "above", humidity: 70, co2: 1500 },
    { temperature_scale: "asr_office" },
  );
  assert.deepEqual(
    all.map((l) => l.key),
    ["temperature", "humidity", "co2"],
  );
  assert.equal(all[0].level, "alert"); // 31 °C on ASR overlay
  assert.equal(all[1].level, "alert"); // 70 % humidity
  assert.equal(all[2].level, "warn"); // 1500 ppm UBA
  assert.match(all[2].color, /--warning-color/);
});

test("buildMonitor: absolute humidity feeds the lamp verdict + title detail", () => {
  const lamps = buildMonitor({
    temperature: 24,
    comfortVerdict: "in_band",
    humidity: 32, // RH alone would say warn
    absHumidityGm3: 7.3, // abs says the warm room is fine (ADR-0066 A.3)
    co2: null,
  });
  const hum = lamps.find((l) => l.key === "humidity");
  assert.equal(hum?.level, "ok");
  assert.equal(hum?.detail, "7.3 g/m³");
  // absent abs value -> no detail, RH fallback verdict
  const fallback = buildMonitor({
    temperature: 24,
    comfortVerdict: "in_band",
    humidity: 32,
    co2: null,
  }).find((l) => l.key === "humidity");
  assert.equal(fallback?.level, "warn");
  assert.equal(fallback?.detail, undefined);
});

test("buildMonitor comfort scale uses the band verdict, not ASR heat", () => {
  // 28 °C would be ASR-warn, but the default comfort scale follows the band.
  const lamps = buildMonitor({
    temperature: 28,
    comfortVerdict: "in_band",
    humidity: null,
    co2: null,
  });
  assert.equal(lamps[0].level, "ok");
});

test("ppdFromPmv matches ISO 7730 (0 -> 5 %, 0.5 -> ~10 %)", () => {
  assert.ok(Math.abs(ppdFromPmv(0) - 5) < 0.01);
  assert.ok(Math.abs(ppdFromPmv(0.5) - 10) < 0.5);
});

test("pmvVerdict: PPD thresholds 10/15, PMV fallback", () => {
  assert.equal(pmvVerdict(null, null), "unknown");
  assert.equal(pmvVerdict(0, 5), "ok");
  assert.equal(pmvVerdict(null, 8), "ok");
  assert.equal(pmvVerdict(null, 10), "warn");
  assert.equal(pmvVerdict(null, 14), "warn");
  assert.equal(pmvVerdict(null, 15), "alert");
  assert.equal(pmvVerdict(null, 30), "alert");
  assert.equal(pmvVerdict(0, null), "ok"); // PMV 0 -> PPD 5
  assert.equal(pmvVerdict(0.9, null), "alert"); // |PMV| 0.9 -> PPD ~22
});

test("caVerdict: worst of deviation / cycles / time-in-band", () => {
  const none = { deviationK: null, timeInBand: null, cyclesPerH: null };
  assert.equal(caVerdict(none), "unknown");
  assert.equal(caVerdict({ deviationK: 0.3, timeInBand: 0.95, cyclesPerH: 1 }), "ok");
  assert.equal(caVerdict({ deviationK: 0.6, timeInBand: 0.95, cyclesPerH: 1 }), "warn");
  assert.equal(caVerdict({ deviationK: 0.3, timeInBand: 0.95, cyclesPerH: 7 }), "alert");
  assert.equal(caVerdict({ deviationK: 0.3, timeInBand: 0.5, cyclesPerH: 1 }), "alert");
  // time-in-band accepts a fraction (0.92) or an already-percent value (92)
  assert.equal(caVerdict({ deviationK: 0.3, timeInBand: 92, cyclesPerH: 1 }), "ok");
});

test("buildMonitor appends pmv and ca lamps only when present", () => {
  const base = buildMonitor({
    temperature: 22,
    comfortVerdict: "in_band",
    humidity: null,
    co2: null,
  });
  assert.equal(base.length, 1); // no pmv/ca fields -> just temperature

  const full = buildMonitor({
    temperature: 22,
    comfortVerdict: "in_band",
    humidity: null,
    co2: null,
    pmv: 0.2,
    ppd: 8,
    ca: { deviationK: 0.4, timeInBand: 0.92, cyclesPerH: 1 },
  });
  assert.deepEqual(
    full.map((l) => l.key),
    ["temperature", "pmv", "ca"],
  );
  assert.equal(full[1].value, 92); // satisfaction % = 100 - PPD (never raw PPD)
  assert.equal(full[1].level, "ok");
  assert.equal(full[2].value, 92); // time-in-band normalised to %
  assert.equal(full[2].level, "ok");
});

test("pmv lamp shows satisfaction (100 - PPD), never the raw PPD", () => {
  // Field feedback: "Behaglichkeit 5 %" read as the OPPOSITE of the best
  // case — the lamp now shows 100 - PPD, thresholds stay PPD-internal.
  const lamps = buildMonitor({
    temperature: 22,
    comfortVerdict: "in_band",
    humidity: null,
    co2: null,
    pmv: 0,
    ppd: 5,
  });
  const pmv = lamps.find((l) => l.key === "pmv");
  assert.ok(pmv);
  assert.equal(pmv.value, 95);
  assert.equal(pmv.level, "ok");
});

test("pmv lamp renders as not-validated when pmv_valid is false", () => {
  // ADR-0054 V3 card note: outside the ISO 7730 domain the integration
  // publishes pmv/ppd as null — the lamp must still render, grey, with the
  // "not validated" hint instead of silently disappearing.
  const lamps = buildMonitor({
    temperature: 22,
    comfortVerdict: "in_band",
    humidity: null,
    co2: null,
    pmv: null,
    ppd: null,
    pmvValid: false,
  });
  const pmv = lamps.find((l) => l.key === "pmv");
  assert.ok(pmv, "lamp must render although pmv/ppd are null");
  assert.equal(pmv.level, "unknown");
  assert.equal(pmv.value, null);
  assert.equal(pmv.detailKey, "pmv_not_validated");
  // valid / undefined without numbers -> unchanged: no pmv lamp at all.
  const none = buildMonitor({
    temperature: 22,
    comfortVerdict: "in_band",
    humidity: null,
    co2: null,
    pmvValid: true,
  });
  assert.equal(
    none.find((l) => l.key === "pmv"),
    undefined,
  );
});

test("comfortMeasure composes active measures and the maturing hint", () => {
  // ADR-0069 E7: display only, gated on the real toggle attribute.
  assert.equal(
    comfortMeasure({
      active: false,
      fanFirstPhase: "dwell",
      tier2FanCe: "live",
      tier2Pmv: "live",
      ceCreditK: 1,
      pmvOffsetK: 1,
    }),
    null,
  );
  const idle = comfortMeasure({
    active: true,
    fanFirstPhase: "idle",
    tier2FanCe: "shadow",
    tier2Pmv: "shadow",
    ceCreditK: 0,
    pmvOffsetK: 0,
  });
  assert.deepEqual(idle, {
    fan: false,
    ceK: null,
    offsetK: null,
    maturing: false,
    dwellMin: null,
    dwellTargetMin: null,
    dwellPaused: false,
  });
  const maturing = comfortMeasure({
    active: true,
    fanFirstPhase: "idle",
    tier2FanCe: "shadow",
    tier2Pmv: "eligible",
    ceCreditK: 0,
    pmvOffsetK: 0,
  });
  assert.equal(maturing?.maturing, true);
  const busy = comfortMeasure({
    active: true,
    fanFirstPhase: "dwell",
    tier2FanCe: "live",
    tier2Pmv: "live",
    ceCreditK: 0.4,
    pmvOffsetK: -0.3,
  });
  assert.deepEqual(busy, {
    fan: true,
    ceK: 0.4,
    offsetK: -0.3,
    maturing: false,
    dwellMin: null,
    dwellTargetMin: null,
    dwellPaused: false,
  });
});

test("comfortMeasure maturing progress: dwell figures, paused hint, fallback", () => {
  // ADR-0069 N1: the maturing hint carries the eligible latch's dwell
  // progress; a stalled dwell (dwelling flag empty) renders as paused.
  const advancing = comfortMeasure({
    active: true,
    fanFirstPhase: "idle",
    tier2FanCe: "shadow",
    tier2Pmv: "eligible",
    ceCreditK: 0,
    pmvOffsetK: 0,
    fanCeDwellMin: 0,
    pmvDwellMin: 780,
    dwellTargetMin: 1440,
    dwelling: "pmv_offset",
  });
  assert.deepEqual(advancing, {
    fan: false,
    ceK: null,
    offsetK: null,
    maturing: true,
    dwellMin: 780,
    dwellTargetMin: 1440,
    dwellPaused: false,
  });
  // fan_ce eligible wins the display slot (serialization order).
  const fanEligible = comfortMeasure({
    active: true,
    fanFirstPhase: "idle",
    tier2FanCe: "eligible",
    tier2Pmv: "shadow",
    ceCreditK: 0,
    pmvOffsetK: 0,
    fanCeDwellMin: 120,
    pmvDwellMin: 0,
    dwellTargetMin: 1440,
    dwelling: "",
  });
  assert.equal(fanEligible?.dwellMin, 120);
  assert.equal(fanEligible?.dwellPaused, true);
  // Old backend without the N1 attributes: plain maturing, never "paused".
  const legacy = comfortMeasure({
    active: true,
    fanFirstPhase: "idle",
    tier2FanCe: "shadow",
    tier2Pmv: "eligible",
    ceCreditK: 0,
    pmvOffsetK: 0,
  });
  assert.equal(legacy?.maturing, true);
  assert.equal(legacy?.dwellMin, null);
  assert.equal(legacy?.dwellPaused, false);
});

test("a collapsed band renders grey WITH its own text (ADR-0049 N1)", () => {
  assert.equal(tempVerdictComfort("no_band"), "unknown");
  const lamps = buildMonitor({
    temperature: 22.7,
    comfortVerdict: "no_band",
    humidity: null,
    co2: null,
  });
  const temp = lamps.find((l) => l.key === "temperature")!;
  assert.equal(temp.level, "unknown");
  // The measurement IS there — only the band verdict is impossible.
  assert.equal(temp.value, 22.7);
  assert.equal(temp.detailKey, "no_band");
  // Control: a genuinely absent verdict carries no explanation, so the lamp
  // keeps the generic "no measurement" label.
  const none = buildMonitor({
    temperature: null,
    comfortVerdict: null,
    humidity: null,
    co2: null,
  });
  assert.equal(none[0]!.detailKey, undefined);
});

test("the collapsed-band text is translated in both locales", () => {
  for (const lang of ["en", "de"]) {
    const s = t(lang, "no_band");
    assert.notEqual(s, "no_band"); // key must not fall through untranslated
    assert.notEqual(s, t(lang, "unknown")); // and must NOT be "no measurement"
  }
});

test("ventChip shows the open advice and the mould guard only (ADR-0066 N2)", () => {
  assert.deepEqual(ventChip("open", "moisture_out", "ok"), {
    labelKey: "vent_open",
    reasonKey: "vent_moisture_out",
    alert: false,
  });
  assert.equal(ventChip("open", "mold_risk", "alert")!.alert, true);
  // A reason the card does not know yet still shows the advice, without the
  // bracket — never a raw token in the UI.
  assert.equal(ventChip("open", "brand_new_reason", "ok")!.reasonKey, null);
  // The mould guard is the ONE close advice that asks the user to act...
  assert.deepEqual(ventChip("close", "mold_guard", "warn"), {
    labelKey: "vent_close",
    reasonKey: "vent_mold_guard",
    alert: false,
  });
  // ...every harmless all-clear stays silent (no chip noise).
  assert.equal(ventChip("close", "target_reached", "ok"), null);
  assert.equal(ventChip("close", "cooled_off", "ok"), null);
  assert.equal(ventChip("close", "thermal_floor", "warn"), null);
  assert.equal(ventChip("idle", "no_gain", "ok"), null);
  assert.equal(ventChip(null, null, null), null);
});

test("the mould-guard chip text is translated in both locales", () => {
  for (const lang of ["en", "de"]) {
    for (const key of ["vent_close", "vent_mold_guard"]) {
      assert.notEqual(t(lang, key), key);
    }
  }
});
