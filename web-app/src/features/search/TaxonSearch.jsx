import { Fragment, useEffect, useId, useMemo, useRef, useState } from "react";
import { searchTaxa } from "@/api/client.js";
import { buildDisambiguationTree, flattenDisambiguationTree } from "./disambiguationTree.js";
import { resolveMatches } from "./searchResolution.js";
import { TaxonName } from "./taxonMatches.jsx";

const EXAMPLES = ["Gadus morhua", "Panthera leo", "Quercus robur", "Amanita muscaria"];
const AUTOCOMPLETE_DELAY_MS = 300;

function MatchLabel({ match }) {
  return (
    <>
      {match.extinct && <span aria-label="éteint" title="Éteint">†</span>}
      <TaxonName match={match} />
      {match.author && <span className="disambiguation-author">{match.author}</span>}
      {match.kingdom && <span className="id-badge">{match.kingdom}</span>}
      {match.rank && <span className="id-badge id-badge-rank">{match.rank}</span>}
      {match.vernacular_names.length > 0 && (
        <span className="disambiguation-vernacular">{match.vernacular_names.join(", ")}</span>
      )}
    </>
  );
}

// Group the domains by parent (e.g. the children of "animal") from the
// `parent` field of /api/v1/domains, rather than recode the
// organon/core/domains.py tree in the frontend.
function groupDomains(domains) {
  const children = new Map();
  const top = [];
  for (const d of domains) {
    if (d.id === "*") continue;
    if (d.parent) {
      if (!children.has(d.parent)) children.set(d.parent, []);
      children.get(d.parent).push(d.id);
    } else {
      top.push(d.id);
    }
  }
  top.sort((a, b) => a.localeCompare(b, "fr"));
  for (const list of children.values()) list.sort((a, b) => a.localeCompare(b, "fr"));
  return { top, children };
}

