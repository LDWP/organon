// Stockage du consentement RGPD pour le stockage local du navigateur (thème jour/nuit,
// futures fonctions de recherche). Aucune donnée n'est envoyée au serveur, mais l'usage du
// localStorage reste soumis au consentement (ePrivacy/RGPD), révocable et expirant après 365
// jours (au-delà, le choix redevient explicite plutôt que reconduit tacitement).
//
// Nom de fichier neutre, sans "cookie"/"consent" : certains bloqueurs de publicité filtrent au
// niveau réseau les requêtes dont l'URL évoque un bandeau de consentement tiers, alors qu'il n'y
// a ici aucun usage commercial ou analytique — juste du stockage local.
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
    /* stockage indisponible (navigation privée, etc.) — le bandeau réapparaîtra à chaque visite */
  }
}
