import { useCallback, useEffect, useMemo, useState } from "react";

import { readStoredLocale, writeStoredLocale } from "@/shell/storagePreferences.js";
import { I18nContext } from "./context.js";
import { createTranslator, detectLocale } from "./core.js";
import { DEFAULT_LOCALE, DEFAULT_MESSAGES, ENABLED_LOCALES, loadMessages } from "./locales.js";

export function I18nProvider({ children, enabledLocales = ENABLED_LOCALES }) {
  const [target, setTarget] = useState(() =>
    detectLocale({
      stored: readStoredLocale(),
      languages: navigator.languages,
      enabled: enabledLocales,
      fallback: DEFAULT_LOCALE,
    }),
  );
  // The displayed language only changes once its messages are loaded;
  // until then the default language stays on screen.
  const [loaded, setLoaded] = useState({ locale: DEFAULT_LOCALE, messages: DEFAULT_MESSAGES });

  useEffect(() => {
    let cancelled = false;
    loadMessages(target)
      .then((messages) => {
        if (!cancelled) setLoaded({ locale: target, messages });
      })
      .catch(() => {
        /* chunk unavailable (network): the default language stays */
      });
    return () => {
      cancelled = true;
    };
  }, [target]);

  useEffect(() => {
    document.documentElement.lang = loaded.locale;
  }, [loaded.locale]);

  const setLocale = useCallback(
    (locale) => {
      if (!enabledLocales.includes(locale)) return;
      writeStoredLocale(locale);
      setTarget(locale);
    },
    [enabledLocales],
  );

  const value = useMemo(() => {
    const numberFormat = new Intl.NumberFormat(loaded.locale);
    const formatNumber = (n) => numberFormat.format(n);
    return {
      locale: loaded.locale,
      enabledLocales,
      setLocale,
      formatNumber,
      t: createTranslator({
        locale: loaded.locale,
        messages: loaded.messages,
        fallbackLocale: DEFAULT_LOCALE,
        fallbackMessages: DEFAULT_MESSAGES,
        formatNumber,
      }),
    };
  }, [loaded, enabledLocales, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
