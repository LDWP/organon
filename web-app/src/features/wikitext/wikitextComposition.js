// Comment left by render_taxobox() (organon/core/rendering/sections.py)
// while no image was chosen. A selection in the Commons gallery (see
// ImageGallery.jsx) triggers no server generation: it directly replaces
// this comment in the wikitext already cached in the frontend, applied
// at display time rather than to the cache itself so the choice
// survives a classification tab change (see applyImageSelection).
export const IMAGE_PLACEHOLDER = "<!-- insérez une image -->";

export function applyImageSelection(wikitext, fileName) {
  if (!fileName || !wikitext) return wikitext;
  return wikitext.replace(IMAGE_PLACEHOLDER, fileName);
}

// Substitute the wikified author (GenerateResponse.resolved_author) of
// the active taxobox source with that of another already prefetched
// source (see authorSourceOverride), with no new network call, like
// applyImageSelection: a text replacement on the cached wikitext rather
// than a server regeneration.
export function applyAuthorOverride(wikitext, activeResolvedAuthor, overrideResolvedAuthor) {
  if (
    !wikitext ||
    !activeResolvedAuthor ||
    !overrideResolvedAuthor ||
    activeResolvedAuthor === overrideResolvedAuthor
  ) {
    return wikitext;
  }
  return wikitext.split(activeResolvedAuthor).join(overrideResolvedAuthor);
}

// Isolated blocks (taxobox_wikitext, subtaxa_wikitext...) carry leading
// and trailing newlines that only separate them cleanly when composed
// into the full wikitext (see spliceBlock); pointless for an isolated
// preview (Taxobox, Sub-ranks, References tabs), where they would add a
// useless blank line at the top or bottom.
export function trimBlockForDisplay(text) {
  return text.replace(/^\n+/, "").replace(/\n+$/, "");
}

// Replace, in the base wikitext, a section block with its equivalent
// from another source (no-op if both blocks are identical or one is
// missing). This is the whole principle of the classification "zoom":
// changing the source of a facet must affect only the matching section,
// never the rest of the article.
export function spliceBlock(baseWikitext, baseBlock, altBlock) {
  if (!baseBlock || !altBlock || baseBlock === altBlock) return baseWikitext;
  return baseWikitext.split(baseBlock).join(altBlock);
}

// Sub-taxa special case: the source recommended for the Taxobox may
// have reported no sub-taxa (empty baseBlock) while the source
// recommended for this facet has: spliceBlock then has no anchor to
// replace and the list silently disappears from "all". Insert the block
// just before "== Systématique ==", which always immediately follows
// the sub-taxa section in render order (see
// organon/core/rendering/engine.py:render): this reproduces exactly the
// position the block would have had if the base source had reported it.
export function spliceSubtaxaBlock(baseWikitext, baseBlock, altBlock) {
  if (!altBlock || baseBlock === altBlock) return baseWikitext;
  if (baseBlock) return baseWikitext.split(baseBlock).join(altBlock);
  const idx = baseWikitext.indexOf("== Systématique ==");
  if (idx === -1) return baseWikitext;
  const before = baseWikitext.slice(0, idx).replace(/\n+$/, "");
  const trimmedAlt = altBlock.replace(/^\n+|\n+$/g, "");
  return `${before}\n\n${trimmedAlt}\n\n${baseWikitext.slice(idx)}`;
}

// Replace, in the lines specific to the displayed taxobox source, those
// whose rank is contested by at least one other source with a {{Taxobox
// conflit}} listing each competing name and its source; other lines
// stay intact. Acts only on ranks explicitly checked "manage" in the
// comparison table (see managedRankConflicts): most rank disagreements
// pose no real editorial problem, so nothing is flagged by default.
export function applyRankConflicts(wikitext, rankLines, managedRankConflicts, rankDisagreements) {
  if (!rankLines) return wikitext;
  let result = wikitext;
  const resolvedRanks = new Set();
  for (const { rank, line } of rankLines) {
    if (!managedRankConflicts[rank]) continue;
    const byName = rankDisagreements[rank];
    if (!byName || byName.size < 2) continue;
    if (resolvedRanks.has(rank)) {
      // The same rank may appear several times in rankLines (e.g. ITIS
      // reporting several equivalent genera for one taxon): the
      // conflict was already inserted once for this rank, so just
      // remove the redundant line instead of duplicating it.
      result = result.split(`${line}\n`).join("");
      continue;
    }
    resolvedRanks.add(rank);
    const parts = [rank];
    for (const [otherName, sourceId] of byName) parts.push(otherName, sourceId.toUpperCase());
    result = result.split(line).join(`{{Taxobox conflit | ${parts.join(" | ")} }}`);
  }
  return result;
}
