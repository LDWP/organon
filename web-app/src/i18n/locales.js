import { flatten } from "./core.js";

// Locale catalogue. Adding a language = adding ./locales/<wiki code>.json
// (same keys as `fr`), naming it in LOCALE_NAMES and listing the code in
// ENABLED_LOCALES once it is complete.
export const DEFAULT_LOCALE = "fr";

// Locales offered to users (selector, cookie, browser detection). `en`
// exists but stays hidden while the interface is being migrated: add it
// here in the final migration step.
export const ENABLED_LOCALES = ["fr"];

// The default language is in the main bundle (no flash); the others are
// separate chunks loaded on demand.
const defaultFile = import.meta.glob("./locales/fr.json", { eager: true, import: "default" });
const lazyFiles = import.meta.glob(["./locales/*.json", "!./locales/fr.json"], { import: "default" });

// Each language's own name (not in its file: that one is loaded lazily).
export const LOCALE_NAMES = { fr: "Français", en: "English" };

export const DEFAULT_MESSAGES = flatten(defaultFile["./locales/fr.json"]);

export async function loadMessages(locale) {
  if (locale === DEFAULT_LOCALE) return DEFAULT_MESSAGES;
  const load = lazyFiles[`./locales/${locale}.json`];
  return load ? flatten(await load()) : DEFAULT_MESSAGES;
}
