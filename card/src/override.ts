// ADR-0059 §4: pure helpers for the manual-override ("Hold") feedback — remaining
// time, wall-clock validity, the explanatory clamp label and the preset fallback
// chip. Kept DOM-free so it unit-tests under `node --test`; the card glue only
// wires these into lit templates and the resume service call.
import type { HomeAssistant } from "./ha-types.ts";
import { t } from "./localize.ts";

// Whole minutes until an ISO-8601 instant, clamped at 0; null when absent/unparseable.
export function minutesUntil(iso: unknown, now: number = Date.now()): number | null {
  if (typeof iso !== "string") return null;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return null;
  return Math.max(0, Math.round((ts - now) / 60000));
}

// Local wall-clock "HH:MM" for an ISO instant; null when absent/unparseable.
export function clockLabel(iso: unknown, locale?: string): string | null {
  if (typeof iso !== "string") return null;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return null;
  return new Date(ts).toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ADR-0059 (VT#1980 — "UI ≠ internal state"): the actually commanded / held
// setpoint is HA's `temperature` attribute (= target_temperature, the clamped
// write target) — NOT `heat_sp`, which is only the comfort-band lower edge and
// is always set, so a `?? temperature` fallback would never fire. Reading
// `heat_sp` here shows the band edge instead of the held value and mis-explains
// an upward clamp. Null-safe: degrades to null when `temperature` is absent
// (never falls back to the band edge), so the caller labels the hold without a
// bogus degree value rather than crashing.
export function heldSetpoint(a: Record<string, unknown>): number | null {
  const v = a["temperature"];
  const n = typeof v === "string" ? parseFloat(v) : (v as number);
  return typeof n === "number" && !Number.isNaN(n) ? n : null;
}

export interface HoldView {
  label: string; // "Manuell 22.5°" or "Manuell (dauerhaft)"
  minutes: number | null; // remaining minutes; null when permanent/unknown
  permanent: boolean;
}

// Compose the Hold-pill text. A `permanent` policy drops the countdown and reads
// "Manual (permanent)"; otherwise the remaining minutes come from expires_at.
export function holdView(
  lang: string | undefined,
  setpoint: number | null,
  policy: unknown,
  expiresAt: unknown,
  now: number = Date.now(),
): HoldView {
  const manual = t(lang, "manual");
  if (policy === "permanent") {
    return {
      label: `${manual} (${t(lang, "permanent")})`,
      minutes: null,
      permanent: true,
    };
  }
  const label = setpoint != null ? `${manual} ${setpoint.toFixed(1)}°` : manual;
  return { label, minutes: minutesUntil(expiresAt, now), permanent: false };
}

// Explanatory clamp label: "22.5° statt 24° (Normgrenze)" from the effective
// setpoint vs the pre-clamp request. Falls back to the generic clamped label
// when either value is missing.
export function clampLabel(
  lang: string | undefined,
  effective: number | null,
  requested: number | null,
): string {
  if (effective == null || requested == null) return t(lang, "override_clamped");
  return `${effective.toFixed(1)}° ${t(lang, "instead_of")} ${requested.toFixed(1)}° (${t(lang, "norm_limit")})`;
}

export interface PresetChipSpec {
  key: string;
  label: string;
}

// Fallback preset chip — only when a preset is active AND the dedicated preset
// row is off (else it duplicates that row). ADR-0059 §4: `preset` is now a real
// attribute, so this chip is live again (was dead code, poise-card.ts:433-435).
export function presetChip(
  lang: string | undefined,
  preset: unknown,
  presetsSectionOn: boolean,
): PresetChipSpec | null {
  const key = preset == null ? "none" : String(preset).toLowerCase();
  if (key === "none" || presetsSectionOn) return null;
  return { key, label: t(lang, key) || key };
}

// HA glue: resume the schedule (drop the manual hold) for one climate entity.
export function resumeSchedule(hass: HomeAssistant, entityId: string): void {
  void hass.callService("poise", "resume_schedule", { entity_id: entityId });
}