// Single field: scientific name, vernacular name or QID. Autocomplete
// is always on; the candidate list only appears when ambiguous (see
// resolveMatches).
export default function TaxonSearch({
  compact, domains, busy, error, kept, onLaunch, onOpenKept,
  referenceSource, referenceLabel, onReferenceSourceChange, classificationModules,
}) {
  const [text, setText] = useState("");
  const [domain, setDomain] = useState("*");
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [candidates, setCandidates] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const timer = useRef(null);
  const generation = useRef(0);
  // Last /search answer: submission reuses the autocomplete one.
  const lastSearch = useRef({ query: null, matches: [] });
  const listId = useId();
  const optionsId = useId();
  const domainGroups = useMemo(() => groupDomains(domains), [domains]);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function fetchMatches(query) {
    if (lastSearch.current.query === query) return lastSearch.current.matches;
    const matches = (await searchTaxa(query)).matches || [];
    lastSearch.current = { query, matches };
    return matches;
  }

  const visibleSuggestions =
    domain === "*" ? suggestions : suggestions.filter((m) => m.kingdom === domain);

  function cancelSuggestions() {
    clearTimeout(timer.current);
    generation.current += 1;
    setSuggestionsOpen(false);
  }

  function launch(match) {
    cancelSuggestions();
    setCandidates(null);
    setText(match.scientific_name);
    onLaunch({
      name: match.scientific_name,
      domain: match.kingdom || domain,
      gbifKey: match.gbif_key ?? undefined,
      qid: match.qid ?? undefined,
    });
  }

  function handleChange(value) {
    setText(value);
    clearTimeout(timer.current);
    const mine = ++generation.current;
    const query = value.trim();
    if (query.length < 2) {
      setSuggestionsOpen(false);
      return;
    }
    timer.current = setTimeout(async () => {
      let matches = [];
      try {
        matches = await fetchMatches(query);
      } catch {
        /* autocomplete unavailable: the submission will retry */
      }
      // replaced by a more recent input
      if (generation.current !== mine) return;
      setSuggestions(matches);
      setSuggestionsOpen(matches.length > 0);
      setHighlighted(-1);
    }, AUTOCOMPLETE_DELAY_MS);
  }

  async function submit(value) {
    const query = value.trim();
    if (!query) return;
    cancelSuggestions();
    setCandidates(null);
    setResolving(true);
    let matches = [];
    try {
      matches = await fetchMatches(query);
    } catch {
      /* search unavailable: try the direct generation anyway */
    }
    setResolving(false);
    const resolution = resolveMatches(matches, query, domain);
    if (resolution.kind === "ambiguous") setCandidates({ query, matches: resolution.matches });
    else if (resolution.kind === "single") launch(resolution.match);
    else onLaunch({ name: query, domain });
  }

  function handleKeyDown(event) {
    if (!suggestionsOpen || visibleSuggestions.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((i) => Math.min(i + 1, visibleSuggestions.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && highlighted >= 0) {
      event.preventDefault();
      launch(visibleSuggestions[highlighted]);
    } else if (event.key === "Escape") {
      setSuggestionsOpen(false);
    }
  }

  function handleExample(name) {
    setText(name);
    submit(name);
  }

  const working = busy || resolving;
  const input = (
    <input
      type="text"
      value={text}
      onChange={(e) => handleChange(e.target.value)}
      onKeyDown={handleKeyDown}
      onBlur={() => setTimeout(() => setSuggestionsOpen(false), 150)}
      placeholder="nom scientifique, nom vernaculaire ou QID…"
      aria-label="Nom scientifique, nom vernaculaire ou QID Wikidata"
      autoComplete="off"
      spellCheck="false"
      role="combobox"
      aria-expanded={suggestionsOpen}
      aria-controls={listId}
      aria-autocomplete="list"
    />
  );
  const optionsToggle = (
    <span className="search-toggles">
      <button
        type="button"
        className="search-options-toggle"
        aria-expanded={helpOpen}
        aria-controls={`${optionsId}-help`}
        onClick={() => setHelpOpen((v) => !v)}
      >
        <span aria-hidden="true">ⓘ</span> Aide
      </button>
      <button
        type="button"
        className="search-options-toggle"
        aria-expanded={optionsOpen}
        aria-controls={optionsId}
        onClick={() => setOptionsOpen((open) => !open)}
      >
        Options {optionsOpen ? "▴" : "▾"}
      </button>
    </span>
  );
  const helpBubble = helpOpen && (
    <p className="search-info-bubble" id={`${optionsId}-help`} role="note">
      Saisissez un nom scientifique, un nom vernaculaire ou un QID Wikidata. Les suggestions
      s'affichent pendant la saisie ; une liste de candidats n'est proposée que si le nom est
      ambigu (homonymes, nom vernaculaire à plusieurs résultats). Le filtre restreint les
      suggestions et lève les homonymies entre domaines.
    </p>
  );
  const dropdown = suggestionsOpen && visibleSuggestions.length > 0 && (
    <ul className="autocomplete-dropdown" role="listbox" id={listId}>
      {visibleSuggestions.map((m, i) => (
        <li key={`${m.gbif_key ?? m.qid ?? m.scientific_name}-${m.kingdom}-${i}`} role="presentation">
          <button
            type="button"
            role="option"
            aria-selected={i === highlighted}
            className={i === highlighted ? "highlighted" : ""}
            onMouseDown={(e) => {
              e.preventDefault();
              launch(m);
            }}
          >
            <MatchLabel match={m} />
          </button>
        </li>
      ))}
    </ul>
  );
  const options = optionsOpen && (
    <div className="search-options" id={optionsId}>
      <div className="field-box">
        <label className="field-label" htmlFor={`${optionsId}-domain`}>Filtre de domaine</label>
        <select id={`${optionsId}-domain`} value={domain} onChange={(e) => setDomain(e.target.value)}>
          <option value="*">aucun</option>
          {domainGroups.top.map((id) => (
            <Fragment key={id}>
              <option value={id}>{id}</option>
              {(domainGroups.children.get(id) || []).map((childId) => (
                <option key={childId} value={childId}>{"\xa0\xa0\xa0\xa0"}{childId}</option>
              ))}
            </Fragment>
          ))}
        </select>
      </div>
      <div className="field-box">
        <label className="field-label" htmlFor={`${optionsId}-source`}>Source de référence</label>
        <select
          id={`${optionsId}-source`}
          value={referenceSource}
          onChange={(e) => onReferenceSourceChange(e.target.value)}
        >
          <option value="">Auto{referenceLabel ? ` · ${referenceLabel.toUpperCase()}` : ""}</option>
          {classificationModules.map((m) => (
            <option key={m.id} value={m.id}>{m.id.toUpperCase()}</option>
          ))}
        </select>
      </div>
    </div>
  );
  const candidateList = candidates && (
    <div className="disambiguation">
      <p className="disambiguation-title">
        Plusieurs taxons correspondent à « {candidates.query} » — choisissez celui à ouvrir :
      </p>
      <ul>
        {flattenDisambiguationTree(buildDisambiguationTree(candidates.matches)).map(
          ({ match, depth, confirmed }, i) => (
            <li key={`${match.gbif_key ?? `${match.scientific_name}-${match.kingdom}`}-${i}`} style={{ paddingLeft: depth * 20 }}>
              <button type="button" onClick={() => launch(match)}>
                {depth > 0 && confirmed && <span className="tree-connector">└</span>}
                <MatchLabel match={match} />
              </button>
            </li>
          ),
        )}
      </ul>
      <div className="disambiguation-footer">
        <button type="button" className="edit-btn" onClick={() => setCandidates(null)}>Fermer</button>
      </div>
    </div>
  );
  const keptRow = kept.length > 0 && (
    <div className="kept-row">
      <span className="kept-label">Résultats conservés</span>
      {kept.map((name) => (
        <button key={name} type="button" className="kept-chip" onClick={() => onOpenKept(name)}>{name}</button>
      ))}
    </div>
  );

  const title = (
    <>
      <span className="eyebrow">Organon</span>
      <h1 className="home-title">Un <span>taxon</span> en entrée, <em>toutes</em> les bases disponibles en réponse</h1>
    </>
  );

  if (compact) {
    return (
      <>
        {title}
        <section aria-label="Recherche" className="search-compact">
          <form className="search-compact-row" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
            <div className="prompt search-compact-field">
              <span className="prompt-glyph" aria-hidden="true">›</span>
              {input}
              {optionsToggle}
              {dropdown}
            </div>
            <button className="run search-compact-run" type="submit" disabled={working}>
              {working ? "Recherche…" : "Rechercher"}
            </button>
          </form>
          {helpBubble}
          {options}
          {error && <p className="error-banner" role="alert">{error}</p>}
          {candidateList}
          {keptRow}
        </section>
      </>
    );
  }

  return (
    <>
      {title}
      <form className="console" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <div className="prompt">
          <span className="prompt-glyph" aria-hidden="true">›</span>
          {input}
          <button className="run home-run" type="submit" disabled={working}>
            {working ? "Recherche…" : "Rechercher ▸"}
          </button>
          {dropdown}
        </div>
        <div className="divider" />
        <div className="home-foot">
          <p className="example-row">
            exemples :{" "}
            {EXAMPLES.map((name, i) => (
              <Fragment key={name}>
                {i > 0 && " · "}
                <button type="button" onClick={() => handleExample(name)}>{name}</button>
              </Fragment>
            ))}
          </p>
          {optionsToggle}
        </div>
        {helpBubble}
        {options}
        {error && <p className="error-banner" role="alert">{error}</p>}
      </form>
      {candidateList}
      {keptRow}
    </>
  );
}
