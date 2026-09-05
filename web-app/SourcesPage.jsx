import { Fragment, useEffect, useMemo, useState } from "react";
import { fetchSources } from "./apiClient.js";

// Tags qui reviennent dans la plupart des sources ("courants") vs mentions propres à une seule
// source ("spécifiques"). `startsWith` couvre les variantes qualifiées (ex. "identifiant Wikidata
// (QID)", "chaîne de classification (genre → embranchement)") : la nuance entre parenthèses est
// perdue, mais la source doit rester taguée comme fournissant bien cet élément. Chaque tag courant
// a sa propre couleur (voir index.css, palette inspirée de Wikimedia Codex) pour rester scannable
// même avec plusieurs tags par ligne.
const FREQUENT_ELEMENTS = [
  { label: "Auteur", css: "chip-auteur", test: (s) => s.toLowerCase() === "auteur" },
  { label: "Rang", css: "chip-rang", test: (s) => s.toLowerCase() === "rang" },
  { label: "Règne", css: "chip-regne", test: (s) => s.toLowerCase() === "règne" },
  { label: "Chaîne de classification", css: "chip-classif", test: (s) => s.toLowerCase().startsWith("chaîne de classification") },
  { label: "Noms vernaculaires", css: "chip-vernac", test: (s) => s.toLowerCase().startsWith("noms vernaculaires") },
  { label: "Synonymes", css: "chip-syno", test: (s) => s.toLowerCase() === "synonymes" },
  { label: "Sous-taxons", css: "chip-sst", test: (s) => s.toLowerCase() === "sous-taxons" },
  { label: "Basionyme", css: "chip-basio", test: (s) => s.toLowerCase() === "basionyme" },
  { label: "Éteint", css: "chip-eteint", test: (s) => s.toLowerCase() === "éteint" },
  { label: "Identifiant", css: "chip-ident", test: (s) => s.toLowerCase().startsWith("identifiant") },
];

// Regroupement de "Méthode d'accès" pour le rendre triable — suit acces.type, une énumération
// propre côté backend (voir organon/core/db_inventory.py). Le détail brut ("API REST/JSON
// (checklistbank.org, dataset 3LXR...)") devient redondant une fois ce marqueur affiché ; il
// reste consultable en infobulle au survol plutôt que de réencombrer la cellule.
const ACCESS_GROUPS = [
  { label: "API REST", test: (s) => s.acces.type === "api_rest" },
  { label: "SOAP", test: (s) => s.acces.type === "soap" },
  { label: "Scraping HTML", test: (s) => s.acces.type === "scraping" },
  { label: "Vérification HTTP", test: (s) => s.acces.type === "verification_http" },
  { label: "Export de données", test: (s) => s.acces.type === "export" },
  { label: "Contact requis", test: (s) => s.acces.type === "contact_requis" },
];

function accessGroupLabel(source) {
  return (ACCESS_GROUPS.find((g) => g.test(source)) ?? { label: "Autre" }).label;
}

// Le module "Liens transversaux Wikimédia" (id `externe` dans db_inventory.yaml) est une entrée
// unique côté backend, mais couvre plusieurs sites indépendants (Wikidata, Commons, Wikispecies,
// Wiktionnaire...) — on l'éclate ici en une ligne par site, réunies dans leur propre groupe
// "Wikimédia" plutôt que noyées dans "Données généralistes". Repérée par id, pas par un texte
// contenant "wikidata"/"commons"/etc. : une autre source peut légitimement mentionner ces mots
// (ex. "résolution DOI en repli après une recherche Wikidata infructueuse" pour crossref) sans
// être elle-même un agrégateur Wikimédia à éclater.
const WIKI_AGGREGATOR_ID = "externe";
const WIKI_PROPERTIES = [
  { test: /wikidata/i, nom: "Wikidata", url: "https://www.wikidata.org" },
  { test: /commons/i, nom: "Wikimedia Commons", url: "https://commons.wikimedia.org" },
  { test: /wikispecies/i, nom: "Wikispecies", url: "https://species.wikimedia.org" },
  { test: /wiktionnaire/i, nom: "Wiktionnaire (français)", url: "https://fr.wiktionary.org" },
  { test: /wikip[ée]dia/i, nom: "Wikipédia", url: "https://www.wikipedia.org" },
];

function isWikimediaAggregator(source) {
  return source.id === WIKI_AGGREGATOR_ID;
}

