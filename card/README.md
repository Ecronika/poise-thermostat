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
