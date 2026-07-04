# Poise Card (source)

Lit/TypeScript source of the Poise Lovelace card (ADR-0040). The **built**
artifact is shipped *inside the integration* at
`custom_components/poise/frontend/poise-card.js` and is **served + auto-registered
by Poise itself** — users install only the integration; the card appears in the
card picker after a restart (Lovelace storage mode). No separate HACS plugin.

## Develop
```bash
cd card
npm install
npm run typecheck     # tsc --noEmit (strict)
npm test              # node --test (comfort.ts band math)
npm run build         # esbuild bundle -> ../custom_components/poise/frontend/poise-card.js
```
Only `lit` is a runtime dependency (bundled); HA types are declared locally in
`src/ha-types.ts`. The card reads Poise's climate attributes (ADR-0016) and the
"Poise System" hub `binary_sensor` (ADR-0038/0039) — no device-specific logic.

## Configure (ADR-0057)

Set options in the dashboard's **visual editor** or in YAML. All layout/display
resolution is pure and unit-tested in `card-config.ts` (`resolveConfig`);
unknown or invalid values fall back silently to defaults.

| Key | Values (default **bold**) |
| --- | --- |
| `density` | **`comfortable`** · `compact` |
| `controls` | **`dial`** (drag) · `buttons` (+/− steppers) · `none` (display-only / wall-tablet lock) |
| `history` | `{ show: bool, hours: 12\|24\|48 }` · `false` to hide (default `{ show: true, hours: 24 }`) |
| `sections.chips` | subset of `[hvac, window, temperature, humidity, co2, ca]` · `false` = none (default: all) |
| `sections.pmv` · `.shadow_pill` · `.learning` · `.presets` | booleans, default **true** |
| `temperature_scale` · `humidity_thresholds` · `co2_scheme` · `co2_thresholds` | ADR-0049 room-condition traffic-light thresholds |

Legacy aliases: `compact: true` → `density: compact`; `show_shadow` →
`sections.shadow_pill`. The dial renders a **mould-limit tick** at the
anti-condensation floor when a humidity sensor is present.

```yaml
type: custom:poise-card
entity: climate.wohnzimmer
density: comfortable
controls: dial                       # dial | buttons | none
history: { show: true, hours: 24 }
sections:
  chips: [hvac, window, humidity, co2]
  pmv: true
  shadow_pill: true
  learning: true
  presets: true
```