function splitWikimediaSource(source) {
  return source.elements_recoltes
    .map((raw, i) => {
      const prop = WIKI_PROPERTIES.find((p) => p.test.test(raw));
      if (!prop) return null;
      return { ...source, id: `${source.id}-${i}`, nom: prop.nom, url: prop.url, elements_recoltes: [raw] };
    })
    .filter(Boolean);
}

function splitElements(list) {
  const courants = [];
  const specifiques = [];
  for (const raw of list) {
    const hit = FREQUENT_ELEMENTS.find((f) => f.test(raw));
    if (hit) {
      if (!courants.includes(hit)) courants.push(hit);
    } else {
      specifiques.push(raw);
    }
  }
  return { courants, specifiques };
}

const STATUT_LABELS = {
  en_attente: "module prêt, en attente de configuration (clé/compte)",
  non_sonde: "non sondée / à revérifier",
  bloque_temporaire: "bloquée temporairement",
  bloque: "bloquée",
  contact_requis: "accès sur inscription ou contact",
  mort: "service arrêté ou injoignable",
  ecarte: "écartée par le projet",
  retire: "intégrée puis retirée",
  hors_perimetre: "hors périmètre",
};

function formatDateFr(iso) {
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
}

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

function sortComparator(key, dir) {
  return (a, b) => {
    const av = key === "nb_courants" ? a[key] : String(a[key]).toLowerCase();
    const bv = key === "nb_courants" ? b[key] : String(b[key]).toLowerCase();
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return a.nom.localeCompare(b.nom);
  };
}

function SortableHeader({ label, sortKey, sort, onSort }) {
  const active = sort.key === sortKey;
  return (
    <th className="sortable" aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort(sortKey)} className={active ? "sort-active" : ""}>
        {label} <span className="sort-arrow">{active ? (sort.dir === 1 ? "▲" : "▼") : ""}</span>
      </button>
    </th>
  );
}

