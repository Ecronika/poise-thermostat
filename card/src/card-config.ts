import type { LovelaceCardConfig } from "./ha-types.ts";

// ADR-0057: card layout & display configuration. All resolution is pure and
// unit-tested; the LitElement only reads the ResolvedConfig. Unknown / invalid
// values fall back silently to sane defaults (same doctrine as ADR-0049 §6).

export type TemperatureScale = "comfort" | "asr_office";
export type Co2Scheme = "uba" | "en16798";
export type Density = "comfortable" | "compact";
export type Controls = "dial" | "buttons" | "none";
export type ChipKey =
  | "hvac"
  | "window"
  | "humidity"
  | "co2"
  | "temperature"
  | "ca";

// Order here is also the render order of the condition row.
export const ALL_CHIPS: readonly ChipKey[] = [
  "hvac",
  "window",
  "temperature",
  "humidity",
  "co2",
  "ca",
];

export interface SectionsConfig {
  chips?: ChipKey[] | boolean; // subset array; false = none; true/undef = all
  shadow_pill?: boolean;
  learning?: boolean;
  pmv?: boolean;
  presets?: boolean;
}

export interface HistoryConfig {
  show?: boolean;
  hours?: number; // 12 | 24 | 48
}

export interface PoiseCardConfig extends LovelaceCardConfig {
  type: string;
  entity?: string; // a Poise climate entity
  show_shadow?: boolean; // legacy alias -> sections.shadow_pill (default true)
  compact?: boolean; // legacy -> density:"compact"
  density?: Density; // comfortable (default) | compact
  controls?: Controls; // dial (default) | buttons | none (display-only)
  history?: HistoryConfig | boolean; // false disables; object sets show/hours
  sections?: SectionsConfig; // per-element visibility
  // ADR-0049 room-condition traffic lights — card-side verdict, no recorder load
  temperature_scale?: TemperatureScale; // "comfort" (default) | "asr_office"
  humidity_thresholds?: number[]; // [alertLo, warnLo, warnHi, alertHi]
  co2_scheme?: Co2Scheme; // "uba" (default) | "en16798"
  co2_thresholds?: number[]; // UBA mode [warn, alert]
}

export interface ResolvedConfig {
  entity: string | undefined;
  density: Density;
  controls: Controls;
  history: { show: boolean; hours: number };
  chips: Set<ChipKey>;
  shadowPill: boolean;
  learning: boolean;
  pmv: boolean;
  presets: boolean;
  temperature_scale?: TemperatureScale;
  humidity_thresholds?: number[];
  co2_scheme?: Co2Scheme;
  co2_thresholds?: number[];
}

export const HISTORY_HOURS: readonly number[] = [12, 24, 48];

function oneOf<T extends string>(
  v: unknown,
  allowed: readonly T[],
  dflt: T,
): T {
  return typeof v === "string" && (allowed as readonly string[]).includes(v)
    ? (v as T)
    : dflt;
}

function boolOr(v: unknown, dflt: boolean): boolean {
  return typeof v === "boolean" ? v : dflt;
}

export function resolveChips(raw: SectionsConfig["chips"]): Set<ChipKey> {
  if (raw === false) return new Set();
  if (raw == null || raw === true) return new Set(ALL_CHIPS);
  if (Array.isArray(raw)) {
    return new Set(
      raw.filter((c): c is ChipKey =>
        (ALL_CHIPS as readonly string[]).includes(c),
      ),
    );
  }
  return new Set(ALL_CHIPS);
}

export function resolveHistory(
  raw: PoiseCardConfig["history"],
): { show: boolean; hours: number } {
  if (raw === false) return { show: false, hours: 24 };
  if (raw === true || raw == null) return { show: true, hours: 24 };
  const h = typeof raw.hours === "number" ? raw.hours : Number(raw.hours);
  const hours = HISTORY_HOURS.includes(h) ? h : 24;
  return { show: boolOr(raw.show, true), hours };
}

export function resolveConfig(raw: PoiseCardConfig): ResolvedConfig {
  const s = raw.sections ?? {};
  const density: Density = raw.density
    ? oneOf(raw.density, ["comfortable", "compact"], "comfortable")
    : raw.compact
      ? "compact"
      : "comfortable";
  return {
    entity: raw.entity,
    density,
    controls: oneOf(raw.controls, ["dial", "buttons", "none"], "dial"),
    history: resolveHistory(raw.history),
    chips: resolveChips(s.chips),
    // sections.shadow_pill wins; else the legacy show_shadow flag; else on.
    shadowPill: boolOr(s.shadow_pill, boolOr(raw.show_shadow, true)),
    learning: boolOr(s.learning, true),
    pmv: boolOr(s.pmv, true),
    presets: boolOr(s.presets, true),
    temperature_scale: raw.temperature_scale,
    humidity_thresholds: raw.humidity_thresholds,
    co2_scheme: raw.co2_scheme,
    co2_thresholds: raw.co2_thresholds,
  };
}

export function chipEnabled(r: ResolvedConfig, key: ChipKey): boolean {
  return r.chips.has(key);
}
