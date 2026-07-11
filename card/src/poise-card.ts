import { LitElement, css, html, nothing, svg, type PropertyValues } from "lit";
import type { HomeAssistant, LovelaceCard } from "./ha-types.ts";
import { buildBand } from "./comfort.ts";
import { buildMonitor, type Lamp } from "./monitoring.ts";
import {
  type PoiseCardConfig,
  type ResolvedConfig,
  type ChipKey,
  resolveConfig,
} from "./card-config.ts";
import { t } from "./localize.ts";
import "./poise-card-editor.ts";
import "./poise-system-card.ts";
import { chartGeometry, type Sample } from "./history.ts";
import {
  DIAL,
  type DialConfig,
  arcPath,
  pointToValue,
  polar,
  setpointForKey,
  valueToAngle,
} from "./dial.ts";
import { CARD_VERSION, checkCardVersion } from "./version.ts";
import {
  clampLabel,
  clockLabel,
  heldSetpoint,
  holdView,
  minutesUntil,
  presetChip,
  resumeSchedule,
} from "./override.ts";

function presetIcon(p: string): string {
  const m: Record<string, string> = {
    eco: "mdi:leaf",
    boost: "mdi:rocket-launch",
    away: "mdi:home-export-outline",
    comfort: "mdi:sofa",
  };
  return m[p] ?? "mdi:tune";
}

function num(v: unknown): number | null {
  const n = typeof v === "string" ? parseFloat(v) : (v as number);
  return typeof n === "number" && !Number.isNaN(n) ? n : null;
}

export class PoiseCard extends LitElement implements LovelaceCard {
  static properties = { hass: {}, _config: { state: true } };
  hass!: HomeAssistant;
  private _config!: PoiseCardConfig;
  private _history: Sample[] = [];
  private _histFor: string | null = null;
  private _dragging = false;
  private _pending: number | null = null;
  private _dialCfg: DialConfig = DIAL;
  private _r!: ResolvedConfig;

  static getConfigElement(): HTMLElement {
    return document.createElement("poise-card-editor");
  }

  static getStubConfig(hass: HomeAssistant): PoiseCardConfig {
    const entity = Object.keys(hass.states).find(
      (id) =>
        id.startsWith("climate.") &&
        hass.states[id].attributes["comfort_low"] !== undefined,
    );
    return { type: "custom:poise-card", entity: entity ?? "", show_shadow: true };
  }

  setConfig(config: PoiseCardConfig): void {
    if (!config) throw new Error("Invalid configuration");
    if (config.entity && !config.entity.startsWith("climate."))
      throw new Error("Poise card: entity must be a climate entity");
    this._config = { show_shadow: true, ...config };
    this._r = resolveConfig(this._config);
  }

  getCardSize(): number {
    return 4;
  }

  getGridOptions() {
    return this._r?.density === "compact"
      ? { columns: 6, rows: "auto", min_columns: 4, min_rows: 6 }
      : { columns: 12, rows: "auto", min_columns: 6, min_rows: 9 };
  }

  shouldUpdate(changed: PropertyValues): boolean {
    if (this._dragging) return true;
    if (changed.has("_config")) return true;
    const old = changed.get("hass") as HomeAssistant | undefined;
    if (!old || !this._config?.entity) return true;
    return old.states[this._config.entity] !== this.hass.states[this._config.entity];
  }

  private _setpoint(delta: number): void {
    const id = this._config.entity;
    if (!id || !this.hass) return; // M12: hass may be unset during early render
    const st = this.hass.states[id];
    if (!st) return; // entity removed between render and click (M10)
    const step = num(st.attributes["target_temperature_step"]) ?? 0.5;
    // ADR-0059 Defekt 1: re-base the +/- nudge from the SAME value the dial
    // shows (`_pending ?? heldSetpoint(a) ?? …`, the held/commanded `temperature`),
    // NOT the `heat_sp` band edge — else a nudge on a 23° hold jumps to ~20.7.
    const cur = this._pending ?? heldSetpoint(st.attributes) ?? 21;
    this.hass.callService("climate", "set_temperature", {
      entity_id: id,
      temperature: Math.round((cur + delta * step) * 10) / 10,
    });
  }

