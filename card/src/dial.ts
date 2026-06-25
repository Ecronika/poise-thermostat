// Pure circular-dial geometry for the setpoint control (ADR-0040, P2).
// Angles in degrees, measured clockwise from east (SVG y-down). Unit-tested.

export interface DialConfig {
  min: number;
  max: number;
  start: number; // angle of min value
  sweep: number; // arc span (deg), gap = 360 - sweep at the bottom
}

// 270° arc with a 90° gap at the bottom (min lower-left, max lower-right).
export const DIAL: DialConfig = { min: 16, max: 28, start: 135, sweep: 270 };

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), hi);
}

export function valueToAngle(v: number, c: DialConfig = DIAL): number {
  const f = clamp((v - c.min) / (c.max - c.min), 0, 1);
  return c.start + f * c.sweep;
}

// Map a raw angle (0..360) onto the track, clamping gap angles to the nearer end.
export function clampAngleToTrack(angDeg: number, c: DialConfig = DIAL): number {
  let a = angDeg;
  while (a < c.start) a += 360;
  while (a >= c.start + 360) a -= 360;
  if (a <= c.start + c.sweep) return a;
  const toEnd = a - (c.start + c.sweep);
  const toStart = c.start + 360 - a;
  return toStart < toEnd ? c.start : c.start + c.sweep;
}

export function angleToValue(angDeg: number, c: DialConfig = DIAL): number {
  const a = clampAngleToTrack(angDeg, c);
  const f = (a - c.start) / c.sweep;
  return c.min + f * (c.max - c.min);
}

export function polar(
  cx: number,
  cy: number,
  r: number,
  angDeg: number,
): { x: number; y: number } {
  const rad = (angDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

export function arcPath(
  cx: number,
  cy: number,
  r: number,
  a0: number,
  a1: number,
): string {
  if (a1 <= a0) return "";
  const p0 = polar(cx, cy, r, a0);
  const p1 = polar(cx, cy, r, a1);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M ${p0.x.toFixed(2)} ${p0.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${p1.x.toFixed(2)} ${p1.y.toFixed(2)}`;
}

// dx/dy are pointer coords relative to the dial centre.
export function pointToValue(dx: number, dy: number, c: DialConfig = DIAL): number {
  let ang = (Math.atan2(dy, dx) * 180) / Math.PI;
  if (ang < 0) ang += 360;
  return angleToValue(ang, c);
}

// Keyboard stepping for the dial slider (accessibility, review D2). Returns the
// new clamped+snapped setpoint for an arrow/page/home/end key, or null for any
// other key (so the caller leaves the event alone).
export function setpointForKey(
  key: string,
  current: number,
  step: number,
  c: DialConfig = DIAL,
): number | null {
  let next: number;
  switch (key) {
    case "ArrowUp":
    case "ArrowRight":
      next = current + step;
      break;
    case "ArrowDown":
    case "ArrowLeft":
      next = current - step;
      break;
    case "PageUp":
      next = current + step * 5;
      break;
    case "PageDown":
      next = current - step * 5;
      break;
    case "Home":
      next = c.min;
      break;
    case "End":
      next = c.max;
      break;
    default:
      return null;
  }
  return Math.round(clamp(next, c.min, c.max) / step) * step;
}
