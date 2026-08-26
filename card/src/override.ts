// ADR-0059 §4: pure helpers for the manual-override ("Hold") feedback — remaining
// time, wall-clock validity, the explanatory clamp label and the preset fallback
// chip. Kept DOM-free so it unit-tests under `node --test`; the card glue only
// wires these into lit templates and the resume service call.
import type { HomeAssistant } from "./ha-types.ts";
import { t } from "./localize.ts";

const MINUTES_PER_DAY = 1440;
const MINUTES_PER_HOUR = 60;

// P2.4: chip minute values (preheating/coasting) come straight from
// ``minutes_to_comfort``/``minutes_to_setback``, which is now the horizon to
// a schedule edge on the cyclic weekly timeline — an ``always_setback`` zone
// with a single short window can be days out. A raw four-digit minute count
// ("2760 min") is unreadable, so >= 1 day renders as "<d> d <h> h" instead;
// below that the existing "<n> min" is unchanged. Rounding the leftover
// remainder up to a full day (e.g. 1439.6 min of the last day) must not
// print "1 d 24 h" — the overflow folds into the day count.
export function formatMinutesLabel(lang: string | undefined, minutes: number): string {
  const total = Math.round(minutes);
  if (total < MINUTES_PER_DAY) return `${total} ${t(lang, "min_left")}`;
  const days = Math.floor(total / MINUTES_PER_DAY);
  const hours = Math.round((total % MINUTES_PER_DAY) / MINUTES_PER_HOUR);
  return hours >= 24 ? `${days + 1} d 0 h` : `${days} d ${hours} h`;
}

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

// The dial/keyboard nudge step. HA serialises
// ClimateEntity.target_temperature_step under the ATTR_TARGET_TEMP_STEP wire
// key "target_temp_step" — the Python property name never appears in a state
// (review plan A.4: reading it always missed and silently fell back). 0.5
// mirrors the Poise entity default; non-positive/unparseable steps fall back
// too, so the dial's division/rounding never sees 0 or NaN.
export function stepOf(a: Record<string, unknown>): number {
  const v = a["target_temp_step"];
  const n = typeof v === "string" ? parseFloat(v) : (v as number);
  return typeof n === "number" && !Number.isNaN(n) && n > 0 ? n : 0.5;
}

export interface HoldView {
  label: string; // "Manuell 22.5°" or "Manuell (dauerhaft)"
  minutes: number | null; // remaining minutes; null when permanent/unknown
  permanent: boolean;
  direction: string | null; // localized "kühlt"/"heizt"/"entfeuchtet"; null when idle
  origin: string | null; // K3: localized "Gerät"/"App" provenance; null when unknown
}

// K3 (Inc 3): where the hold came from — the device (IR remote / vendor app, whose
// change Poise adopted) vs the Poise UI ("app"). A reason starting "device_adopt"
// is the device; "ui" is the app; frost_rescue / unknown → null (no origin shown).
export function holdOrigin(lang: string | undefined, reason: unknown): string | null {
  const r = typeof reason === "string" ? reason : "";
  if (r.startsWith("device_adopt")) return t(lang, "origin_device");
  if (r.startsWith("ui")) return t(lang, "origin_app");
  return null;
}

// Map the entity's hvac_action to a localized direction word for the Hold pill
// (V4, review 2026-07-13): the pill should say *what* the hold is doing, not just
// the value + time. idle/off/unknown -> null (no direction shown).
export function holdDirection(lang: string | undefined, action: unknown): string | null {
  const act = typeof action === "string" ? action.toLowerCase() : "";
  if (act === "cooling") return t(lang, "cools");
  if (act === "heating") return t(lang, "heats");
  if (act === "drying") return t(lang, "dries");
  return null;
}

// Map a held hvac_mode to its localized word for the Hold pill (mode-holds,
// K2). Known modes localize; an unknown future mode stays visible raw.
export function modeHoldLabel(lang: string | undefined, mode: unknown): string | null {
  if (typeof mode !== "string" || mode === "") return null;
  const key = `mode_${mode}`;
  const word = t(lang, key);
  return word === key ? mode : word;
}

// Compose the Hold-pill text. A `permanent` policy drops the countdown and reads
// "Manual (permanent)"; otherwise the remaining minutes come from expires_at. The
// optional `action` (entity hvac_action) adds the current direction word (V4).
// A mode-hold (`modeOverride`) appends its mode word; when it is the ONLY hold
// (`hasSetpointHold` false — no `override_requested` published) the pill shows
// "Manual · Off" WITHOUT a degree number: the entity `temperature` is then just
// the live schedule edge, not a held value (field bug 2026-08-10).
export function holdView(
  lang: string | undefined,
  setpoint: number | null,
  policy: unknown,
  expiresAt: unknown,
  now: number = Date.now(),
  action: unknown = null,
  reason: unknown = null,
  modeOverride: unknown = null,
  hasSetpointHold: boolean = true,
): HoldView {
  const manual = t(lang, "manual");
  const direction = holdDirection(lang, action);
  const origin = holdOrigin(lang, reason);
  const modeWord = modeHoldLabel(lang, modeOverride);
  const suffix = modeWord != null ? ` · ${modeWord}` : "";
  if (policy === "permanent") {
    return {
      label: `${manual} (${t(lang, "permanent")})${suffix}`,
      minutes: null,
      permanent: true,
      direction,
      origin,
    };
  }
  const label =
    hasSetpointHold && setpoint != null
      ? `${manual} ${setpoint.toFixed(1)}°${suffix}`
      : `${manual}${suffix}`;
  return {
    label,
    minutes: minutesUntil(expiresAt, now),
    permanent: false,
    direction,
    origin,
  };
}

// V3a (review 2026-07-13, D1): the dial's big number shows the *operative*
// temperature (air+radiation); the air temperature is a different, unlabelled
// value the entity's more-info shows. Return the air value to display as a
// secondary hint only when it diverges meaningfully (>= threshold K) from the
// operative value; null when they agree, either is absent, or the gap is noise.
export function airHint(
  op: number | null,
  air: number | null,
  threshold = 0.3,
): number | null {
  if (op == null || air == null) return null;
  return Math.abs(op - air) >= threshold ? air : null;
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