  protected updated(): void {
    if (this.hass) void checkCardVersion(this, this.hass);
    const id = this._config?.entity;
    if (id && this.hass && this._r?.history.show && this._histFor !== id) {
      this._histFor = id;
      void this._loadHistory(id);
    }
  }

  private async _loadHistory(id: string): Promise<void> {
    if (!this.hass.connection) return;
    const hours = this._r?.history.hours ?? 24;
    const end = new Date();
    const start = new Date(end.getTime() - hours * 3600 * 1000);
    try {
      const resp = await this.hass.connection.sendMessagePromise<
        Record<string, Array<Record<string, unknown>>>
      >({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: [id],
        minimal_response: false,
        no_attributes: false,
      });
      const list = resp?.[id] ?? [];
      let attrs: Record<string, unknown> = {};
      const samples: Sample[] = [];
      for (const e of list) {
        if (e["a"]) attrs = { ...attrs, ...(e["a"] as Record<string, unknown>) };
        const ts = (num(e["lu"]) ?? num(e["lc"]) ?? 0) * 1000;
        samples.push({
          t: ts,
          op: num(attrs["operative_temperature"]) ?? num(attrs["current_temperature"]),
          // ADR-0059 Defekt 1: plot the commanded setpoint (`temperature`), not
          // the `heat_sp` band edge (the comfort band is shaded from low/high).
          sp: num(attrs["temperature"]),
        });
      }
      this._history = samples;
      this.requestUpdate();
    } catch {
      /* graceful: no chart */
    }
  }

  private _moreInfo(): void {
    if (!this._config.entity) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId: this._config.entity },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _chart(low: number | null, high: number | null) {
    const g = chartGeometry(this._history, low, high, 300, 80);
    if (!g) return nothing;
    return html`<svg
      class="chart"
      viewBox="0 0 ${g.width} ${g.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${g.bandTop}
        width=${g.width}
        height=${Math.max(0, g.bandBottom - g.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${g.spPath} class="csp"></polyline>
      <polyline points=${g.opPath} class="cop"></polyline>
    </svg>`;
  }

  render() {
    const lang = this.hass?.locale?.language;
    const id = this._config?.entity;
    const st = id ? this.hass.states[id] : undefined;
    if (!st) {
      return html`<ha-card
        ><div class="empty">${t(lang, "no_entity")}</div></ha-card
      >`;
    }
    const a = st.attributes;
    const operative =
      num(a["operative_temperature"]) ?? num(a["current_temperature"]);
    const setpoint = num(a["heat_sp"]) ?? num(a["temperature"]);
    const band = buildBand({
      operative,
      setpoint,
      low: num(a["comfort_low"]),
      high: num(a["comfort_high"]),
      category: (a["category"] as string) ?? null,
    });

    const r = this._r;
    return html`<ha-card .header=${a["friendly_name"] ?? "Poise"}>
      <div class="wrap ${r.density === "compact" ? "compact" : ""}">
        ${this._dial(a, lang)}
        <div class="verdict">
          ${band ? t(lang, band.verdict) : t(lang, "unknown")}
          ${band?.category ? html`<span class="cat">Kat. ${band.category}</span>` : nothing}
        </div>
        ${this._holdPill(a, lang)}
        ${r.controls === "buttons"
          ? this._control(this._pending ?? setpoint, lang)
          : nothing}
        ${this._presets(a, lang)}
        ${r.history.show
          ? this._chart(num(a["comfort_low"]), num(a["comfort_high"]))
          : nothing}
        ${this._monitor(a, band, lang)} ${this._chips(a, lang)}
        ${this._learn(a, lang)}
      </div>
    </ha-card>`;
  }

