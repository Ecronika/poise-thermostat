import type { LovelaceCardConfig } from "./ha-types.ts";

export interface PoiseCardConfig extends LovelaceCardConfig {
  type: string;
  entity?: string; // a Poise climate entity
  show_shadow?: boolean; // show MPC/TPI/PI shadow pill (default true)
}
