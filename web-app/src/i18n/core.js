// Pure i18n logic (no React, no Vite): importable by node:test.

const pluralRulesCache = new Map();

function pluralCategory(locale, count) {
  if (!pluralRulesCache.has(locale)) pluralRulesCache.set(locale, new Intl.PluralRules(locale));
  return pluralRulesCache.get(locale).select(count);
}

// { review: { retry: "x" } } -> { "review.retry": "x" }; `_`-prefixed
// top-level keys are metadata, not messages.
export function flatten(tree, prefix = "") {
  const messages = {};
  for (const [key, value] of Object.entries(tree)) {
    if (!prefix && key.startsWith("_")) continue;
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "object" && value !== null) Object.assign(messages, flatten(value, path));
    else messages[path] = value;
  }
  return messages;
}

export function interpolate(template, vars = {}) {
  return template.replace(/\{(\w+)\}/g, (placeholder, name) =>
    Object.hasOwn(vars, name) ? String(vars[name]) : placeholder,
  );
}

// `count` selects the `<key>_<category>` variant (CLDR category of the
// locale), falling back on `<key>_other`, then on the bare key.
function lookup(messages, locale, key, count) {
  if (typeof count === "number") {
    const plural = messages[`${key}_${pluralCategory(locale, count)}`] ?? messages[`${key}_other`];
    if (plural !== undefined) return plural;
  }
  return messages[key];
}

// A key missing from `messages` falls back on the default language,
// formatted with that language's plural rules; missing from both, the
// key itself is returned so the gap stays visible.
export function createTranslator({
  locale,
  messages,
  fallbackLocale,
  fallbackMessages,
  formatNumber = String,
}) {
  return function t(key, vars) {
    const count = vars?.count;
    // `count` is displayed in the locale's number format ("1 234" / "1,234").
    const shown = typeof count === "number" ? { ...vars, count: formatNumber(count) } : vars;
    const own = lookup(messages, locale, key, count);
    if (own !== undefined) return interpolate(own, shown);
    const fallback = lookup(fallbackMessages, fallbackLocale, key, count);
    return fallback !== undefined ? interpolate(fallback, shown) : key;
  };
}

// Order: stored choice > browser languages > fallback. Only `enabled`
// locales can be chosen.
export function detectLocale({ stored, languages = [], enabled, fallback }) {
  if (stored && enabled.includes(stored)) return stored;
  for (const language of languages) {
    const base = String(language).toLowerCase().split("-")[0];
    if (enabled.includes(base)) return base;
  }
  return fallback;
}
