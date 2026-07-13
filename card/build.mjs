import { build } from "esbuild";
import { readFileSync } from "node:fs";
const version = JSON.parse(readFileSync("./package.json", "utf8")).version;
const outfile = "../custom_components/poise/frontend/poise-card.js";
await build({
  entryPoints: ["src/poise-card.ts"],
  bundle: true,
  format: "esm",
  minify: true,
  target: "es2021",
  legalComments: "none",
  outfile,
  define: { CARD_BUILD_VERSION: JSON.stringify(version) },
  banner: { js: `/* poise-card ${version} — bundled, served by the Poise integration (ADR-0040) */` },
});

// Registration guard (v0.170.2): the whole card is dead if the entry module's
// `customElements.define("poise-card", …)` side-effect is missing from the bundle
// — HA then shows "Custom element doesn't exist: poise-card". This was dropped
// once by an editing accident and went unnoticed because tsc/unit tests import
// pure modules, not the registration side-effect. Fail the build so a broken
// bundle can never be shipped again. (esbuild minifies but keeps the literal
// element name inside customElements.define, so a substring check is robust.)
const bundle = readFileSync(outfile, "utf8");
for (const needle of ['customElements.define("poise-card"', "customCards"]) {
  if (!bundle.includes(needle)) {
    throw new Error(
      `build guard: bundle is missing \`${needle}\` — the card would not register. ` +
        "Check the registration block at the end of src/poise-card.ts.",
    );
  }
}
console.log("built poise-card.js", version, "(registration guard OK)");
