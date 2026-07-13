import { useEffect, useState } from "react";
import { fetchSources } from "./apiClient.js";

// Ordre d'affichage des sous-sections "non disponible" : des cas les plus susceptibles
// d'évoluer prochainement (à revérifier, blocage temporaire) vers les plus définitifs (mort,
// écarté, hors périmètre) — un lecteur qui cherche "qu'est-ce qui pourrait bientôt marcher ?"
// n'a pas à parcourir toute la liste.
const STATUT_ORDER = [
  "non_sonde",
  "bloque_temporaire",
  "bloque",
  "contact_requis",
  "mort",
  "ecarte",
  "retire",
  "hors_perimetre",
];

const STATUT_LABELS = {
  non_sonde: "Non sondée / à revérifier",
  bloque_temporaire: "Bloquée temporairement",
  bloque: "Bloquée",
  contact_requis: "Accès sur inscription ou contact",
  mort: "Service arrêté ou injoignable",
  ecarte: "Écartée par le projet",
  retire: "Intégrée puis retirée",
  hors_perimetre: "Hors périmètre",
};

const STATUT_BADGE_CLASS = {
  non_sonde: "source-badge-neutral",
  bloque_temporaire: "source-badge-warn",
  bloque: "source-badge-warn",
  contact_requis: "source-badge-warn",
  mort: "source-badge-danger",
  ecarte: "source-badge-neutral",
  retire: "source-badge-neutral",
  hors_perimetre: "source-badge-neutral",
};

function SourceName({ source }) {
  const label = source.is_default ? `${source.nom} (défaut)` : source.nom;
  if (!source.url) return <span>{label}</span>;
  return (
    <a href={source.url} target="_blank" rel="noopener noreferrer">
      {label}
    </a>
  );
}

function ClassificationCell({ classification }) {
  if (!classification.possible) {
    return <span className="source-muted">non</span>;
  }
  return (
    <span>
      oui
      {classification.estime && <span className="source-badge source-badge-warn">estimé</span>}
    </span>
  );
}

function SourcesHeader({ onBack, children }) {
  return (
    <div className="sources-page">
      <button type="button" className="back-link" onClick={onBack}>
        ‹ Retour
      </button>
      <span className="eyebrow">Sources de données</span>
      {children}
    </div>
  );
}

export default function SourcesPage({ onBack }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchSources()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <SourcesHeader onBack={onBack}>
        <p className="panel-empty">Impossible de charger la liste des sources ({error}).</p>
      </SourcesHeader>
    );
  }

  if (!data) {
    return (
      <SourcesHeader onBack={onBack}>
        <p className="panel-loading">Chargement des sources…</p>
      </SourcesHeader>
    );
  }

  // Le backend groupe déjà par catégorie biologique (voir organon/core/data/db_inventory.yaml) ;
  // la page regroupe plutôt par statut, l'axe qui intéresse le lecteur ici (qu'est-ce qui
  // marche vs pourquoi le reste ne marche pas), la catégorie devenant une simple colonne.
  const sources = data.categories.flatMap((category) =>
    category.sources.map((source) => ({ ...source, categorie: category.nom }))
  );
  const disponibles = sources.filter((s) => s.statut === "disponible");
  const indisponibles = sources.filter((s) => s.statut !== "disponible");

  return (
    <SourcesHeader onBack={onBack}>
      <h1>
        {disponibles.length} source{disponibles.length > 1 ? "s" : ""} disponible
        {disponibles.length > 1 ? "s" : ""} sur {sources.length} bases considérées
      </h1>
      <p className="sources-updated">Liste mise à jour le {data.derniere_maj}</p>

      <section className="sources-section">
        <h2>Disponibles ({disponibles.length})</h2>
        <table className="sources-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Domaine biologique</th>
              <th>Classification</th>
              <th>Éléments récoltés</th>
              <th>Méthode d'accès</th>
            </tr>
          </thead>
          <tbody>
            {disponibles.map((source) => (
              <tr key={source.id}>
                <td>
                  <SourceName source={source} />
                </td>
                <td>{source.categorie}</td>
                <td>
                  <ClassificationCell classification={source.classification} />
                </td>
                <td>{source.elements_recoltes.length ? source.elements_recoltes.join(", ") : "—"}</td>
                <td>{source.acces.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="sources-section">
        <h2>Non disponibles ({indisponibles.length})</h2>
        {STATUT_ORDER.map((statut) => {
          const rows = indisponibles.filter((s) => s.statut === statut);
          if (!rows.length) return null;
          return (
            <div className="sources-subsection" key={statut}>
              <h3>
                <span className={`source-badge ${STATUT_BADGE_CLASS[statut]}`}>{STATUT_LABELS[statut]}</span>
                <span className="sources-subsection-count">{rows.length}</span>
              </h3>
              <table className="sources-table sources-table-compact">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Domaine biologique</th>
                    <th>Classification</th>
                    <th>Motif</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((source) => (
                    <tr key={source.id}>
                      <td>
                        <SourceName source={source} />
                      </td>
                      <td>{source.categorie}</td>
                      <td>
                        <ClassificationCell classification={source.classification} />
                      </td>
                      <td>
                        {source.acces.detail}
                        {source.notes ? <span className="source-notes"> — {source.notes}</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </section>
    </SourcesHeader>
  );
}
