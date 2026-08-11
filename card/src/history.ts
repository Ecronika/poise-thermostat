// Pure SVG-geometry math for the card's 24h history chart (ADR-0040, P2).
// Self-contained (no internal ha-chart-base dependency) and unit-tested.

export interface Sample {
  t: number; // epoch ms
  op: number | null; // operative temperature
  sp: number | null; // setpoint
}

export interface ChartGeom {
  width: number;
  height: number;
  opPath: string; // SVG polyline "x,y x,y …" for operative
  spPath: string; // … for setpoint
  bandTop: number; // y of comfort_high
  bandBottom: number; // y of comfort_low
  vMin: number;
  vMax: number;
}

// --- refresh scheduling (review plan A.1) --------------------------------------
// The card must not show an ageing chart on a dashboard that stays open: the
// loaded series is identified by entity+hours (``histKey``) and re-fetched
// periodically; a failed fetch re-arms on a much tighter backoff so a transient
// recorder/WS error never silently freezes the chart until a page reload.

export interface HistSync {
  key: string; // histKey() identity of the loaded series
  at: number; // epoch ms of the last (attempted) successful load
  failedAt: number | null; // epoch ms of the last failed attempt; null when ok
}

export const HIST_REFRESH_MS = 5 * 60_000;
export const HIST_RETRY_MS = 30_000;

export function histKey(entity: string, hours: number): string {
  return `${entity}|${hours}`;
}

export function shouldLoadHistory(
  cur: HistSync | null,
  key: string,
  now: number,
  refreshMs: number = HIST_REFRESH_MS,
  retryMs: number = HIST_RETRY_MS,
): boolean {
  if (cur === null || cur.key !== key) return true; // first load / re-keyed
  if (cur.failedAt != null) return now - cur.failedAt >= retryMs;
  return now - cur.at >= refreshMs;
}

// A completed fetch may only commit its outcome (samples or failure stamp)
// while the card still waits for exactly this series: a re-key while in
// flight (entity or hours changed) invalidates the response — else a slow
// old recorder query overwrites the new chart for up to HIST_REFRESH_MS, and
// a late failure would destroy the new fetch's in-flight stamp (double load).
export function histCurrent(cur: HistSync | null, key: string): boolean {
  return cur?.key === key;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), hi);
}

export function chartGeometry(
  samples: Sample[],
  low: number | null,
  high: number | null,
  width = 300,
  height = 90,
  padK = 1,
): ChartGeom | null {
  const vals: number[] = [];
  for (const s of samples) {
    if (s.op != null) vals.push(s.op);
    if (s.sp != null) vals.push(s.sp);
  }
  if (low != null) vals.push(low);
  if (high != null) vals.push(high);
  if (vals.length === 0 || samples.length === 0) return null;

  const vMin = Math.min(...vals) - padK;
  const vMax = Math.max(...vals) + padK;
  const tMin = samples[0].t;
  const tMax = samples[samples.length - 1].t;
  const span = tMax - tMin || 1;
  const vSpan = vMax - vMin || 1;

  const x = (t: number) => ((t - tMin) / span) * width;
  const y = (v: number) => height - ((v - vMin) / vSpan) * height; // inverted

  const path = (pick: (s: Sample) => number | null): string =>
    samples
      .filter((s) => pick(s) != null)
      .map((s) => `${x(s.t).toFixed(1)},${y(pick(s) as number).toFixed(1)}`)
      .join(" ");

  return {
    width,
    height,
    opPath: path((s) => s.op),
    spPath: path((s) => s.sp),
    bandTop: high == null ? 0 : clamp(y(high), 0, height),
    bandBottom: low == null ? height : clamp(y(low), 0, height),
    vMin,
    vMax,
  };
}