export default function SourcesPage({ onBack }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [sort, setSort] = useState({ key: "nom", dir: 1 });
  const [collapsed, setCollapsed] = useState({});

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

  const grouped = useMemo(() => {
    if (!data) return null;

    const wikimediaSources = [];
    const categories = data.categories
      .map((category) => ({
        nom: category.nom,
        sources: category.sources.filter((s) => {
          if (s.statut !== "disponible") return false;
          if (isWikimediaAggregator(s)) {
            wikimediaSources.push(...splitWikimediaSource(s));
            return false;
          }
          return true;
        }),
      }))
      .filter((category) => category.sources.length > 0);
    if (wikimediaSources.length) categories.push({ nom: "Wikimédia", sources: wikimediaSources });

    return categories.map((category) => ({
      nom: category.nom,
      sources: category.sources.map((s) => {
        const { courants, specifiques } = splitElements(s.elements_recoltes);
        return {
          ...s,
          categorie: category.nom,
          courants,
          specifiques,
          nb_courants: courants.length,
          acces_group: accessGroupLabel(s),
        };
      }),
    }));
  }, [data]);

  const nonDisponibles = useMemo(() => {
    if (!data) return [];
    return data.categories.flatMap((category) => category.sources).filter((s) => s.statut !== "disponible");
  }, [data]);

  // "retire" = intégrée un temps puis débranchée volontairement (voir la sémantique du statut
  // dans db_inventory.yaml) : jamais "considérée" au même titre que le reste des indisponibles
  // (jamais évaluée, écartée...), donc comptée et listée à part.
  const archivees = useMemo(
    () => nonDisponibles.filter((s) => s.statut === "retire").sort((a, b) => a.nom.localeCompare(b.nom, "fr")),
    [nonDisponibles]
  );
  const considerees = useMemo(
    () => nonDisponibles.filter((s) => s.statut !== "retire").sort((a, b) => a.nom.localeCompare(b.nom, "fr")),
    [nonDisponibles]
  );

  if (error) {
    return (
      <SourcesHeader onBack={onBack}>
        <p className="panel-empty">Impossible de charger la liste des sources ({error}).</p>
      </SourcesHeader>
    );
  }

  if (!data || !grouped) {
    return (
      <SourcesHeader onBack={onBack}>
        <p className="panel-loading">Chargement des sources…</p>
      </SourcesHeader>
    );
  }

  // Nombre d'entrées yaml "disponible" avant l'éclatement Wikimédia (voir `grouped` ci-dessus) —
  // sinon le titre grimperait de +3 dès qu'un module d'agrégation liens externes est affiché en
  // plusieurs lignes, sans rapport avec le nombre réel de sources distinctes. Même calcul que le
  // badge de l'en-tête (App.jsx), pour que les deux nombres restent toujours identiques.
  const totalDisponibles = data.categories.reduce(
    (n, c) => n + c.sources.filter((s) => s.statut === "disponible").length,
    0
  );
  const cmp = sortComparator(sort.key, sort.dir);

  function handleSort(key) {
    setSort((prev) => ({
      key,
      dir: prev.key === key ? -prev.dir : key === "nb_courants" ? -1 : 1,
    }));
  }

  function toggleGroup(categorie) {
    setCollapsed((prev) => ({ ...prev, [categorie]: !prev[categorie] }));
  }

  return (
    <SourcesHeader onBack={onBack}>
      <h1>{totalDisponibles} sources disponibles</h1>
      <p className="sources-updated">Liste mise à jour le {formatDateFr(data.derniere_maj)}</p>

      <section className="sources-section">
        <h2>Disponibles</h2>
        <p className="section-sub">
          Sources regroupées par domaine biologique. Colonnes triables et lignes repliables par groupe.
        </p>

        <div className="color-legend">
          <span className="color-legend-title">Éléments courants — code couleur</span>
          {FREQUENT_ELEMENTS.map((f) => (
            <span key={f.label} className={`chip ${f.css}`}>
              {f.label}
            </span>
          ))}
        </div>

        <div className="table-scroll">
          <table className="sources-table">
            <thead>
              <tr>
                <SortableHeader label="Source" sortKey="nom" sort={sort} onSort={handleSort} />
                <SortableHeader label="Classification" sortKey="classif" sort={sort} onSort={handleSort} />
                <SortableHeader label="Éléments courants" sortKey="nb_courants" sort={sort} onSort={handleSort} />
                <th>Éléments spécifiques</th>
                <SortableHeader label="Méthode d'accès" sortKey="acces_group" sort={sort} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {grouped.map((category) => {
                const isCollapsed = !!collapsed[category.nom];
                const rows = [...category.sources]
                  .map((s) => ({ ...s, classif: s.classification.possible ? (s.classification.estime ? "oui (estimé)" : "oui") : "non" }))
                  .sort(cmp);
                return (
                  <Fragment key={category.nom}>
                    <tr
                      className={`group-head${isCollapsed ? " collapsed" : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-expanded={!isCollapsed}
                      onClick={() => toggleGroup(category.nom)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleGroup(category.nom);
                        }
                      }}
                    >
                      <td colSpan={5}>
                        <span className="group-toggle">
                          <span className="group-chev">▾</span>
                          {category.nom}
                        </span>
                        <span className="group-count">
                          {" "}
                          — {rows.length} source{rows.length > 1 ? "s" : ""}
                        </span>
                      </td>
                    </tr>
                    {!isCollapsed &&
                      rows.map((source) => (
                        <tr key={source.id}>
                          <td>
                            <SourceName source={source} />
                          </td>
                          <td>
                            <ClassificationCell classification={source.classification} />
                          </td>
                          <td>
                            {source.courants.length ? (
                              <div className="chip-row">
                                {source.courants.map((c) => (
                                  <span key={c.label} className={`chip ${c.css}`}>
                                    {c.label}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="none-cell">—</span>
                            )}
                          </td>
                          <td>
                            {source.specifiques.length ? (
                              source.specifiques.map((sp) => (
                                <span key={sp} className="specifique-text">
                                  {sp}
                                </span>
                              ))
                            ) : (
                              <span className="none-cell">—</span>
                            )}
                          </td>
                          <td>
                            <span className="access-chip" title={source.acces.detail}>
                              {source.acces_group}
                            </span>
                          </td>
                        </tr>
                      ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="sources-section">
        <h2>Non disponibles</h2>
        <div className="considered-list">
          <p>
            {considerees.length} source{considerees.length > 1 ? "s" : ""} considérée{considerees.length > 1 ? "s" : ""} :{" "}
            {considerees.map((s, i) => (
              <span key={s.id}>
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" title={STATUT_LABELS[s.statut] || s.statut}>
                    {s.nom}
                  </a>
                ) : (
                  <span title={STATUT_LABELS[s.statut] || s.statut}>{s.nom}</span>
                )}
                {i < considerees.length - 1 && <span className="sep">, </span>}
              </span>
            ))}
          </p>
          {archivees.length > 0 && (
            <p className="sources-archived">
              {archivees.length} source{archivees.length > 1 ? "s" : ""} archivée
              {archivees.length > 1 ? "s" : ""} : {archivees.map((s) => s.nom).join(", ")}
            </p>
          )}
        </div>
      </section>
    </SourcesHeader>
  );
}
