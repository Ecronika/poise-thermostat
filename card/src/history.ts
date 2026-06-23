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
