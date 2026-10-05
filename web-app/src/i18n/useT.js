import { useContext } from "react";

import { I18nContext } from "./context.js";

function useI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useT/useLocale must be used inside <I18nProvider>.");
  return value;
}

// t("feature.key", { name }); with { count }, the `_one`/`_other`
// variant of the key is chosen.
export function useT() {
  return useI18n().t;
}

export function useLocale() {
  const { locale, enabledLocales, setLocale, formatNumber } = useI18n();
  return { locale, enabledLocales, setLocale, formatNumber };
}
