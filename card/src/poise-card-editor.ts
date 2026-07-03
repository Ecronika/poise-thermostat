import { LitElement, html, type PropertyValues } from "lit";
import type { HomeAssistant } from "./ha-types.ts";
import type { PoiseCardConfig } from "./card-config.ts";

const CHIP_OPTIONS = [
  { value: "hvac", label: "HVAC status" },
  { value: "window", label: "Window" },
  { value: "temperature", label: "Temperature" },
  { value: "humidity", label: "Humidity" },
  { value: "co2", label: "CO₂" },
  { value: "ca", label: "Regulation (CA)" },
];

const SCHEMA = [
  {
    name: "entity",
    required: true,
    selector: { entity: { integration: "poise", domain: "climate" } },
  },
  {
    name: "density",
    selector: {
      select: {
        mode: "dropdown",
        options: [
          { value: "comfortable", label: "Comfortable" },
          { value: "compact", label: "Compact" },
        ],
      },
    },
  },
  {
    name: "controls",
    selector: {
      select: {
        mode: "dropdown",
        options: [
          { value: "dial", label: "Dial (drag)" },
          { value: "buttons", label: "Buttons (+/−)" },
          { value: "none", label: "Display only" },
        ],
      },
    },
  },
  {
    type: "expandable",
    name: "history",
    title: "History",
    schema: [
      { name: "show", selector: { boolean: {} } },
      {
        name: "hours",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: 12, label: "12 h" },
              { value: 24, label: "24 h" },
              { value: 48, label: "48 h" },
            ],
          },
        },
      },
    ],
  },
  {
    type: "expandable",
    name: "sections",
    title: "Sections",
    schema: [
      { name: "chips", selector: { select: { multiple: true, options: CHIP_OPTIONS } } },
      { name: "pmv", selector: { boolean: {} } },
      { name: "presets", selector: { boolean: {} } },
      { name: "shadow_pill", selector: { boolean: {} } },
      { name: "learning", selector: { boolean: {} } },
    ],
  },
  {
    type: "expandable",
    name: "",
    title: "Advanced",
    flatten: true,
    schema: [
      {
        name: "temperature_scale",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "comfort", label: "Comfort band" },
              { value: "asr_office", label: "ASR office (≤26 °C)" },
            ],
          },
        },
      },
      {
        name: "co2_scheme",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "uba", label: "UBA (absolute)" },
              { value: "en16798", label: "EN 16798 (outdoor offset)" },
            ],
          },
        },
      },
    ],
  },
];

const LABELS: Record<string, string> = {
  entity: "Entity",
  density: "Density",
  controls: "Controls",
  history: "History",
  sections: "Sections",
  show: "Show graph",
  hours: "Time span",
  chips: "Condition chips",
  pmv: "Comfort (PMV) lamp",
  presets: "Preset buttons",
  shadow_pill: "Shadow pill",
  learning: "Learning bar",
  temperature_scale: "Temperature scale",
  co2_scheme: "CO₂ scale",
};

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
      .computeLabel=${(s: { name: string }) => LABELS[s.name] ?? s.name}
      @value-changed=${this._changed}
    ></ha-form>`;
  }
}

if (!customElements.get("poise-card-editor")) {
  customElements.define("poise-card-editor", PoiseCardEditor);
}
