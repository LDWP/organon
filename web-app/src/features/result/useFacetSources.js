import { useCallback, useState } from "react";
import { buildClassificationTable, computeRankDisagreements } from "@/shared/rankComparison.js";

// Effective source per facet of the classification "zoom" (taxobox,
// sub-taxa), and data derived from the already resolved classifications
// (rank disagreements, comparison table).
export function useFacetSources(classificationModules, resultsBySource, activeSource) {
  // Manual user choice for the taxobox facet (comparison table of the
  // Taxobox tab): `null` until an explicit choice, in which case the
  // automatic recommendation applies. The sub-taxa facet has no manual
  // choice: it always follows the recommended source.
  const [taxoboxSourceOverride, setTaxoboxSourceOverride] = useState(null);
  // Ranks for which the user asked to flag the source disagreement in
  // the render (inserting {{Taxobox conflit}}): per rank rather than a
  // global switch, so a contested rank (e.g. "classe") can be handled
  // without marking others that pose no real editorial problem.
  const [managedRankConflicts, setManagedRankConflicts] = useState({});

  // Automatic recommendation, independent per facet: a single
  // aggregated `completeness_score` hid that a classification may have
  // the best taxobox without the best sub-taxa list, or the reverse
  // (see `taxobox_completeness_score` and `subtaxa_completeness_score`
  // backend-side). Recomputed at each render rather than stored, to
  // follow the background prefetch as other sources finish.
  //
  // Tie-break: `activeSource` (the `used_classification` winner
  // returned by the backend) is the starting point rather than an
  // arbitrary score; the backend already arbitrates by domain
  // specialization (`best_classification`, organon/core/domains.py), so
  // on a tie or an unloaded score that choice stays displayed as the
  // recommendation. A strictly more complete source can still supersede
  // it for this facet.
  function recommendedSourceForFacet(scoreField) {
    let recommended = activeSource;
    let bestScore = activeSource ? (resultsBySource[activeSource]?.data?.[scoreField] ?? 0) : -1;
    for (const m of classificationModules) {
      const entry = resultsBySource[m.id];
      if (entry?.status !== "ok") continue;
      const score = entry.data[scoreField] ?? 0;
      if (score > bestScore) {
        recommended = m.id;
        bestScore = score;
      }
    }
    return recommended;
  }

  const recommendedTaxoboxSource = recommendedSourceForFacet("taxobox_completeness_score");
  const recommendedSubtaxaSource = recommendedSourceForFacet("subtaxa_completeness_score");

  // A manual choice beats the automatic recommendation, which beats the
  // active source as long as no source has finished.
  const taxoboxSourceId = taxoboxSourceOverride ?? recommendedTaxoboxSource ?? activeSource;
  const subtaxaSourceId = recommendedSubtaxaSource ?? activeSource;

  const taxoboxEntry = taxoboxSourceId ? resultsBySource[taxoboxSourceId] : null;
  const taxoboxData = taxoboxEntry?.status === "ok" ? taxoboxEntry.data : null;
  const subtaxaEntry = subtaxaSourceId ? resultsBySource[subtaxaSourceId] : null;
  const subtaxaData = subtaxaEntry?.status === "ok" ? subtaxaEntry.data : null;

  // Sources usable for the facet selectors and the per-rank comparison:
  // only those already resolved successfully (a failed or still
  // prefetching source can feed neither the taxobox nor the sub-taxa).
  const availableSources = classificationModules.filter((m) => resultsBySource[m.id]?.status === "ok");

  // Name retained per rank for the currently displayed taxobox source:
  // used to highlight, in the comparison table, only the names that
  // *differ* from this choice.
  const taxoboxNameByRank = {};
  for (const { rank, name } of taxoboxData?.rank_lines || []) {
    if (!(rank in taxoboxNameByRank)) taxoboxNameByRank[rank] = name;
  }

  const toggleRankConflictManaged = useCallback((rank) => {
    setManagedRankConflicts((prev) => ({ ...prev, [rank]: !prev[rank] }));
  }, []);

  const reset = useCallback(() => {
    setTaxoboxSourceOverride(null);
    setManagedRankConflicts({});
  }, []);

  return {
    recommendedTaxoboxSource,
    taxoboxSourceId,
    taxoboxData,
    subtaxaData,
    // The base article (systematics, distribution, etymology, original
    // publication, external links...) comes from the source chosen for
    // the taxobox facet: only two facets are exposed to the user, and
    // the rest of the article must come from a single source. That
    // source also feeds the taxobox directly, so only the sub-taxa
    // block may need substituting (see spliceBlock).
    baseData: taxoboxData,
    availableSources,
    rankDisagreements: computeRankDisagreements(classificationModules, resultsBySource),
    classificationTable: buildClassificationTable(availableSources, resultsBySource, recommendedTaxoboxSource),
    taxoboxNameByRank,
    managedRankConflicts,
    chooseTaxoboxSource: setTaxoboxSourceOverride,
    toggleRankConflictManaged,
    reset,
  };
}
