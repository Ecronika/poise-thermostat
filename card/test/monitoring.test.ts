import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildMonitor,
  co2Thresholds,
  co2Verdict,
  humidityVerdict,
  levelColor,
  tempVerdictAsrOffice,
  tempVerdictComfort,
} from "../src/monitoring.ts";

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
