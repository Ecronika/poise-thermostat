import { LitElement, html, type PropertyValues } from "lit";
import type { HomeAssistant } from "./ha-types.ts";
import type { PoiseCardConfig } from "./card-config.ts";

const SCHEMA = [
  { name: "entity", required: true, selector: { entity: { integration: "poise", domain: "climate" } } },
  { name: "show_shadow", selector: { boolean: {} } },
];

export class PoiseCardEditor extends LitElement {
  static properties = { hass: {}, _config: { state: true } };
  hass!: HomeAssistant;
  private _config!: PoiseCardConfig;

  setConfig(config: PoiseCardConfig): void {
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
      .schema=${SCHEMA}
      .computeLabel=${(s: { name: string }) => s.name}
      @value-changed=${this._changed}
    ></ha-form>`;
  }
}

if (!customElements.get("poise-card-editor")) {
  customElements.define("poise-card-editor", PoiseCardEditor);
}
