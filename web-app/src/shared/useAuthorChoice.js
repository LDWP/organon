import { useState } from "react";

export const normalizeAuthor = (s) => s.trim().replace(/\s+/g, " ").replace(/\s*,\s*/g, ", ");

// Agreement between sources on the taxon author: merge the raw
// candidates reported by each module (see
// GenerateResponse.author_candidates, organon/api/schemas.py) over all
// the already resolved classifications, not only the active source. The
// union covers more candidates than the displayed source's
// author_candidates alone if another source (still prefetching) were
// ignored.
export function useAuthorChoice(classificationModules, resultsBySource, activeSource, activeData) {
  // Manual choice of the author source in the "Auteur" card of the
  // Names & synonyms tab: `null` until an explicit choice, in which
  // case the backend majority vote (consolidated_author) applies.
  const [sourceOverride, setSourceOverride] = useState(null);

  const candidates = {};
  for (const m of classificationModules) {
    const entry = resultsBySource[m.id];
    if (entry?.status === "ok") Object.assign(candidates, entry.data.author_candidates);
  }
  const values = Object.values(candidates).filter(Boolean);
  const variants = new Set(values.map(normalizeAuthor));
  // By default, the author already retained by the backend majority
  // vote (`consolidated_author`, the one wikified in the wikitext
  // through `resolved_author`), not the raw text of the active module
  // alone, which can lose the vote (e.g. Campylobacter: ITIS classifies
  // the taxon but WRMS and INPN win on the author, 2 votes to 1). Fall
  // back on the raw text of the active module, then the first known
  // candidate if the vote kept nothing. A manual choice overrides
  // everything.
  const displayed =
    (sourceOverride && candidates[sourceOverride]) ||
    activeData?.consolidated_author ||
    candidates[activeSource] ||
    values[0] ||
    null;
  // Wikified version of the chosen author, for applyAuthorOverride:
  // only available if that source was already prefetched.
  const overrideResolved =
    sourceOverride && resultsBySource[sourceOverride]?.status === "ok"
      ? resultsBySource[sourceOverride].data.resolved_author
      : null;

  return { sourceOverride, chooseSource: setSourceOverride, values, variants, displayed, overrideResolved };
}
