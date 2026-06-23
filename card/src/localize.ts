type Dict = Record<string, string>;

const EN: Dict = {
  in_band: "In comfort band",
  cool_edge: "Cool edge of band",
  warm_edge: "Warm edge of band",
  below: "Below comfort band",
  above: "Above comfort band",
  unknown: "No reading",
  preheating: "Pre-heating",
  coasting: "Coasting",
  window: "Window open",
  failure: "Heating failure",
  learning: "Learning",
  shadow: "Shadow active",
  setpoint: "Setpoint",
  no_entity: "Select a Poise thermostat entity.",
  min_left: "min",
};
const DE: Dict = {
  in_band: "Im Komfortband",
  cool_edge: "Untere Bandkante",
  warm_edge: "Obere Bandkante",
  below: "Unter dem Komfortband",
  above: "Über dem Komfortband",
  unknown: "Kein Messwert",
  preheating: "Vorheizen",
  coasting: "Auslaufen",
  window: "Fenster offen",
  failure: "Heizausfall",
  learning: "Lernt",
  shadow: "Shadow aktiv",
  setpoint: "Sollwert",
  no_entity: "Bitte eine Poise-Thermostat-Entität wählen.",
  min_left: "Min",
};

export function t(lang: string | undefined, key: string): string {
  const dict = (lang ?? "en").toLowerCase().startsWith("de") ? DE : EN;
  return dict[key] ?? EN[key] ?? key;
}
