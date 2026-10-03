// Decide, from the /search matches, whether to open a taxon directly or
// ask the user to choose. The candidate list only appears when
// ambiguous: homonyms (several identical scientific names) or a
// vernacular name with several results.
export function resolveMatches(matches, query, domain) {
  // A QID names a precise item: the domain filter (the match has no
  // kingdom) does not apply.
  if (matches.length === 1 && matches[0].qid) return { kind: "single", match: matches[0] };
  const visible = domain === "*" ? matches : matches.filter((m) => m.kingdom === domain);
  if (visible.length === 0) return { kind: "none" };
  const wanted = query.trim().toLowerCase();
  const exact = visible.filter((m) => m.scientific_name.toLowerCase() === wanted);
  // Several records of the same kingdom and rank differ only by author
  // (variants of one name at GBIF): the first, most relevant, is kept.
  // A distinct kingdom or rank is a true homonym, for the user to
  // settle.
  const kinds = new Set(exact.map((m) => `${m.kingdom}|${m.rank}`));
  if (exact.length > 0 && kinds.size === 1) return { kind: "single", match: exact[0] };
  if (exact.length === 0 && visible.length === 1) return { kind: "single", match: visible[0] };
  return { kind: "ambiguous", matches: visible };
}
