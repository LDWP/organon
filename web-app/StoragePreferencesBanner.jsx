// Icônes façon Iconoir "cookie"/"half-cookie" (pleine = stockage local accepté, mi-pleine =
// refusé), redessinées en SVG inline (même style trait que les icônes de App.jsx) plutôt que
// dépendre du paquet Iconoir pour deux icônes.
//
// Fichier nommé "StoragePreferences" plutôt que "CookieConsent" volontairement : voir
// storagePreferences.js pour la raison (neutralité vis-à-vis des bloqueurs de publicité).
function AcceptedIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2c0 1.5 1.2 2.8 2.8 2.8S17.5 5 19 5c0 3.9 3.1 7 7 7 0 5.5-4.5 10-10 10S2 17.5 2 12 6.5 2 12 2z" transform="translate(1 1) scale(0.85)" />
      <circle cx="9" cy="10" r="1" fill="currentColor" stroke="none" />
      <circle cx="14" cy="14" r="1" fill="currentColor" stroke="none" />
      <circle cx="10" cy="16" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

function PartialIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9.5" />
      <path d="M12 2.5a9.5 9.5 0 0 1 0 19z" fill="currentColor" stroke="none" opacity="0.35" />
      <circle cx="14" cy="9" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="14" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function PreferencesToggleButton({ consent, onClick }) {
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={onClick}
      aria-label="Préférences de stockage local"
      title="Préférences de stockage local"
    >
      {consent === "accepted" ? <AcceptedIcon /> : <PartialIcon />}
    </button>
  );
}

export function PreferencesBanner({ onAccept, onRefuse }) {
  return (
    <div className="storage-banner" role="dialog" aria-label="Préférences de stockage local">
      <p>
        Ce site peut mémoriser vos préférences (thème jour/nuit, et de futures fonctions de
        recherche) dans le stockage local de votre navigateur, pour 90 jours maximum. Aucune
        donnée n'est envoyée à un tiers ni à Organon.
      </p>
      <div className="storage-actions">
        <button type="button" className="run" onClick={onAccept}>
          Accepter
        </button>
        <button type="button" className="edit-btn" onClick={onRefuse}>
          Refuser
        </button>
      </div>
    </div>
  );
}
