import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import type { HomeAssistant, LovelaceCard } from "./ha-types.ts";
import { buildBand } from "./comfort.ts";
import type { PoiseCardConfig } from "./card-config.ts";
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
  valueToAngle,
} from "./dial.ts";
import { CARD_VERSION, checkCardVersion } from "./version.ts";

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
  }

  getCardSize(): number {
    return 4;
  }

  getGridOptions() {
    // Default to natural height (rows:"auto" → HA sizes the cell to content).
    // min_rows is a *floor*: the user may still drag the card larger in the
    // Sections editor, but HA clamps any numeric rows up to this minimum, so
    // it can never be shrunk small enough to clip the content — and a stale
    // override saved into the dashboard (e.g. an old rows:8) is healed too.
    return this._config?.compact
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
    if (!id) return;
    const st = this.hass.states[id];
    if (!st) return; // entity removed between render and click (M10)
    const step = num(st.attributes["target_temperature_step"]) ?? 0.5;
    const cur =
      num(st.attributes["heat_sp"]) ?? num(st.attributes["temperature"]) ?? 21;
    this.hass.callService("climate", "set_temperature", {
      entity_id: id,
      temperature: Math.round((cur + delta * step) * 10) / 10,
    });
  }

  protected updated(): void {
    if (this.hass) void checkCardVersion(this, this.hass);
    const id = this._config?.entity;
    if (id && this.hass && this._histFor !== id) {
      this._histFor = id;
      void this._loadHistory(id);
    }
  }

  private async _loadHistory(id: string): Promise<void> {
    if (!this.hass.connection) return;
    const end = new Date();
    const start = new Date(end.getTime() - 24 * 3600 * 1000);
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
          sp: num(attrs["heat_sp"]) ?? num(attrs["temperature"]),
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

    return html`<ha-card .header=${a["friendly_name"] ?? "Poise"}>
      <div class="wrap ${this._config.compact ? "compact" : ""}">
        ${this._dial(a, lang)}
        <div class="verdict">
          ${band ? t(lang, band.verdict) : t(lang, "unknown")}
          ${band?.category ? html`<span class="cat">Kat. ${band.category}</span>` : nothing}
        </div>
        ${this._config.compact
          ? nothing
          : html`${this._control(this._pending ?? setpoint, lang)}
              ${this._chart(num(a["comfort_low"]), num(a["comfort_high"]))}
              ${this._chips(a, lang)}`}
        ${this._learn(a, lang)}
      </div>
    </ha-card>`;
  }

  private _dial(a: Record<string, unknown>, lang?: string) {
    const op = num(a["operative_temperature"]) ?? num(a["current_temperature"]);
    const actualSp = num(a["heat_sp"]) ?? num(a["temperature"]);
    // Scale the dial to the device's own setpoint range, not a hard [16,28]
    // (M12). Never invent a 16 °C setpoint — fall back to the operative reading.
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
    return html`<div class="dialwrap">
      <svg
        class="dial"
        viewBox="0 0 200 200"
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${track}></path>
        <path class="bandarc" d=${bandArc}></path>
        <circle
          class="opdot"
          cx=${(opA?.x ?? 0).toFixed(1)}
          cy=${(opA?.y ?? 0).toFixed(1)}
          r=${opA ? 5 : 0}
        ></circle>
        <circle class="handle ${hcls}" cx=${h.x.toFixed(1)} cy=${h.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div class="ctrclick" @click=${this._moreInfo}>
          <div class="op">${op != null ? op.toFixed(1) : "—"}<span>°C</span></div>
          <div class="soll">${t(lang, "setpoint")} <b>${sp.toFixed(1)}°</b></div>
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
    if (!this._config.entity) return;
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

  private _chips(a: Record<string, unknown>, lang?: string) {
    const chips = [];
    if (a["preheating"])
      chips.push(this._chip("mdi:fire-circle", t(lang, "preheating"), a["minutes_to_comfort"], lang));
    if (a["coasting"])
      chips.push(this._chip("mdi:coffee", t(lang, "coasting"), a["minutes_to_setback"], lang));
    if (a["window_open"])
      chips.push(
        this._chip(
          "mdi:window-open",
          t(lang, a["window_auto_detected"] ? "window_auto" : "window"),
        ),
      );
    if (a["window_bypass"])
      chips.push(this._chip("mdi:window-closed-variant", t(lang, "bypass")));
    const preset = a["preset"] == null ? "none" : String(a["preset"]);
    if (preset !== "none")
      chips.push(this._chip(presetIcon(preset), t(lang, preset) || preset));
    if (a["heating_failure"]) chips.push(this._chip("mdi:alert", t(lang, "failure")));
    const cause = a["binding_lower_cause"];
    if (cause && cause !== "en16798")
      chips.push(this._chip("mdi:shield-alert", String(cause)));
    return chips.length
      ? html`<div class="chips" @click=${this._moreInfo}>${chips}</div>`
      : nothing;
  }

  private _chip(icon: string, label: string, minutes?: unknown, lang?: string) {
    const m = num(minutes);
    return html`<div class="chip">
      <ha-icon icon=${icon}></ha-icon><span>${label}</span>
      ${m != null ? html`<em>${Math.round(m)} ${t(lang, "min_left")}</em>` : nothing}
    </div>`;
  }

  private _learn(a: Record<string, unknown>, lang?: string) {
    const conf = num(a["confidence"]);
    const shadow =
      this._config.show_shadow &&
      (a["mpc_active"] || a["tpi_active"] || a["pi_active"]);
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
      ${conf != null
        ? html`<div class="bar">
            <i style="width:${(conf * 100).toFixed(0)}%"></i>
          </div>
          <span>${t(lang, "learning")} ${(conf * 100).toFixed(0)}%</span>`
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
    .dialwrap { position: relative; width: 100%; max-width: 230px; margin: 6px auto 2px; }
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
