// Storage of the GDPR consent for the browser local storage (day/night
// theme, future search features). No data is sent to the server, but
// local storage use remains subject to consent (ePrivacy, GDPR),
// revocable and expiring after 365 days (beyond that the choice becomes
// explicit again rather than tacitly renewed).
//
// Neutral file name, without "cookie" or "consent": some ad blockers
// filter at the network level requests whose URL evokes a third-party
// consent banner, although there is no commercial or analytics use
// here, only local storage.
const STORAGE_KEY = "organon-storage-preferences";
const MAX_AGE_MS = 365 * 24 * 60 * 60 * 1000;

export function getStorageConsent() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const { status, ts } = JSON.parse(raw);
    if (typeof ts !== "number" || Date.now() - ts > MAX_AGE_MS) return null;
    return status === "accepted" || status === "refused" ? status : null;
  } catch {
    return null;
  }
}

export function setStorageConsent(status) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ status, ts: Date.now() }));
  } catch {
    /* storage unavailable (private browsing...): the banner reappears at each visit */
  }
}

const THEME_KEY = "organon-theme";

// Reading and writing the theme depend on consent: without "accepted",
// nothing is read from or written to localStorage.
export function readStoredTheme() {
  if (getStorageConsent() !== "accepted") return null;
  try {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === "dark" || saved === "light" ? saved : null;
  } catch {
    return null;
  }
}

export function writeStoredTheme(theme) {
  if (getStorageConsent() !== "accepted") return;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* harmless if the preference cannot be saved */
  }
}

export function clearStoredTheme() {
  try {
    localStorage.removeItem(THEME_KEY);
  } catch {
    /* nothing to do if storage is already unavailable */
  }
}

// Interface language: a functional preference cookie (SameSite=Lax,
// 1 year, no personal data), exempt from the consent above. It is sent
// along with same-origin requests, which is harmless.
const LOCALE_COOKIE = "organon-locale";
const LOCALE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60;
const LOCALE_PATTERN = /^[a-z]{2,3}$/;

export function parseLocaleCookie(cookieHeader) {
  for (const part of String(cookieHeader ?? "").split(";")) {
    const [name, value] = part.trim().split("=");
    if (name === LOCALE_COOKIE && LOCALE_PATTERN.test(value ?? "")) return value;
  }
  return null;
}

export function buildLocaleCookie(locale, secure) {
  return `${LOCALE_COOKIE}=${locale}; Max-Age=${LOCALE_COOKIE_MAX_AGE}; Path=/; SameSite=Lax${secure ? "; Secure" : ""}`;
}

export function readStoredLocale() {
  try {
    return parseLocaleCookie(document.cookie);
  } catch {
    return null;
  }
}

export function writeStoredLocale(locale) {
  if (!LOCALE_PATTERN.test(locale)) return;
  try {
    document.cookie = buildLocaleCookie(locale, location.protocol === "https:");
  } catch {
    /* harmless if the preference cannot be saved */
  }
}
