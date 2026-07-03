// Pure card-side room-condition traffic lights (ADR-0049).
// Temperature / humidity / CO₂ → ok / warn / alert, computed in the FRONTEND
// from the live entity state — zero recorder load, no actuation (ADR-0048,
// monitor-only). Thresholds are configurable; colours map to HA theme
// variables (a11y, ADR-0040). Silent fallbacks on bad input — never throws.
// No DOM, no HA: unit-tested in isolation like comfort.ts (F21).

import type { Verdict } from "./comfort.ts";

export type Level = "ok" | "warn" | "alert" | "unknown";
export type TempScale = "comfort" | "asr_office";
export type Co2Scheme = "uba" | "en16798";

// Colours fixed to HA theme variables (ADR-0049 §6) with safe fallbacks.
export const LEVEL_COLOR: Record<Level, string> = {
  ok: "var(--success-color, #43a047)",
  warn: "var(--warning-color, #fb8c00)",
  alert: "var(--error-color, #e53935)",
  unknown: "var(--disabled-text-color, #9e9e9e)",
};

export function levelColor(level: Level): string {
  return LEVEL_COLOR[level] ?? LEVEL_COLOR.unknown;
}

// Defaults (ADR-0049 §3–5), all overridable from the card config.
export const DEFAULT_CO2_THRESHOLDS: readonly [number, number] = [1000, 2000]; // UBA
export const DEFAULT_HUMIDITY_THRESHOLDS: readonly [number, number, number, number] =
  [30, 40, 60, 65];
export const ASR_OFFICE_THRESHOLDS: readonly [number, number] = [26, 30]; // ASR A3.5
export const EN16798_OUTDOOR_CO2 = 420; // assumed outdoor ppm when none supplied
export const EN16798_CO2_RISE: readonly [number, number] = [800, 1350]; // Cat II/III

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

// A strictly ascending pair, else the (valid) fallback — silent (ADR-0049 §6).
function pairOr(
  a: readonly number[] | undefined,
  fallback: readonly [number, number],
): [number, number] {
  if (a && a.length >= 2 && isNum(a[0]) && isNum(a[1]) && a[0] < a[1]) {
    return [a[0], a[1]];
  }
  return [fallback[0], fallback[1]];
}

// A non-decreasing 4-tuple, else the fallback.
function quadOr(
  a: readonly number[] | undefined,
  fallback: readonly [number, number, number, number],
): [number, number, number, number] {
  if (a && a.length >= 4 && a.slice(0, 4).every(isNum)) {
    const [w, x, y, z] = a;
    if (w <= x && x <= y && y <= z) return [w, x, y, z];
  }
  return [fallback[0], fallback[1], fallback[2], fallback[3]];
}

// --- CO₂ (UBA absolute default; EN 16798-1 outdoor-offset opt-in) ---
export interface Co2Opts {
  scheme?: Co2Scheme;
  thresholds?: readonly number[]; // UBA mode [warn, alert]
  outdoor?: number | null; // EN mode outdoor ppm
  enRise?: readonly number[]; // EN rise over outdoor [warn, alert]
}

export function co2Thresholds(opts?: Co2Opts): [number, number] {
  if (opts?.scheme === "en16798") {
    const outdoor = isNum(opts.outdoor) ? opts.outdoor : EN16798_OUTDOOR_CO2;
    const rise = pairOr(opts.enRise, EN16798_CO2_RISE);
    return [outdoor + rise[0], outdoor + rise[1]];
  }
  return pairOr(opts?.thresholds, DEFAULT_CO2_THRESHOLDS);
}

export function co2Verdict(value: number | null, opts?: Co2Opts): Level {
  if (!isNum(value)) return "unknown";
  const [warn, alert] = co2Thresholds(opts);
  if (value >= alert) return "alert";
  if (value >= warn) return "warn";
  return "ok";
}

// --- Humidity: thresholds = [alertLo, warnLo, warnHi, alertHi] ---
// green inside [warnLo, warnHi]; warn in the two side-bands; alert beyond.
export function humidityVerdict(
  value: number | null,
  thresholds?: readonly number[],
): Level {
  if (!isNum(value)) return "unknown";
  const [aLo, wLo, wHi, aHi] = quadOr(thresholds, DEFAULT_HUMIDITY_THRESHOLDS);
  if (value < aLo || value >= aHi) return "alert";
  if (value < wLo || value > wHi) return "warn";
  return "ok";
}

// --- Temperature: comfort-band reuse (default) or ASR office-heat overlay ---
export function tempVerdictComfort(v: Verdict | null): Level {
  switch (v) {
    case "in_band":
      return "ok";
    case "cool_edge":
    case "warm_edge":
      return "warn";
    case "below":
    case "above":
      return "alert";
    default:
      return "unknown";
  }
}

// ASR A3.5: ≤26 ok / 26–30 warn / >30 alert (>35 unsuitable, still alert).
export function tempVerdictAsrOffice(
  value: number | null,
  thresholds?: readonly number[],
): Level {
  if (!isNum(value)) return "unknown";
  const [warn, alert] = pairOr(thresholds, ASR_OFFICE_THRESHOLDS);
  if (value > alert) return "alert";
  if (value > warn) return "warn";
  return "ok";
}

