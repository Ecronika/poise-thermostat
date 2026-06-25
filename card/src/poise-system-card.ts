import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import type { HomeAssistant, LovelaceCard } from "./ha-types.ts";
import type { LovelaceCardConfig } from "./ha-types.ts";
import { t } from "./localize.ts";
import { checkCardVersion } from "./version.ts";

interface SysConfig extends LovelaceCardConfig {
  entity?: string;
}

function num(v: unknown): number | null {
  const n = typeof v === "string" ? parseFloat(v) : (v as number);
  return typeof n === "number" && !Number.isNaN(n) ? n : null;
}

export class PoiseSystemCard extends LitElement implements LovelaceCard {
  static properties = { hass: {}, _config: { state: true } };
  hass!: HomeAssistant;
  private _config!: SysConfig;

  static getConfigElement(): HTMLElement {
    return document.createElement("poise-system-card-editor");
  }

  static getStubConfig(hass: HomeAssistant): SysConfig {
    const e = Object.keys(hass.states).find(
      (id) =>
        id.startsWith("binary_sensor.") &&
        hass.states[id].attributes["zone_count"] !== undefined,
    );
    return { type: "custom:poise-system-card", entity: e ?? "" };
  }

  setConfig(config: SysConfig): void {
    if (!config) throw new Error("Invalid configuration");
    this._config = config;
  }

  getCardSize(): number {
    return 2;
  }

  getGridOptions() {
    // Natural height by default; min_rows floors any numeric override so a
    // manually resized hub card can never clip its content.
    return { columns: 12, rows: "auto", min_columns: 4, min_rows: 4 };
  }

  protected updated(): void {
    if (this.hass) void checkCardVersion(this, this.hass);
  }

  shouldUpdate(changed: PropertyValues): boolean {
    if (changed.has("_config")) return true;
    const old = changed.get("hass") as HomeAssistant | undefined;
    if (!old || !this._config?.entity) return true;
    return old.states[this._config.entity] !== this.hass.states[this._config.entity];
  }

  private _moreInfo(): void {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId: this._config.entity },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onActivateKey(ev: KeyboardEvent): void {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      this._moreInfo();
    }
  }

  render() {
    const lang = this.hass?.locale?.language;
    const id = this._config?.entity;
    const st = id ? this.hass.states[id] : undefined;
    if (!st) {
      return html`<ha-card
        ><div class="empty">${t(lang, "no_system")}</div></ha-card
      >`;
    }
    const a = st.attributes;
    const on = st.state === "on";
    const flow = num(a["flow_target"]);
    const shed = num(a["shed_count"]) ?? 0;
    const grants = (a["source_grants"] as Record<string, string>) ?? {};
    const grantKeys = Object.keys(grants);
    return html`<ha-card .header=${t(lang, "sys_title")}>
      <div
        class="wrap"
        role="button"
        tabindex="0"
        aria-label=${t(lang, "details")}
        @click=${this._moreInfo}
        @keydown=${this._onActivateKey}
      >
        <div class="state ${on ? "on" : ""}">
          <ha-icon icon=${on ? "mdi:fire" : "mdi:fire-off"}></ha-icon>
          <span>${on ? t(lang, "demand_on") : t(lang, "demand_off")}</span>
          ${a["frost_override"]
            ? html`<em class="frost">${t(lang, "frost")}</em>`
            : nothing}
        </div>
        <div class="stats">
          <div>
            <strong>${num(a["active_zones"]) ?? 0}</strong
            ><span>${t(lang, "heating_n")}</span>
          </div>
          <div>
            <strong
              >${num(a["controlling_zones"]) ?? 0}/${num(a["zone_count"]) ?? 0}</strong
            ><span>${t(lang, "zones")}</span>
          </div>
          ${flow != null
            ? html`<div>
                <strong>${flow.toFixed(0)}°</strong><span>${t(lang, "flow")}</span>
              </div>`
            : nothing}
          ${shed > 0
            ? html`<div>
                <strong>${shed}</strong><span>${t(lang, "shed")}</span>
              </div>`
            : nothing}
        </div>
        ${grantKeys.length
          ? html`<div class="grants">
              ${grantKeys.map(
                (z) => html`<span class="chip">${z}: ${grants[z]}</span>`,
              )}
            </div>`
          : nothing}
      </div>
    </ha-card>`;
  }

  static styles = css`
    .wrap { padding: 8px 16px 16px; cursor: pointer; }
    .wrap:focus { outline: none; }
    .wrap:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: -2px; border-radius: 10px;
    }
    .state { display: flex; align-items: center; gap: 8px; font-size: 18px; }
    .state ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
    .state.on ha-icon { color: var(--error-color, #d33); }
    .frost { font-style: normal; margin-left: auto; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; background: var(--info-color, #2196f3); color: var(--text-primary-color, #fff); }
    .stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
    .stats strong { font-size: 20px; }
    .stats span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .grants { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .chip { padding: 3px 8px; border-radius: 12px; font-size: 12px;
      background: var(--secondary-background-color); }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;
}

class PoiseSystemCardEditor extends LitElement {
  static properties = { hass: {}, _config: { state: true } };
  hass!: HomeAssistant;
  private _config!: SysConfig;

  setConfig(config: SysConfig): void {
    this._config = config;
  }

  protected shouldUpdate(c: PropertyValues): boolean {
    return c.has("hass") || c.has("_config");
  }

  private _changed(ev: CustomEvent): void {
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: ev.detail.value } }),
    );
  }

  render() {
    if (!this.hass || !this._config) return html``;
    return html`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[
        { name: "entity", required: true, selector: { entity: { integration: "poise", domain: "binary_sensor" } } },
      ]}
      .computeLabel=${(s: { name: string }) => s.name}
      @value-changed=${this._changed}
    ></ha-form>`;
  }
}

if (!customElements.get("poise-system-card-editor")) {
  customElements.define("poise-system-card-editor", PoiseSystemCardEditor);
}

if (!customElements.get("poise-system-card")) {
  customElements.define("poise-system-card", PoiseSystemCard);
}
(window as unknown as { customCards: unknown[] }).customCards =
  (window as unknown as { customCards: unknown[] }).customCards || [];
(window as unknown as { customCards: unknown[] }).customCards.push({
  type: "poise-system-card",
  name: "Poise System",
  preview: true,
  description: "Multi-zone boiler demand, flow & load shedding for the Poise hub.",
});
