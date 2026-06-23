// Minimal Home Assistant frontend types actually used by the card.
// Keeps the card self-contained (only `lit` as a runtime dependency, ADR-0022).
export interface HassEntity {
  state: string;
  attributes: Record<string, unknown>;
}
export interface HomeAssistant {
  states: Record<string, HassEntity>;
  locale?: { language?: string };
  callService(
    domain: string,
    service: string,
    data?: Record<string, unknown>,
  ): Promise<unknown>;
  connection?: {
    sendMessagePromise<T>(msg: Record<string, unknown>): Promise<T>;
  };
}
export interface LovelaceCardConfig {
  type: string;
  [key: string]: unknown;
}
export interface LovelaceCard extends HTMLElement {
  hass?: HomeAssistant;
  setConfig(config: LovelaceCardConfig): void;
  getCardSize(): number | Promise<number>;
}
