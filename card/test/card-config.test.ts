import { test } from "node:test";
import assert from "node:assert/strict";
import {
  resolveConfig,
  resolveChips,
  resolveHistory,
  chipEnabled,
  ALL_CHIPS,
  type PoiseCardConfig,
} from "../src/card-config.ts";

const base: PoiseCardConfig = { type: "custom:poise-card", entity: "climate.x" };

test("defaults: comfortable / dial / history 24h / all sections on", () => {
  const r = resolveConfig(base);
  assert.equal(r.density, "comfortable");
  assert.equal(r.controls, "dial");
  assert.deepEqual(r.history, { show: true, hours: 24 });
  assert.equal(r.chips.size, ALL_CHIPS.length);
  assert.equal(r.shadowPill, true);
  assert.equal(r.learning, true);
  assert.equal(r.pmv, true);
  assert.equal(r.presets, true);
});

test("legacy compact:true maps to density compact (visual only)", () => {
  assert.equal(resolveConfig({ ...base, compact: true }).density, "compact");
  // explicit density wins over legacy compact
  assert.equal(
    resolveConfig({ ...base, compact: true, density: "comfortable" }).density,
    "comfortable",
  );
});

test("legacy show_shadow:false disables the shadow pill", () => {
  assert.equal(resolveConfig({ ...base, show_shadow: false }).shadowPill, false);
  // sections.shadow_pill wins over the legacy flag
  assert.equal(
    resolveConfig({
      ...base,
      show_shadow: false,
      sections: { shadow_pill: true },
    }).shadowPill,
    true,
  );
});

test("controls: invalid falls back to dial; valid passes through", () => {
  assert.equal(resolveConfig({ ...base, controls: "buttons" }).controls, "buttons");
  assert.equal(resolveConfig({ ...base, controls: "none" }).controls, "none");
  // @ts-expect-error deliberate bad value
  assert.equal(resolveConfig({ ...base, controls: "wat" }).controls, "dial");
});

test("history: boolean false / true and hours validation", () => {
  assert.deepEqual(resolveHistory(false), { show: false, hours: 24 });
  assert.deepEqual(resolveHistory(true), { show: true, hours: 24 });
  assert.deepEqual(resolveHistory({ show: true, hours: 48 }), { show: true, hours: 48 });
  assert.deepEqual(resolveHistory({ hours: 12 }), { show: true, hours: 12 });
  // invalid hours -> 24
  assert.deepEqual(resolveHistory({ hours: 999 }), { show: true, hours: 24 });
});

test("chips: subset / false / true / unknown-token dropped", () => {
  assert.deepEqual([...resolveChips(["hvac", "window"])].sort(), ["hvac", "window"]);
  assert.equal(resolveChips(false).size, 0);
  assert.equal(resolveChips(true).size, ALL_CHIPS.length);
  assert.equal(resolveChips(undefined).size, ALL_CHIPS.length);
  // unknown tokens are silently dropped
  assert.deepEqual([...resolveChips(["hvac", "bogus" as never])], ["hvac"]);
});

test("chipEnabled reflects the resolved set", () => {
  const r = resolveConfig({ ...base, sections: { chips: ["humidity", "co2"] } });
  assert.equal(chipEnabled(r, "humidity"), true);
  assert.equal(chipEnabled(r, "hvac"), false);
});

test("sections booleans gate pmv / learning / presets independently", () => {
  const r = resolveConfig({
    ...base,
    sections: { pmv: false, learning: false, presets: false },
  });
  assert.equal(r.pmv, false);
  assert.equal(r.learning, false);
  assert.equal(r.presets, false);
  assert.equal(r.shadowPill, true); // untouched -> default on
});

test("passthrough monitoring options survive resolution", () => {
  const r = resolveConfig({
    ...base,
    temperature_scale: "asr_office",
    co2_scheme: "en16798",
    humidity_thresholds: [30, 40, 60, 65],
  });
  assert.equal(r.temperature_scale, "asr_office");
  assert.equal(r.co2_scheme, "en16798");
  assert.deepEqual(r.humidity_thresholds, [30, 40, 60, 65]);
});
