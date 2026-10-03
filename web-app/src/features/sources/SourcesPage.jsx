import { Fragment, useEffect, useMemo, useState } from "react";
import { fetchSources } from "@/api/client.js";

// Tags recurring in most sources ("common") vs mentions specific to one
// source ("specific"). `startsWith` covers qualified variants (e.g.
// "identifiant Wikidata (QID)"): the parenthesized nuance is lost, but
// the source must stay tagged as providing that item. Each common tag
// has its own color (see index.css, palette inspired by Wikimedia
// Codex) to stay scannable with several tags per row.
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
  { label: "Autres projets", css: "chip-projets", test: (s) => s.toLowerCase() === "autres projets" },
];

// Grouping of "Méthode d'accès" to make it sortable; follows
// access.type, a backend enumeration (see
// organon/core/db_inventory.py). The raw detail ("API REST/JSON
// (checklistbank.org, dataset 3LXR...)") is redundant once this marker
// is shown; it stays in a hover tooltip rather than clutter the cell
// again.
const ACCESS_GROUPS = [
  { label: "API REST", test: (s) => s.access.type === "api_rest" },
  { label: "SOAP", test: (s) => s.access.type === "soap" },
  { label: "Scraping HTML", test: (s) => s.access.type === "scraping" },
  { label: "Vérification HTTP", test: (s) => s.access.type === "verification_http" },
  { label: "Export de données", test: (s) => s.access.type === "export" },
  { label: "Contact requis", test: (s) => s.access.type === "contact_requis" },
];

function accessGroupLabel(source) {
  return (ACCESS_GROUPS.find((g) => g.test(source)) ?? { label: "Autre" }).label;
}

// A source may cover several distinct sites or usages under one module
// (same id, status and access): e.g. the `externe` module covers
// Wikidata, Commons, Wikispecies, Wiktionary and fr.wikipedia.org. The
// per-site detail then comes from `source.facets` (db_inventory.yaml),
// not from a deduction on the text of `harvested_items`: one row per
// facet, with its own name and url and the rest inherited from the
// parent source.
function expandParts(source) {
  if (!source.facets?.length) return [source];
  return source.facets.map((part, i) => ({
    ...source,
    id: `${source.id}-${i}`,
    name: part.name,
    url: part.url,
    harvested_items: part.harvested_items,
  }));
}

function splitElements(list) {
  const common = [];
  const specific = [];
  for (const raw of list) {
    const hit = FREQUENT_ELEMENTS.find((f) => f.test(raw));
    if (hit) {
      if (!common.includes(hit)) common.push(hit);
    } else {
      specific.push(raw);
    }
  }
  return { common, specific };
}

const STATUS_LABELS = {
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
  const label = source.is_default ? `${source.name} (défaut)` : source.name;
  if (!source.url) return <span>{label}</span>;
  return (
    <a href={source.url} target="_blank" rel="noopener noreferrer">
      {label}
    </a>
  );
}

