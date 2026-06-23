import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import type { HomeAssistant, LovelaceCard } from "./ha-types.ts";
import { buildBand } from "./comfort.ts";
import type { PoiseCardConfig } from "./card-config.ts";
import { t } from "./localize.ts";
import "./poise-card-editor.ts";
import "./poise-system-card.ts";
import { chartGeometry, type Sample } from "./history.ts";

const CARD_VERSION = "0.52.0";

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

  shouldUpdate(changed: PropertyValues): boolean {
    if (changed.has("_config")) return true;
    const old = changed.get("hass") as HomeAssistant | undefined;
    if (!old || !this._config?.entity) return true;
    return old.states[this._config.entity] !== this.hass.states[this._config.entity];
  }

  private _setpoint(delta: number): void {
    const id = this._config.entity;
    if (!id) return;
    const st = this.hass.states[id];
    const step = num(st.attributes["target_temperature_step"]) ?? 0.5;
    const cur =
      num(st.attributes["heat_sp"]) ?? num(st.attributes["temperature"]) ?? 21;
    this.hass.callService("climate", "set_temperature", {
      entity_id: id,
      temperature: Math.round((cur + delta * step) * 10) / 10,
    });
  }

  protected updated(): void {
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
      <div class="wrap">
        ${this._hero(band, lang)}
        <div class="big">
          ${operative != null ? operative.toFixed(1) : "—"}<span>°C</span>
        </div>
        <div class="verdict">
          ${band ? t(lang, band.verdict) : t(lang, "unknown")}
          ${band?.category ? html`<span class="cat">Kat. ${band.category}</span>` : nothing}
        </div>
        ${this._control(setpoint, lang)}
        ${this._chart(num(a["comfort_low"]), num(a["comfort_high"]))}
        ${this._chips(a, lang)}
        ${this._learn(a, lang)}
      </div>
    </ha-card>`;
  }

  private _hero(band: ReturnType<typeof buildBand>, _lang?: string) {
    if (!band) return nothing;
    const pct = (f: number) => `${(f * 100).toFixed(1)}%`;
    return html`<div class="band">
      <div
        class="fill"
        style="left:${pct(band.lowFrac)};right:${pct(1 - band.highFrac)}"
      ></div>
      ${band.setpointFrac != null
        ? html`<div class="mark sp" style="left:${pct(band.setpointFrac)}"></div>`
        : nothing}
      ${band.operativeFrac != null
        ? html`<div class="mark op" style="left:${pct(band.operativeFrac)}"></div>`
        : nothing}
      <div class="tick" style="left:${pct(band.lowFrac)}">${band.low.toFixed(0)}</div>
      <div class="tick" style="left:${pct(band.highFrac)}">${band.high.toFixed(0)}</div>
    </div>`;
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
    if (a["window_open"]) chips.push(this._chip("mdi:window-open", t(lang, "window")));
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
