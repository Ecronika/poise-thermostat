import { build } from "esbuild";
import { readFileSync } from "node:fs";
const version = JSON.parse(readFileSync("./package.json", "utf8")).version;
await build({
  entryPoints: ["src/poise-card.ts"],
  bundle: true,
  format: "esm",
  minify: true,
  target: "es2021",
  legalComments: "none",
  outfile: "../custom_components/poise/frontend/poise-card.js",
  define: { CARD_BUILD_VERSION: JSON.stringify(version) },
  banner: { js: `/* poise-card ${version} — bundled, served by the Poise integration (ADR-0040) */` },
});
console.log("built poise-card.js", version);
