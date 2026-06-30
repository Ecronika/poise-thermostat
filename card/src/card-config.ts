import type { LovelaceCardConfig } from "./ha-types.ts";

export type TemperatureScale = "comfort" | "asr_office";
export type Co2Scheme = "uba" | "en16798";

export interface PoiseCardConfig extends LovelaceCardConfig {
  type: string;
  entity?: string; // a Poise climate entity
  show_shadow?: boolean; // show MPC/TPI/PI shadow pill (default true)
  compact?: boolean; // slim tile (dial + setpoint only)
  // ADR-0049 room-condition traffic lights — card-side verdict, no recorder load
  temperature_scale?: TemperatureScale; // "comfort" (default) | "asr_office"
  humidity_thresholds?: number[]; // [alertLo, warnLo, warnHi, alertHi]
  co2_scheme?: Co2Scheme; // "uba" (default) | "en16798"
  co2_thresholds?: number[]; // UBA mode [warn, alert]
}
