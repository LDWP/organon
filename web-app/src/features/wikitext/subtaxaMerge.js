// "alternative" groups are complete but divergent lists (see
// organon/core/rendering/subtaxa_merge.py): two groups may report the
// same species name without being identical. The key must therefore
// carry the group AND the name, never the name alone, or the checked
// state of a species would be tied to all its reappearances in other
// groups.
export function subtaxaCheckKey(groupIndex, speciesName) {
  return `${groupIndex}:${speciesName}`;
}

export function isSpeciesChecked(checked, groupIndex, species) {
  return checked[subtaxaCheckKey(groupIndex, species.name)] ?? species.default_checked;
}

// Sentence fragment common to all groups (see MergedGroup.kind
// server-side): each group carries a COMPLETE list (merged only if the
// sources agree exactly), so only the subject of the sentence changes
// (taxonPhrase for the first rendered group, pronoun afterwards).
// Singular/plural agreement: the server gives both forms (e.g.
// "espèces" and "espèce"); as the count reacts to the checked boxes,
// only the choice between them is made here.
function mergeMiddle(count, plural, singular) {
  return `comprend ${count} ${count === 1 ? singular : plural}`;
}

// Recompute (plural, singular) from the ranks actually present in
// `speciesList` rather than use `rank_text` and `rank_text_singular` as
// is (fixed server-side over the whole set, all sources): otherwise the
// sentence would keep citing a rank (e.g. "variétés") the user fully
// unchecked. `rankNames` (MergedSubtaxaResponse.rank_names) maps each
// rank key to its (plural, singular); the "comma + et" join is the only
// logic done here, like `join_and` server-side.
export function rankTextFor(speciesList, rankNames) {
  const seen = [];
  for (const sp of speciesList) {
    if (rankNames[sp.rank] && !seen.includes(sp.rank)) seen.push(sp.rank);
  }
  if (seen.length === 0) {
    return { plural: "taxons de rang inférieur", singular: "taxon de rang inférieur" };
  }
  const join = (items) =>
    items.length <= 1 ? items[0] || "" : `${items.slice(0, -1).join(", ")} et ${items[items.length - 1]}`;
  return {
    plural: join(seen.map((r) => rankNames[r][0])),
    singular: join(seen.map((r) => rankNames[r][1])),
  };
}

// Compose the "sous-taxons" block in merged mode: one sentence per
// non-empty group (a fully unchecked group disappears), followed by the
// already rendered lines of the checked species. The very first
// rendered sentence names the taxon ("le genre X comprend..."); the
// following use the `pronoun` anaphora ("il comprend..."). Based on the
// first RENDERED sentence (not on `kind === "anchor"`): if the user
// fully unchecks the anchor group, the next sentence must name the
// taxon since nothing has been said yet in the final render.
export function renderSubtaxaMergeWikitext(merge, checkedState) {
  if (!merge) return "";
  const { pronoun, taxon_phrase: taxonPhrase, rank_names: rankNames } = merge;
  const parts = [];
  const allChecked = [];
  merge.groups.forEach((group, gi) => {
    const checked = group.species.filter((s) => isSpeciesChecked(checkedState, gi, s));
    if (checked.length === 0) return;
    allChecked.push(...checked);
    const subject = parts.length === 0 ? taxonPhrase : pronoun;
    const { plural, singular } = rankTextFor(checked, rankNames);
    parts.push(`${group.intro}, ${subject} ${mergeMiddle(checked.length, plural, singular)} :\n${checked.map((s) => s.line).join("")}`);
  });
  if (parts.length === 0) return "";
  const { plural: headerPlural } = rankTextFor(allChecked, rankNames);
  return `\n== Liste des ${headerPlural} ==\n${parts.join("\n")}`;
}