  private _dial(a: Record<string, unknown>, lang?: string) {
    const op = num(a["operative_temperature"]) ?? num(a["current_temperature"]);
    // ADR-0059 Defekt 1: the dial centre number + handle marker show the
    // commanded/held setpoint (`temperature`), NOT `heat_sp` — the latter is
    // only the comfort-band lower edge (the band arc below keeps low/high).
    const actualSp = heldSetpoint(a);
    const cfg: DialConfig = {
      min: num(a["min_temp"]) ?? DIAL.min,
      max: num(a["max_temp"]) ?? DIAL.max,
      start: DIAL.start,
      sweep: DIAL.sweep,
    };
    this._dialCfg = cfg.max > cfg.min ? cfg : DIAL;
    const sp = this._pending ?? actualSp ?? op ?? this._dialCfg.min;
    const low = num(a["comfort_low"]);
    const high = num(a["comfort_high"]);
    const cx = 100;
    const cy = 100;
    const r = 80;
    const track = arcPath(cx, cy, r, DIAL.start, DIAL.start + DIAL.sweep);
    const bandArc =
      low != null && high != null
        ? arcPath(
            cx, cy, r,
            valueToAngle(Math.min(low, high), this._dialCfg),
            valueToAngle(Math.max(low, high), this._dialCfg),
          )
        : "";
    const action = String(a["hvac_action"] ?? "");
    const hcls = action === "heating" ? "heat" : action === "cooling" ? "cool" : "";
    const h = polar(cx, cy, r, valueToAngle(sp, this._dialCfg));
    const opA =
      op != null ? polar(cx, cy, r, valueToAngle(op, this._dialCfg)) : null;
    // ADR-0057: mould-protection floor as an orange tick on the dial, drawn only
    // when the value is inside the visible arc (silently skipped otherwise).
    const mould = num(a["mould_floor"]);
    const showMould =
      mould != null &&
      mould > this._dialCfg.min &&
      mould < this._dialCfg.max;
    const mAng = showMould ? valueToAngle(mould as number, this._dialCfg) : 0;
    const mIn = showMould ? polar(cx, cy, r - 9, mAng) : null;
    const mOut = showMould ? polar(cx, cy, r + 9, mAng) : null;
    const mLbl = showMould ? polar(cx, cy, r + 17, mAng) : null;
    const interactive = this._r.controls === "dial";
    // ADR-0059 §4: while dragging the dial, surface the hold validity ("valid
    // until 22:00") from override_expires_at — the explain-at-the-moment cue.
    const validUntil = this._dragging
      ? clockLabel(a["override_expires_at"], lang)
      : null;
    const valText = `${sp.toFixed(1)} °C${validUntil ? ` · ${t(lang, "valid_until")} ${validUntil}` : ""}`;
    return html`<div class="dialwrap">
      <svg
        class="dial ${interactive ? "" : "ro"}"
        viewBox="0 0 200 200"
        role=${interactive ? "slider" : "img"}
        tabindex=${interactive ? 0 : -1}
        aria-label=${t(lang, "setpoint")}
        aria-valuemin=${this._dialCfg.min}
        aria-valuemax=${this._dialCfg.max}
        aria-valuenow=${sp}
        aria-valuetext=${valText}
        @keydown=${this._onKey}
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${track}></path>
        <path class="bandarc" d=${bandArc}></path>
        ${showMould && mIn && mOut && mLbl
          ? svg`<line class="mould" x1=${mIn.x.toFixed(1)} y1=${mIn.y.toFixed(1)} x2=${mOut.x.toFixed(1)} y2=${mOut.y.toFixed(1)}><title>${t(lang, "mould")} ${(mould as number).toFixed(1)}°</title></line><text class="mlbl" x=${mLbl.x.toFixed(1)} y=${mLbl.y.toFixed(1)}>${(mould as number).toFixed(0)}°</text>`
          : nothing}
        <circle
          class="opdot"
          cx=${(opA?.x ?? 0).toFixed(1)}
          cy=${(opA?.y ?? 0).toFixed(1)}
          r=${opA ? 5 : 0}
        ></circle>
        <circle class="handle ${hcls}" cx=${h.x.toFixed(1)} cy=${h.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div
          class="ctrclick"
          role="button"
          tabindex="0"
          aria-label=${t(lang, "details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          <div class="op">${op != null ? op.toFixed(1) : "—"}<span>°C</span></div>
          <div class="soll">${t(lang, "setpoint")} <b>${sp.toFixed(1)}°</b></div>
          ${validUntil
            ? html`<div class="valid">${t(lang, "valid_until")} ${validUntil}</div>`
            : nothing}
        </div>
      </div>
    </div>`;
  }

