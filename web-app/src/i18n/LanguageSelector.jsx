import { LOCALE_NAMES } from "./locales.js";
import { useLocale, useT } from "./useT.js";

// Not mounted yet: SiteHeader gets it in the final migration step,
// together with "en" in ENABLED_LOCALES.
export default function LanguageSelector() {
  const t = useT();
  const { locale, enabledLocales, setLocale } = useLocale();
  if (enabledLocales.length < 2) return null;
  return (
    <select
      className="status"
      value={locale}
      onChange={(event) => setLocale(event.target.value)}
      aria-label={t("language.label")}
    >
      {enabledLocales.map((code) => (
        <option key={code} value={code} lang={code}>
          {LOCALE_NAMES[code] ?? code}
        </option>
      ))}
    </select>
  );
}