// --- Comfort quality: PMV / PPD (ISO 7730, ADR-0054) ---
// PPD (predicted % dissatisfied) is the intuitive single number; ISO 7730
// category targets are Cat I <=6, Cat II <=10, Cat III <=15 %. Green within the
// Cat II target, warn up to Cat III, alert beyond. Falls back to PMV via the PPD
// relation when PPD is absent. Silent on missing input (ADR-0049 §6).
export const DEFAULT_PPD_THRESHOLDS: readonly [number, number] = [10, 15];

export function ppdFromPmv(pmv: number): number {
  return 100 - 95 * Math.exp(-(0.03353 * pmv ** 4 + 0.2179 * pmv ** 2));
}

export function pmvVerdict(
  pmv: number | null,
  ppd: number | null,
  thresholds?: readonly number[],
): Level {
  const [warn, alert] = pairOr(thresholds, DEFAULT_PPD_THRESHOLDS);
  const p = isNum(ppd) ? ppd : isNum(pmv) ? ppdFromPmv(pmv) : null;
  if (p == null) return "unknown";
  if (p >= alert) return "alert";
  if (p >= warn) return "warn";
  return "ok";
}

// --- Regulation quality: control accuracy (EN 15500-1, ADR-0055) ---
// Combines band deviation [K], time-in-band (fraction 0..1 or %) and the
// short-cycle rate [cycles/h]; the worst single metric sets the level.
export interface CaInput {
  deviationK: number | null;
  timeInBand: number | null;
  cyclesPerH: number | null;
}
export const DEFAULT_CA_DEVIATION: readonly [number, number] = [0.5, 1.0]; // K
export const DEFAULT_CA_CYCLES: readonly [number, number] = [3, 6]; // per hour
export const DEFAULT_CA_TIME_IN_BAND: readonly [number, number] = [85, 60]; // %

export function timeInBandPct(v: number): number {
  return v <= 1 ? v * 100 : v;
}

const _RANK: Record<Level, number> = { unknown: -1, ok: 0, warn: 1, alert: 2 };

export function caVerdict(input: CaInput): Level {
  const levels: Level[] = [];
  if (isNum(input.deviationK)) {
    const [w, a] = DEFAULT_CA_DEVIATION;
    levels.push(input.deviationK >= a ? "alert" : input.deviationK >= w ? "warn" : "ok");
  }
  if (isNum(input.cyclesPerH)) {
    const [w, a] = DEFAULT_CA_CYCLES;
    levels.push(input.cyclesPerH >= a ? "alert" : input.cyclesPerH >= w ? "warn" : "ok");
  }
  if (isNum(input.timeInBand)) {
    const p = timeInBandPct(input.timeInBand);
    const [w, a] = DEFAULT_CA_TIME_IN_BAND;
    levels.push(p < a ? "alert" : p < w ? "warn" : "ok");
  }
  if (!levels.length) return "unknown";
  return levels.reduce((x, y) => (_RANK[y] > _RANK[x] ? y : x), "ok" as Level);
}

// --- Assemble the lamps for the card (capability-gated by presence) ---
export interface MonitorInput {
  temperature: number | null;
  comfortVerdict?: Verdict | null;
  humidity: number | null;
  co2: number | null;
  pmv?: number | null;
  ppd?: number | null;
  ca?: CaInput | null;
}

export interface MonitorConfig {
  temperature_scale?: TempScale;
  asr_thresholds?: readonly number[];
  humidity_thresholds?: readonly number[];
  co2_scheme?: Co2Scheme;
  co2_thresholds?: readonly number[];
  outdoor_co2?: number | null;
}

export interface Lamp {
  key: "temperature" | "humidity" | "co2" | "pmv" | "ca";
  value: number | null;
  unit: string;
  level: Level;
  color: string;
}

export function buildMonitor(input: MonitorInput, config?: MonitorConfig): Lamp[] {
  const lamps: Lamp[] = [];
  const tLevel =
    config?.temperature_scale === "asr_office"
      ? tempVerdictAsrOffice(input.temperature, config.asr_thresholds)
      : tempVerdictComfort(input.comfortVerdict ?? null);
  lamps.push({
    key: "temperature",
    value: input.temperature,
    unit: "°C",
    level: tLevel,
    color: levelColor(tLevel),
  });
  if (isNum(input.humidity)) {
    const h = humidityVerdict(input.humidity, config?.humidity_thresholds);
    lamps.push({
      key: "humidity",
      value: input.humidity,
      unit: "%",
      level: h,
      color: levelColor(h),
    });
  }
  if (isNum(input.co2)) {
    const c = co2Verdict(input.co2, {
      scheme: config?.co2_scheme,
      thresholds: config?.co2_thresholds,
      outdoor: config?.outdoor_co2,
    });
    lamps.push({
      key: "co2",
      value: input.co2,
      unit: "ppm",
      level: c,
      color: levelColor(c),
    });
  }
  if (isNum(input.pmv) || isNum(input.ppd)) {
    const p = pmvVerdict(input.pmv ?? null, input.ppd ?? null);
    lamps.push({
      key: "pmv",
      value: isNum(input.ppd) ? input.ppd : null,
      unit: "%",
      level: p,
      color: levelColor(p),
    });
  }
  const ca = input.ca;
  if (ca && (isNum(ca.deviationK) || isNum(ca.timeInBand) || isNum(ca.cyclesPerH))) {
    const q = caVerdict(ca);
    lamps.push({
      key: "ca",
      value: isNum(ca.timeInBand) ? timeInBandPct(ca.timeInBand) : null,
      unit: "%",
      level: q,
      color: levelColor(q),
    });
  }
  return lamps;
}
