import { useCallback, useEffect, useState } from "react";
import { mergeSubtaxa } from "@/api/client.js";
import { renderSubtaxaMergeWikitext, subtaxaCheckKey } from "./subtaxaMerge.js";

// Merge of the sub-taxa of the already resolved classification sources
// (POST /api/v1/subtaxa-merge) and per-species checkboxes.
// `availableSources`: successfully resolved modules; `baseData`:
// response of the taxobox source (null until one finishes).
export function useSubtaxaMerge(availableSources, resultsBySource, baseData) {
  // Server response (MergedSubtaxaResponse), `null` until it arrives.
  const [merge, setMerge] = useState(null);
  // One checkbox per species (key = group + name, see subtaxaCheckKey),
  // initialized from `default_checked` when each species arrives, then
  // left to the user: an already known species keeps its state even if
  // the merge is recomputed (e.g. one more source finishes
  // prefetching).
  const [checked, setChecked] = useState({});

  // Sources that actually reported sub-taxa (GenerateResponse.subtaxa):
  // a subset of availableSources that also requires a non-empty list.
  const sources = availableSources
    .map((m) => ({ id: m.id, subtaxa: resultsBySource[m.id]?.data?.subtaxa || [] }))
    .filter((s) => s.subtaxa.length > 0);
  // Stable signature (id + species count per source): an effect
  // dependency to rerun the call only when the set of available sources
  // really changes, not at each render (`sources` is a new array at
  // each call).
  const signature = sources.map((s) => `${s.id}:${s.subtaxa.length}`).join(",");

  // `false` until at least two sources have sub-taxa: the effect then
  // has nothing to do, and `merge` is ignored in favor of
  // `effectiveMerge` (derived from the current render rather than a
  // synchronous setState in the effect).
  const ready = sources.length >= 2 && !!baseData;
  const effectiveMerge = ready ? merge : null;

  // Compute (or recompute) the merge as soon as at least two sources
  // have sub-taxa, without waiting for the sub-tab to open: the
  // computation is local server-side, except a targeted COL XR call
  // when two sources diverge on names (see
  // organon/api/routes/subtaxa_merge.py); the call can be anticipated
  // during the prefetch.
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    mergeSubtaxa({
      taxon_rank: baseData.taxon_rank,
      taxon_name: baseData.resolved_taxon,
      kingdom: baseData.kingdom,
      sources: sources.map((s) => ({ module_id: s.id, subtaxa: s.subtaxa })),
    })
      .then((data) => {
        if (cancelled) return;
        setMerge(data);
        // Only newly appeared species get their default_checked.
        setChecked((prev) => {
          const next = { ...prev };
          data.groups.forEach((g, gi) => {
            for (const s of g.species) {
              const key = subtaxaCheckKey(gi, s.name);
              if (!(key in next)) next[key] = s.default_checked;
            }
          });
          return next;
        });
      })
      .catch(() => {
        if (!cancelled) setMerge(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, signature, baseData?.taxon_rank, baseData?.resolved_taxon, baseData?.kingdom]);

  const toggleSpecies = useCallback((groupIndex, speciesName) => {
    const key = subtaxaCheckKey(groupIndex, speciesName);
    setChecked((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const setGroupChecked = useCallback((groupIndex, group, value) => {
    setChecked((prev) => {
      const next = { ...prev };
      for (const sp of group.species) next[subtaxaCheckKey(groupIndex, sp.name)] = value;
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setMerge(null);
    setChecked({});
  }, []);

  return {
    sources,
    // Merge whenever possible: no more manual switch to the single
    // source (redundant with the fold/unfold of the "Sous-rangs" card).
    enabled: ready,
    merge: effectiveMerge,
    checked,
    wikitext: ready ? renderSubtaxaMergeWikitext(effectiveMerge, checked) : "",
    toggleSpecies,
    setGroupChecked,
    reset,
  };
}