  private _fromPointer(ev: PointerEvent, svg: SVGSVGElement): void {
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !this._config.entity) return;
    const vx = ((ev.clientX - rect.left) / rect.width) * 200 - 100;
    const vy = ((ev.clientY - rect.top) / rect.height) * 200 - 100;
    const step =
      num(
        this.hass.states[this._config.entity]?.attributes[
          "target_temperature_step"
        ],
      ) ?? 0.5;
    this._pending = Math.round(pointToValue(vx, vy, this._dialCfg) / step) * step;
    this.requestUpdate();
  }

  private _onDown(ev: PointerEvent): void {
    if (!this._config.entity || this._r.controls !== "dial") return;
    ev.preventDefault();
    const svg = ev.currentTarget as SVGSVGElement;
    svg.setPointerCapture(ev.pointerId);
    this._dragging = true;
    this._fromPointer(ev, svg);
  }

  private _onMove(ev: PointerEvent): void {
    if (this._dragging) this._fromPointer(ev, ev.currentTarget as SVGSVGElement);
  }

  private _onUp(): void {
    if (!this._dragging) return;
    this._dragging = false;
    const v = this._pending;
    this._pending = null;
    if (v != null && this._config.entity) {
      this.hass.callService("climate", "set_temperature", {
        entity_id: this._config.entity,
        temperature: v,
      });
    }
    this.requestUpdate();
  }

  private _onKey(ev: KeyboardEvent): void {
    const id = this._config.entity;
    if (!id || this._r.controls !== "dial") return;
    const st = this.hass.states[id];
    if (!st) return;
    const step = num(st.attributes["target_temperature_step"]) ?? 0.5;
    // ADR-0059 Defekt 1: arrow keys re-base from the shown/held setpoint
    // (mirrors the dial's `_pending ?? heldSetpoint(a) ?? … min`), not the
    // `heat_sp` band edge — keeps the keyboard step consistent with the display.
    const cur =
      this._pending ?? heldSetpoint(st.attributes) ?? this._dialCfg.min;
    const next = setpointForKey(ev.key, cur, step, this._dialCfg);
    if (next == null) return;
    ev.preventDefault();
    this.hass.callService("climate", "set_temperature", {
      entity_id: id,
      temperature: next,
    });
  }

  private _onActivateKey(ev: KeyboardEvent): void {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      this._moreInfo();
    }
  }

  private _control(setpoint: number | null, lang?: string) {
    return html`<div class="ctl">
      <ha-icon-button @click=${() => this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${t(lang, "setpoint")}</span
        ><strong>${setpoint != null ? setpoint.toFixed(1) : "—"}°C</strong>
      </div>
      <ha-icon-button @click=${() => this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`;
  }

  private _setPreset(mode: string): void {
    const id = this._config.entity;
    if (!id || !this.hass) return;
    this.hass.callService("climate", "set_preset_mode", {
      entity_id: id,
      preset_mode: mode,
    });
  }

  // ADR-0059 §4: the Hold-pill X resumes the schedule / drops the manual hold.
  private _resumeSchedule(): void {
    const id = this._config.entity;
    if (!id || !this.hass) return;
    resumeSchedule(this.hass, id);
  }

  // ADR-0057: optional preset row from the entity's own preset_modes, calling
  // climate.set_preset_mode. Hidden when the section is off or no presets exist.
  private _presets(a: Record<string, unknown>, lang?: string) {
    if (!this._r.presets) return nothing;
    const modes = a["preset_modes"];
    if (!Array.isArray(modes) || !modes.length) return nothing;
    const cur = a["preset_mode"] == null ? null : String(a["preset_mode"]);
    // ADR-0059 §4: Boost is timed — show its remaining minutes from boost_expires_at.
    const boostMin = minutesUntil(a["boost_expires_at"]);
    return html`<div class="presets" role="group" aria-label=${t(lang, "presets")}>
      ${modes.map((m) => {
        const key = String(m);
        const kl = key.toLowerCase();
        return html`<button
          class="preset ${cur === key ? "on" : ""}"
          aria-pressed=${cur === key ? "true" : "false"}
          @click=${() => this._setPreset(key)}
        >
          <ha-icon icon=${presetIcon(kl)}></ha-icon>
          <span>${t(lang, kl) || key}</span>
          ${kl === "boost" && boostMin != null
            ? html`<em>${boostMin} ${t(lang, "min_left")}</em>`
            : nothing}
        </button>`;
      })}
    </div>`;
  }

  // ADR-0059 §4: manual-hold ("Hold") pill — hand icon, "Manual 22.5° · 45 min",
  // and an X that resumes the schedule. A `permanent` policy shows "Manual
  // (permanent)" with no countdown; the countdown reuses the min_left minute
  // token, like the preheating/coasting chips.
  private _holdPill(a: Record<string, unknown>, lang?: string) {
    if (!a["override_active"]) return nothing;
    const sp = heldSetpoint(a);
    const v = holdView(lang, sp, a["override_policy"], a["override_expires_at"]);
    return html`<div class="hold">
      <div class="chip hold-chip">
        <ha-icon icon="mdi:hand-back-right"></ha-icon><span>${v.label}</span>
        ${v.minutes != null
          ? html`<em>· ${v.minutes} ${t(lang, "min_left")}</em>`
          : nothing}
      </div>
      <button
        class="resume"
        aria-label=${t(lang, "resume_schedule")}
        title=${t(lang, "resume_schedule")}
        @click=${this._resumeSchedule}
      >
        <ha-icon icon="mdi:close"></ha-icon>
      </button>
    </div>`;
  }

  private _chips(a: Record<string, unknown>, lang?: string) {
    const r = this._r;
    const chips = [];
    if (r.chips.has("hvac")) {
      if (a["preheating"])
        chips.push(this._chip("mdi:fire-circle", t(lang, "preheating"), a["minutes_to_comfort"], lang));
      if (a["coasting"])
        chips.push(this._chip("mdi:coffee", t(lang, "coasting"), a["minutes_to_setback"], lang));
      // ADR-0059 §4: preset fallback chip — live now that `preset` is published,
      // shown only when the dedicated preset section is off (else it duplicates).
      const pc = presetChip(lang, a["preset"], r.presets);
      if (pc) chips.push(this._chip(presetIcon(pc.key), pc.label));
      if (a["heating_failure"]) chips.push(this._chip("mdi:alert", t(lang, "failure")));
      // ADR-0059 §4: explain the clamp ("22.5° instead of 24° (norm limit)") from
      // the pre-clamp request vs the effective setpoint, not just "clamped".
      if (a["override_clamped"])
        chips.push(
          this._chip(
            "mdi:arrow-collapse-vertical",
            clampLabel(
              lang,
              heldSetpoint(a),
              num(a["override_requested"]),
            ),
          ),
        );
      // ADR-0046 §8: compressor guard is holding a cool/dry start or flip.
      if (a["mode_nudge_blocked"])
        chips.push(
          this._chip("mdi:timer-sand", `${t(lang, "compressor_guard")}: ${a["mode_nudge_blocked"]}`),
        );
      const cause = a["binding_lower_cause"];
      if (cause && cause !== "en16798")
        chips.push(this._chip("mdi:shield-alert", String(cause)));
    }
    if (r.chips.has("window")) {
      if (a["window_open"])
        chips.push(
          this._chip(
            "mdi:window-open",
            t(lang, a["window_auto_detected"] ? "window_auto" : "window"),
          ),
        );
      if (a["window_bypass"])
        chips.push(this._chip("mdi:window-closed-variant", t(lang, "bypass")));
    }
    return chips.length
      ? html`<div
          class="chips"
          role="button"
          tabindex="0"
          aria-label=${t(lang, "details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          ${chips}
        </div>`
      : nothing;
  }

  private _chip(icon: string, label: string, minutes?: unknown, lang?: string) {
    const m = num(minutes);
    return html`<div class="chip">
      <ha-icon icon=${icon}></ha-icon><span>${label}</span>
      ${m != null ? html`<em>${Math.round(m)} ${t(lang, "min_left")}</em>` : nothing}
    </div>`;
  }

  private _monitor(
    a: Record<string, unknown>,
    band: ReturnType<typeof buildBand>,
    lang?: string,
  ) {
    const lamps = buildMonitor(
      {
        temperature:
          num(a["operative_temperature"]) ?? num(a["current_temperature"]),
        comfortVerdict: band?.verdict ?? null,
        humidity: num(a["humidity"]) ?? num(a["current_humidity"]),
        co2: num(a["co2"]) ?? num(a["carbon_dioxide"]),
        pmv: num(a["pmv"]),
        ppd: num(a["ppd"]),
        ca: {
          deviationK: num(a["ca_deviation_k"]),
          timeInBand: num(a["ca_time_in_band"]),
          cyclesPerH: num(a["ca_cycles_per_h"]),
        },
      },
      {
        temperature_scale: this._config.temperature_scale,
        humidity_thresholds: this._config.humidity_thresholds,
        co2_scheme: this._config.co2_scheme,
        co2_thresholds: this._config.co2_thresholds,
        outdoor_co2: num(a["outdoor_co2"]),
      },
    );
    // ADR-0057: honour the per-element section toggles. The pmv lamp has its own
    // switch; every other lamp is gated by the chips set. Unknown keys are kept
    // (defensive) so a future lamp is visible until explicitly hidden.
    const r = this._r;
    const shown = lamps.filter((l) =>
      l.key === "pmv" ? r.pmv : r.chips.has(l.key as ChipKey),
    );
    if (!shown.length) return nothing;
    return html`<div
      class="monitor"
      role="group"
      aria-label=${t(lang, "air_quality")}
    >
      ${shown.map((l) => this._lamp(l, lang))}
    </div>`;
  }

  private _lamp(l: Lamp, lang?: string) {
    const label = t(lang, l.key);
    const lvl = t(lang, l.level === "unknown" ? "unknown" : "air_" + l.level);
    let val = "—";
    if (l.value != null) {
      val =
        l.key === "temperature" ? l.value.toFixed(1) : String(Math.round(l.value));
    }
    const desc = `${label}: ${val} ${l.unit} — ${lvl}`;
    return html`<div class="lamp" title=${desc} aria-label=${desc}>
      <span class="dot" style="background:${l.color}"></span>
      <span class="lk">${label}</span>
      <span class="lv">${val}<small>${l.unit}</small></span>
    </div>`;
  }

  private _learn(a: Record<string, unknown>, lang?: string) {
    const conf = num(a["confidence"]);
    const showBar = this._r.learning && conf != null;
    const shadow =
      this._r.shadowPill &&
      (a["mpc_active"] || a["tpi_active"] || a["pi_active"]);
    if (!showBar && !shadow) return nothing;
    const sp = num(a["pi_setpoint"]);
    const mp = num(a["mpc_setpoint"]);
    const would = a["tpi_active"]
      ? `TPI ${Math.round(num(a["tpi_valve_percent"]) ?? 0)}%`
      : a["pi_active"] && sp != null
        ? `PI ${sp.toFixed(1)}°`
        : a["mpc_active"] && mp != null
          ? `MPC ${mp.toFixed(1)}°`
          : "";
    return html`<div class="learn">
      ${showBar
        ? html`<div class="bar">
            <i style="width:${((conf ?? 0) * 100).toFixed(0)}%"></i>
          </div>
          <span>${t(lang, "learning")} ${((conf ?? 0) * 100).toFixed(0)}%</span>`
        : nothing}
      ${shadow
        ? html`<div class="pill">
            ${t(lang, "shadow")}${would ? html` · ${would}` : nothing}
          </div>`
        : nothing}
    </div>`;
  }

  static styles = css`
    .wrap { padding: 8px 16px 16px; }
    .band {
      position: relative; height: 26px; margin: 8px 0 22px;
      border-radius: 13px; background: var(--divider-color, #e0e0e0);
    }
    .fill {
      position: absolute; top: 0; bottom: 0; border-radius: 13px;
      background: color-mix(in srgb, var(--success-color, #4caf50) 35%, transparent);
    }
    .mark { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px; transform: translateX(-2px); }
    .mark.op { background: var(--primary-color, #2196f3); }
    .mark.sp { background: var(--secondary-text-color, #888); }
    .tick { position: absolute; top: 28px; font-size: 11px; color: var(--secondary-text-color); transform: translateX(-50%); }
    .big { font-size: 40px; font-weight: 600; line-height: 1; }
    .big span { font-size: 18px; color: var(--secondary-text-color); }
    .verdict { color: var(--secondary-text-color); margin-bottom: 8px; }
    .cat { margin-left: 8px; opacity: 0.8; }
    .ctl { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 10px 0 4px; }
    .sp { text-align: center; }
    .sp span { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .sp strong { font-size: 20px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .chip ha-icon { --mdc-icon-size: 16px; }
    .chip em { font-style: normal; color: var(--secondary-text-color); }
    .learn { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
    .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary-color); }
    .learn span { font-size: 12px; color: var(--secondary-text-color); }
    .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px;
      background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .chart { width: 100%; height: 80px; margin: 10px 0 2px; display: block; }
    .cband { fill: color-mix(in srgb, var(--success-color, #4caf50) 16%, transparent); }
    .cop { fill: none; stroke: var(--primary-color, #2196f3); stroke-width: 2; vector-effect: non-scaling-stroke; }
    .csp { fill: none; stroke: var(--secondary-text-color, #888); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
    .chips { cursor: pointer; }
    .monitor { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 2px; }
    .lamp { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .lamp .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
    .lamp .lk { color: var(--secondary-text-color); }
    .lamp .lv { font-weight: 600; }
    .lamp .lv small { font-weight: 400; color: var(--secondary-text-color); margin-left: 1px; }
    .dialwrap { position: relative; width: 100%; max-width: 230px; margin: 6px auto 2px; }
    .dial:focus, .ctrclick:focus, .chips:focus { outline: none; }
    .dial:focus-visible, .ctrclick:focus-visible, .chips:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: 2px; border-radius: 10px;
    }
    .dial { width: 100%; display: block; touch-action: none; cursor: pointer; }
    .track { fill: none; stroke: var(--divider-color, #444); stroke-width: 10; stroke-linecap: round; }
    .bandarc { fill: none; stroke: color-mix(in srgb, var(--success-color, #4caf50) 55%, transparent); stroke-width: 10; stroke-linecap: round; }
    .opdot { fill: var(--primary-text-color, #fff); }
    .handle { fill: var(--primary-color, #2196f3); stroke: var(--card-background-color, #1c1c1c); stroke-width: 2; }
    .dialctr { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
    .ctrclick { pointer-events: auto; cursor: pointer; display: flex; flex-direction: column; align-items: center; }
    .handle.heat { fill: var(--state-climate-heat-color, #ff8100); }
    .handle.cool { fill: var(--state-climate-cool-color, #2b9af9); }
    .wrap.compact .dialwrap { max-width: 150px; }
    .dialctr .op { font-size: 38px; font-weight: 600; line-height: 1; }
    .dialctr .op span { font-size: 16px; color: var(--secondary-text-color); }
    .dialctr .soll { font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
    .mould { stroke: var(--warning-color, #ff9800); stroke-width: 3; stroke-linecap: round; }
    .mlbl { fill: var(--warning-color, #ff9800); font-size: 11px; font-weight: 600;
      text-anchor: middle; dominant-baseline: middle; }
    .dial.ro { cursor: default; }
    .presets { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 2px; }
    .preset { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px;
      border: 1px solid var(--divider-color, #e0e0e0); border-radius: 16px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color); font: inherit; font-size: 13px; cursor: pointer; }
    .preset ha-icon { --mdc-icon-size: 16px; }
    .preset.on { background: var(--primary-color, #2196f3);
      color: var(--text-primary-color, #fff); border-color: var(--primary-color, #2196f3); }
    .preset:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .preset em { font-style: normal; color: var(--secondary-text-color); margin-left: 2px; }
    .preset.on em { color: inherit; opacity: 0.85; }
    .hold { display: flex; align-items: center; gap: 6px; margin: 8px 0 2px; }
    .hold-chip { flex: 1 1 auto; }
    .resume { flex: none; display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; padding: 0; border: none; border-radius: 50%;
      background: var(--secondary-background-color); color: var(--secondary-text-color); cursor: pointer; }
    .resume ha-icon { --mdc-icon-size: 18px; }
    .resume:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .valid { font-size: 11px; color: var(--secondary-text-color); margin-top: 3px; }
    .wrap.compact { padding: 6px 12px 12px; }
    .wrap.compact .dialctr .op { font-size: 30px; }
    .wrap.compact .presets, .wrap.compact .monitor, .wrap.compact .chips { gap: 4px; }
  `;
}

(window as unknown as { customCards: unknown[] }).customCards =
  (window as unknown as { customCards: unknown[] }).customCards || [];
(window as unknown as { customCards: unknown[] }).customCards.push({
  type: "poise-card",
  name: "Poise Thermostat",
  preview: true,
  description: "EN-16798 comfort band, operative temperature & shadow state for Poise.",
});

if (!customElements.get("poise-card")) {
  customElements.define("poise-card", PoiseCard);
}
console.info(`%c POISE-CARD ${CARD_VERSION} `, "background:#2196f3;color:#fff");
