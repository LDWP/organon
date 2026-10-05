// Probe rendered by the dev-server-only harness page (not part of the build).
import LanguageSelector from "@/i18n/LanguageSelector.jsx";
import { useLocale, useT } from "@/i18n/useT.js";

export default function Probe() {
  const t = useT();
  const { formatNumber } = useLocale();
  return (
    <>
      <LanguageSelector />
      <p data-testid="one">{t("sources.available", { count: 1 })}</p>
      <p data-testid="many">{t("sources.available", { count: 1234 })}</p>
      <p data-testid="missing">{t("language.notInEnglishOrFrench")}</p>
      <p data-testid="number">{formatNumber(1234567.5)}</p>
    </>
  );
}