function ClassificationCell({ classification }) {
  if (!classification.can_classify) {
    return <span className="source-muted">non</span>;
  }
  return (
    <span>
      oui
      {classification.estimated && <span className="source-badge source-badge-warn">estimé</span>}
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
    const av = key === "commonCount" ? a[key] : String(a[key]).toLowerCase();
    const bv = key === "commonCount" ? b[key] : String(b[key]).toLowerCase();
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return a.name.localeCompare(b.name);
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
  const [sort, setSort] = useState({ key: "name", dir: 1 });
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

    const categories = data.categories
      .map((category) => ({
        name: category.name,
        sources: category.sources.filter((s) => s.status === "disponible").flatMap(expandParts),
      }))
      .filter((category) => category.sources.length > 0);

    return categories.map((category) => ({
      name: category.name,
      sources: category.sources.map((s) => {
        const { common, specific } = splitElements(s.harvested_items);
        return {
          ...s,
          category: category.name,
          common,
          specific,
          commonCount: common.length,
          accessGroup: accessGroupLabel(s),
        };
      }),
    }));
  }, [data]);

  const unavailable = useMemo(() => {
    if (!data) return [];
    return data.categories.flatMap((category) => category.sources).filter((s) => s.status !== "disponible");
  }, [data]);

  // "retire" = integrated for a while then deliberately unplugged (see
  // the status semantics in db_inventory.yaml): never "considered" like
  // the other unavailable ones (never evaluated, discarded...), so
  // counted and listed apart.
  const archived = useMemo(
    () => unavailable.filter((s) => s.status === "retire").sort((a, b) => a.name.localeCompare(b.name, "fr")),
    [unavailable]
  );
  const considered = useMemo(
    () => unavailable.filter((s) => s.status !== "retire").sort((a, b) => a.name.localeCompare(b.name, "fr")),
    [unavailable]
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

  // Number of "disponible" yaml entries before the split into facets
  // (see `grouped` above); otherwise the title would grow as soon as a
  // multi-facet source (e.g. `externe`) shows on several rows,
  // unrelated to the real number of distinct modules. Same count as the
  // header badge (App.jsx), so both numbers always match.
  const totalAvailable = data.categories.reduce(
    (n, c) => n + c.sources.filter((s) => s.status === "disponible").length,
    0
  );
  const cmp = sortComparator(sort.key, sort.dir);

  function handleSort(key) {
    setSort((prev) => ({
      key,
      dir: prev.key === key ? -prev.dir : key === "commonCount" ? -1 : 1,
    }));
  }

  function toggleGroup(category) {
    setCollapsed((prev) => ({ ...prev, [category]: !prev[category] }));
  }

  return (
    <SourcesHeader onBack={onBack}>
      <h1>{totalAvailable} sources disponibles</h1>
      <p className="sources-updated">Liste mise à jour le {formatDateFr(data.last_updated)}</p>

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
                <SortableHeader label="Source" sortKey="name" sort={sort} onSort={handleSort} />
                <SortableHeader label="Classification" sortKey="classif" sort={sort} onSort={handleSort} />
                <SortableHeader label="Éléments courants" sortKey="commonCount" sort={sort} onSort={handleSort} />
                <th>Éléments spécifiques</th>
                <SortableHeader label="Méthode d'accès" sortKey="accessGroup" sort={sort} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {grouped.map((category) => {
                const isCollapsed = !!collapsed[category.name];
                const rows = [...category.sources]
                  .map((s) => ({ ...s, classif: s.classification.can_classify ? (s.classification.estimated ? "oui (estimé)" : "oui") : "non" }))
                  .sort(cmp);
                return (
                  <Fragment key={category.name}>
                    <tr
                      className={`group-head${isCollapsed ? " collapsed" : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-expanded={!isCollapsed}
                      onClick={() => toggleGroup(category.name)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleGroup(category.name);
                        }
                      }}
                    >
                      <td colSpan={5}>
                        <span className="group-toggle">
                          <span className="group-chev">▾</span>
                          {category.name}
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
                            {source.common.length ? (
                              <div className="chip-row">
                                {source.common.map((c) => (
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
                            {source.specific.length ? (
                              source.specific.map((sp) => (
                                <span key={sp} className="specifique-text">
                                  {sp}
                                </span>
                              ))
                            ) : (
                              <span className="none-cell">—</span>
                            )}
                          </td>
                          <td>
                            <span className="access-chip" title={source.access.detail}>
                              {source.accessGroup}
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
            {considered.length} source{considered.length > 1 ? "s" : ""} considérée{considered.length > 1 ? "s" : ""} :{" "}
            {considered.map((s, i) => (
              <span key={s.id}>
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" title={STATUS_LABELS[s.status] || s.status}>
                    {s.name}
                  </a>
                ) : (
                  <span title={STATUS_LABELS[s.status] || s.status}>{s.name}</span>
                )}
                {i < considered.length - 1 && <span className="sep">, </span>}
              </span>
            ))}
          </p>
          {archived.length > 0 && (
            <p className="sources-archived">
              {archived.length} source{archived.length > 1 ? "s" : ""} archivée
              {archived.length > 1 ? "s" : ""} : {archived.map((s) => s.name).join(", ")}
            </p>
          )}
        </div>
      </section>
    </SourcesHeader>
  );
}
