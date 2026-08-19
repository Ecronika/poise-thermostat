// Pure EN-16798 comfort-band math for the Poise card (ADR-0040, ADR-0016).
// No DOM, no HA — unit-tested in isolation (mirrors the integration's pure core).

export type Verdict =
  | "below"
  | "cool_edge"
  | "in_band"
  | "warm_edge"
  | "above"
  // ADR-0049 N1: the band collapsed onto a point because a protection floor
  // (mould/norm) holds the setpoint at the upper edge. A band verdict is
  // impossible — which is NOT the same as having no measurement.
  | "no_band"
  | "unknown";

export interface BandInput {
  operative: number | null;
  setpoint: number | null;
  low: number | null;
  high: number | null;
  category?: string | null;
}

export interface BandModel {
  low: number;
  high: number;
  span: number;
  // ADR-0049 N1: low == high — the band display stays omitted, but the state
  // is distinguishable from "no band data at all".
  collapsed: boolean;
  operative: number | null;
  setpoint: number | null;
  category: string;
  verdict: Verdict;
  axisLow: number;
  axisHigh: number;
  lowFrac: number;
  highFrac: number;
  operativeFrac: number | null;
  setpointFrac: number | null;
}

// Padding (K) shown around the comfort band on the axis.
export const AXIS_PAD_K = 1.5;

export function clamp(value: number, lo: number, hi: number): number {
  return Math.min(Math.max(value, lo), hi);
}

// Position of a value on the padded axis, 0..1.
export function frac(value: number, axisLow: number, axisHigh: number): number {
  if (axisHigh <= axisLow) return 0.5;
  return clamp((value - axisLow) / (axisHigh - axisLow), 0, 1);
}

export function verdictFor(
  operative: number | null,
  low: number,
  high: number,
): Verdict {
  if (operative == null) return "unknown";
  if (operative < low) return "below";
  if (operative > high) return "above";
  const span = high - low;
  if (span <= 0) return "in_band";
  const r = (operative - low) / span;
  if (r < 0.25) return "cool_edge";
  if (r > 0.75) return "warm_edge";
  return "in_band";
}

export function buildBand(input: BandInput): BandModel | null {
  const { operative, setpoint, low, high } = input;
  // An INVERTED band (high < low) stays a contract violation — the backend
  // never publishes one (dual_setpoint: cool_sp = max(cool_sp, heat_sp)). A
  // COLLAPSED band (high == low) is a real state and keeps its model
  // (ADR-0049 N1); only the band verdict is impossible.
  if (low == null || high == null || high < low) return null;
  const collapsed = high === low;
  const axisLow = low - AXIS_PAD_K;
  const axisHigh = high + AXIS_PAD_K;
  return {
    low,
    high,
    span: high - low,
    collapsed,
    operative,
    setpoint,
    category: input.category ?? "",
    verdict: collapsed ? "no_band" : verdictFor(operative, low, high),
    axisLow,
    axisHigh,
    lowFrac: frac(low, axisLow, axisHigh),
    highFrac: frac(high, axisLow, axisHigh),
    operativeFrac: operative == null ? null : frac(operative, axisLow, axisHigh),
    setpointFrac: setpoint == null ? null : frac(setpoint, axisLow, axisHigh),
  };
}
