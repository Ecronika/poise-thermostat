// Card<->integration version check (Browser-Mod style, ADR-0040).
// On a mismatch, toast a reload action that clears caches first — solves the
// frontend application-cache problem on updates. Runs once per page.
import type { HomeAssistant } from "./ha-types.ts";
import { t } from "./localize.ts";

export const CARD_VERSION = "0.57.0";
let checked = false;

function clearAndReload(): void {
  const reload = () => location.reload();
  if ("caches" in window) {
    caches
      .keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(reload, reload);
  } else {
    reload();
  }
}

export async function checkCardVersion(
  el: HTMLElement,
  hass: HomeAssistant,
): Promise<void> {
  if (checked || !hass?.connection) return;
  checked = true;
  try {
    const res = await hass.connection.sendMessagePromise<{ version: string }>({
      type: "poise/card_version",
    });
    if (res?.version && res.version !== CARD_VERSION) {
      const lang = hass.locale?.language;
      el.dispatchEvent(
        new CustomEvent("hass-notification", {
          detail: {
            message: `${t(lang, "update_msg")} (${CARD_VERSION} → ${res.version})`,
            duration: -1,
            dismissable: true,
            action: { text: t(lang, "reload"), action: clearAndReload },
          },
          bubbles: true,
          composed: true,
        }),
      );
    }
  } catch {
    /* version endpoint missing / older backend — ignore */
  }
}
